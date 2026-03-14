from __future__ import annotations

import logging
import os
import pathspec
from datetime import datetime, timezone
from pathlib import Path

from code_atlas.core.config import DEFAULT_INGESTION_CONFIG, IngestionConfig
from code_atlas.core.models import FileRecord, FileStatus
from code_atlas.ingestion.hasher import hash_files_parallel
from code_atlas.ingestion.language_detector import detect_language, is_binary_file

logger = logging.getLogger(__name__)

def get_gitignore_spec(repo_path: Path) -> pathspec.PathSpec:
    gitignore_path = repo_path / ".gitignore"
    if gitignore_path.exists():
        with open(gitignore_path, "r", encoding="utf-8") as f:
            return pathspec.PathSpec.from_lines('gitwildmatch', f)
    return pathspec.PathSpec.from_lines('gitwildmatch', [])

def scan_repository(
    root: Path,
    stored_hashes: dict[str, str],
    config: IngestionConfig | None = None,
) -> list[FileRecord]:
    """
    Walk root and return a FileRecord for every valid source file.
    Respects .gitignore and IngestionConfig exclusion rules.
    """
    cfg = config or DEFAULT_INGESTION_CONFIG
    root = root.resolve()
    
    ignore_spec = get_gitignore_spec(root)

    logger.info("Scanning %s ...", root)

    candidate_paths = _walk(root, cfg, ignore_spec)
    logger.info("Found %d candidate source files.", len(candidate_paths))

    if not candidate_paths:
        logger.warning("No source files found under %s. Check exclusion rules.", root)
        return _handle_deletions(root, {}, stored_hashes)

    hash_map: dict[Path, str] = hash_files_parallel(
        candidate_paths, workers=cfg.hash_workers
    )
    
    records: list[FileRecord] = []
    for abs_path, sha256 in hash_map.items():
        rel_path = str(abs_path.relative_to(root))
        language = detect_language(abs_path)
        
        if language is None:
            continue

        try:
            stat = abs_path.stat()
        except OSError as exc:
            logger.warning("Cannot stat %s: %s — skipping.", abs_path, exc)
            continue

        prev_hash = stored_hashes.get(rel_path)
        if prev_hash is None:
            status = FileStatus.NEW
        elif prev_hash != sha256:
            status = FileStatus.MODIFIED
        else:
            status = FileStatus.UNCHANGED

        line_count = _count_lines(abs_path) if status != FileStatus.UNCHANGED else 0

        records.append(FileRecord(
            path=rel_path,
            absolute_path=str(abs_path),
            language=language,
            sha256=sha256,
            size_bytes=stat.st_size,
            last_modified=datetime.fromtimestamp(stat.st_mtime, tz=timezone.utc),
            status=status,
            line_count=line_count,
        ))

    return _handle_deletions(root, hash_map, stored_hashes, records)

def _walk(root: Path, cfg: IngestionConfig, ignore_spec: pathspec.PathSpec) -> list[Path]:
    result: list[Path] = []

    for dirpath, dirnames, filenames in os.walk(root, topdown=True):
        current_dir = Path(dirpath)
        
        dirnames[:] = [
            d for d in dirnames
            if d not in cfg.excluded_dirs 
            and not d.startswith(".")
            and not ignore_spec.match_file(str((current_dir / d).relative_to(root)))
        ]

        for filename in filenames:
            abs_path = current_dir / filename
            rel_path = str(abs_path.relative_to(root))

            if ignore_spec.match_file(rel_path):
                continue
            ext = abs_path.suffix.lower()
            if ext and ext not in cfg.source_extensions:
                continue

            try:
                if abs_path.stat().st_size > cfg.max_file_size_bytes:
                    continue
            except OSError:
                continue

            if is_binary_file(abs_path):
                continue

            result.append(abs_path)

    return result

def _handle_deletions(root: Path, current_map: dict, stored_hashes: dict, records: list = None) -> list[FileRecord]:
    if records is None: records = []
    
    current_paths = {str(p.relative_to(root)) for p in current_map}
    deleted_paths = set(stored_hashes.keys()) - current_paths

    for rel_path in deleted_paths:
        records.append(FileRecord(
            path=rel_path,
            language="unknown",
            sha256="",
            size_bytes=0,
            last_modified=datetime.now(timezone.utc),
            status=FileStatus.DELETED,
        ))
    return records

def _count_lines(path: Path) -> int:
    count = 0
    try:
        with path.open("rb") as fh:
            while chunk := fh.read(65_536):
                count += chunk.count(b"\n")
    except OSError:
        pass
    return count


# Purpose
# This module persists ingestion results to disk using SQLite
# This is the engine of ingestion.
# It walks through the repository and identifies valid source files.


# run_ingestion()
#       ↓
# clone repo
#       ↓
# scan files
#       ↓
# detect language
#       ↓
# hash files
#       ↓
# detect changes
#       ↓
# store metadata
#       ↓
# return RepoManifest