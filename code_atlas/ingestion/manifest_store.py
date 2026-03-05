from __future__ import annotations

import sqlite3
import logging
from contextlib import contextmanager
from datetime import datetime, timezone
from pathlib import Path
from typing import Iterator

from code_atlas.core.config import MANIFESTS_DIR
from code_atlas.core.models import FileRecord, FileStatus

logger = logging.getLogger(__name__)

_CREATE_TABLE = """
CREATE TABLE IF NOT EXISTS files (
    repo_id       TEXT    NOT NULL,
    path          TEXT    NOT NULL,
    language      TEXT    NOT NULL,
    sha256        TEXT    NOT NULL,
    size_bytes    INTEGER NOT NULL,
    last_modified TEXT    NOT NULL,
    line_count    INTEGER NOT NULL DEFAULT 0,
    indexed_at    TEXT    NOT NULL,
    PRIMARY KEY (repo_id, path)
);
"""

_CREATE_META = """
CREATE TABLE IF NOT EXISTS repo_meta (
    repo_id          TEXT PRIMARY KEY,
    source           TEXT,
    source_type      TEXT,
    git_branch       TEXT,
    git_commit       TEXT,
    last_indexed_at  TEXT
);
"""


class ManifestStore:
    def __init__(self, repo_id: str, manifests_dir: Path | None = None) -> None:
        self.repo_id = repo_id
        _dir = manifests_dir or MANIFESTS_DIR
        _dir.mkdir(parents=True, exist_ok=True)
        self.db_path = _dir / f"{repo_id}.db"
        self._init_db()

    @contextmanager
    def _conn(self) -> Iterator[sqlite3.Connection]:
        con = sqlite3.connect(self.db_path, timeout=10)
        con.row_factory = sqlite3.Row
        con.execute("PRAGMA journal_mode=WAL;")
        con.execute("PRAGMA foreign_keys=ON;")
        try:
            yield con
            con.commit()
        except Exception:
            con.rollback()
            raise
        finally:
            con.close()

    def _init_db(self) -> None:
        with self._conn() as con:
            con.execute(_CREATE_TABLE)
            con.execute(_CREATE_META)

    def load_snapshot(self) -> dict[str, str]:
        with self._conn() as con:
            rows = con.execute(
                "SELECT path, sha256 FROM files WHERE repo_id = ?",
                (self.repo_id,),
            ).fetchall()
        return {row["path"]: row["sha256"] for row in rows}

    def load_all_records(self) -> list[FileRecord]:
        with self._conn() as con:
            rows = con.execute(
                "SELECT * FROM files WHERE repo_id = ?",
                (self.repo_id,),
            ).fetchall()
        records = []
        for row in rows:
            records.append(FileRecord(
                path=row["path"],
                language=row["language"],
                sha256=row["sha256"],
                size_bytes=row["size_bytes"],
                last_modified=datetime.fromisoformat(row["last_modified"]),
                line_count=row["line_count"],
                status=FileStatus.UNCHANGED,
            ))
        return records

    def save_records(self, records: list[FileRecord]) -> None:
        now = datetime.now(timezone.utc).isoformat()
        to_upsert = [r for r in records if r.status != FileStatus.DELETED]
        to_delete = [r for r in records if r.status == FileStatus.DELETED]

        with self._conn() as con:
            if to_delete:
                con.executemany(
                    "DELETE FROM files WHERE repo_id = ? AND path = ?",
                    [(self.repo_id, r.path) for r in to_delete],
                )
                logger.debug("Removed %d deleted file records.", len(to_delete))

            if to_upsert:
                con.executemany(
                    """
                    INSERT INTO files
                        (repo_id, path, language, sha256, size_bytes, last_modified, line_count, indexed_at)
                    VALUES (?, ?, ?, ?, ?, ?, ?, ?)
                    ON CONFLICT(repo_id, path) DO UPDATE SET
                        language      = excluded.language,
                        sha256        = excluded.sha256,
                        size_bytes    = excluded.size_bytes,
                        last_modified = excluded.last_modified,
                        line_count    = excluded.line_count,
                        indexed_at    = excluded.indexed_at
                    """,
                    [
                        (
                            self.repo_id, r.path, r.language, r.sha256,
                            r.size_bytes, r.last_modified.isoformat(),
                            r.line_count, now,
                        )
                        for r in to_upsert
                    ],
                )
                logger.debug("Upserted %d file records.", len(to_upsert))

    def save_repo_meta(
        self,
        source: str,
        source_type: str,
        git_branch: str | None,
        git_commit: str | None,
    ) -> None:
        now = datetime.now(timezone.utc).isoformat()
        with self._conn() as con:
            con.execute(
                """
                INSERT INTO repo_meta (repo_id, source, source_type, git_branch, git_commit, last_indexed_at)
                VALUES (?, ?, ?, ?, ?, ?)
                ON CONFLICT(repo_id) DO UPDATE SET
                    git_branch      = excluded.git_branch,
                    git_commit      = excluded.git_commit,
                    last_indexed_at = excluded.last_indexed_at
                """,
                (self.repo_id, source, source_type, git_branch, git_commit, now),
            )

    def last_indexed_at(self) -> datetime | None:
        with self._conn() as con:
            row = con.execute(
                "SELECT last_indexed_at FROM repo_meta WHERE repo_id = ?",
                (self.repo_id,),
            ).fetchone()
        if row and row["last_indexed_at"]:
            return datetime.fromisoformat(row["last_indexed_at"])
        return None

    def stats(self) -> dict:
        with self._conn() as con:
            total = con.execute(
                "SELECT COUNT(*) FROM files WHERE repo_id = ?", (self.repo_id,)
            ).fetchone()[0]
            by_lang = con.execute(
                "SELECT language, COUNT(*) AS cnt FROM files WHERE repo_id = ? GROUP BY language ORDER BY cnt DESC",
                (self.repo_id,),
            ).fetchall()
        return {
            "total_files": total,
            "by_language": {row["language"]: row["cnt"] for row in by_lang},
        }
