from __future__ import annotations

import json
import logging
import sqlite3
from contextlib import contextmanager
from pathlib import Path
from typing import Iterator, Optional

from code_atlas.core.config import DATA_DIR
from code_atlas.core.models import IRNode, NodeKind

logger = logging.getLogger(__name__)

IR_DIR = DATA_DIR / "ir"
IR_DIR.mkdir(parents=True, exist_ok=True)

_CREATE_NODES = """
CREATE TABLE IF NOT EXISTS ir_nodes (
    id           TEXT PRIMARY KEY,
    name         TEXT NOT NULL,
    kind         TEXT NOT NULL,
    file_path    TEXT NOT NULL,
    start_line   INTEGER NOT NULL,
    end_line     INTEGER NOT NULL,
    language     TEXT NOT NULL,
    parent_class TEXT,
    return_type  TEXT,
    docstring    TEXT,
    signature    TEXT,
    is_exported  INTEGER NOT NULL DEFAULT 1,
    -- JSON arrays stored as text
    parameters   TEXT NOT NULL DEFAULT '[]',
    calls        TEXT NOT NULL DEFAULT '[]',
    imports      TEXT NOT NULL DEFAULT '[]',
    bases        TEXT NOT NULL DEFAULT '[]',
    decorators   TEXT NOT NULL DEFAULT '[]'
);
"""

_CREATE_IDX_FILE  = "CREATE INDEX IF NOT EXISTS idx_file ON ir_nodes(file_path);"
_CREATE_IDX_KIND  = "CREATE INDEX IF NOT EXISTS idx_kind ON ir_nodes(kind);"
_CREATE_IDX_NAME  = "CREATE INDEX IF NOT EXISTS idx_name ON ir_nodes(name);"


class IRStore:
    def __init__(self, repo_id: str, ir_dir: Optional[Path] = None) -> None:
        self.repo_id = repo_id
        _dir = ir_dir or IR_DIR
        _dir.mkdir(parents=True, exist_ok=True)
        self.db_path = _dir / f"{repo_id}.db"
        self._init_db()

    @contextmanager
    def _conn(self) -> Iterator[sqlite3.Connection]:
        con = sqlite3.connect(self.db_path, timeout=10)
        con.row_factory = sqlite3.Row
        con.execute("PRAGMA journal_mode=WAL;")
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
            con.execute(_CREATE_NODES)
            con.execute(_CREATE_IDX_FILE)
            con.execute(_CREATE_IDX_KIND)
            con.execute(_CREATE_IDX_NAME)

    def delete_file(self, file_path: str) -> int:
        with self._conn() as con:
            cur = con.execute(
                "DELETE FROM ir_nodes WHERE file_path = ?", (file_path,)
            )
        deleted = cur.rowcount
        logger.debug("Deleted %d nodes for %s", deleted, file_path)
        return deleted

    def upsert_nodes(self, nodes: list[IRNode]) -> None:
        if not nodes:
            return
        rows = [_node_to_row(n) for n in nodes]
        with self._conn() as con:
            con.executemany(
                """
                INSERT OR REPLACE INTO ir_nodes
                  (id, name, kind, file_path, start_line, end_line, language,
                   parent_class, return_type, docstring, signature, is_exported,
                   parameters, calls, imports, bases, decorators)
                VALUES
                  (:id, :name, :kind, :file_path, :start_line, :end_line, :language,
                   :parent_class, :return_type, :docstring, :signature, :is_exported,
                   :parameters, :calls, :imports, :bases, :decorators)
                """,
                rows,
            )
        logger.debug("Upserted %d IR nodes.", len(nodes))

    def load_all(self) -> list[IRNode]:
        with self._conn() as con:
            rows = con.execute("SELECT * FROM ir_nodes").fetchall()
        return [_row_to_node(r) for r in rows]

    def load_by_file(self, file_path: str) -> list[IRNode]:
        with self._conn() as con:
            rows = con.execute(
                "SELECT * FROM ir_nodes WHERE file_path = ?", (file_path,)
            ).fetchall()
        return [_row_to_node(r) for r in rows]

    def load_by_kind(self, kind: NodeKind) -> list[IRNode]:
        with self._conn() as con:
            rows = con.execute(
                "SELECT * FROM ir_nodes WHERE kind = ?", (kind.value,)
            ).fetchall()
        return [_row_to_node(r) for r in rows]

    def find_by_name(self, name: str) -> list[IRNode]:
        with self._conn() as con:
            rows = con.execute(
                "SELECT * FROM ir_nodes WHERE lower(name) = lower(?)", (name,)
            ).fetchall()
        return [_row_to_node(r) for r in rows]

    def stats(self) -> dict:
        with self._conn() as con:
            total = con.execute("SELECT COUNT(*) FROM ir_nodes").fetchone()[0]
            by_kind = con.execute(
                "SELECT kind, COUNT(*) AS cnt FROM ir_nodes GROUP BY kind ORDER BY cnt DESC"
            ).fetchall()
            by_lang = con.execute(
                "SELECT language, COUNT(*) AS cnt FROM ir_nodes GROUP BY language ORDER BY cnt DESC"
            ).fetchall()
        return {
            "total_nodes": total,
            "by_kind": {r["kind"]: r["cnt"] for r in by_kind},
            "by_language": {r["language"]: r["cnt"] for r in by_lang},
        }


def _node_to_row(node: IRNode) -> dict:
    return {
        "id":           node.id,
        "name":         node.name,
        "kind":         node.kind if isinstance(node.kind, str) else node.kind.value,
        "file_path":    node.file_path,
        "start_line":   node.start_line,
        "end_line":     node.end_line,
        "language":     node.language,
        "parent_class": node.parent_class,
        "return_type":  node.return_type,
        "docstring":    node.docstring,
        "signature":    node.signature,
        "is_exported":  int(node.is_exported),
        "parameters":   json.dumps(node.parameters),
        "calls":        json.dumps(node.calls),
        "imports":      json.dumps(node.imports),
        "bases":        json.dumps(node.bases),
        "decorators":   json.dumps(node.decorators),
    }


def _row_to_node(row: sqlite3.Row) -> IRNode:
    return IRNode(
        id=row["id"],
        name=row["name"],
        kind=row["kind"],
        file_path=row["file_path"],
        start_line=row["start_line"],
        end_line=row["end_line"],
        language=row["language"],
        parent_class=row["parent_class"],
        return_type=row["return_type"],
        docstring=row["docstring"],
        signature=row["signature"],
        is_exported=bool(row["is_exported"]),
        parameters=json.loads(row["parameters"]),
        calls=json.loads(row["calls"]),
        imports=json.loads(row["imports"]),
        bases=json.loads(row["bases"]),
        decorators=json.loads(row["decorators"]),
    )