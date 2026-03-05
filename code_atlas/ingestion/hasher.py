from __future__ import annotations

import hashlib
import logging
from concurrent.futures import ThreadPoolExecutor, as_completed
from pathlib import Path

from code_atlas.core.config import DEFAULT_INGESTION_CONFIG

logger = logging.getLogger(__name__)

_CHUNK = 65_536 

def hash_file(path: Path) -> str:
    h = hashlib.sha256()
    with path.open("rb") as fh:
        while chunk := fh.read(_CHUNK):
            h.update(chunk)
    return h.hexdigest()

def hash_files_parallel(
    paths: list[Path],
    workers: int | None = None,
) -> dict[Path, str]:
    if workers is None:
        workers = DEFAULT_INGESTION_CONFIG.hash_workers

    result: dict[Path, str] = {}

    if not paths:
        return result

    with ThreadPoolExecutor(max_workers=workers) as pool:
        future_to_path = {pool.submit(hash_file, p): p for p in paths}

        for future in as_completed(future_to_path):
            path = future_to_path[future]
            try:
                result[path] = future.result()
            except OSError as exc:
                logger.warning("Could not hash %s: %s", path, exc)

    return result

def compute_change_set(
    current_hashes: dict[str, str],   
    stored_hashes:  dict[str, str],  
) -> dict[str, str]:
    changed: dict[str, str] = {}
    
    for rel_path, sha256 in current_hashes.items():
        prev = stored_hashes.get(rel_path)
        if prev is None or prev != sha256:
            changed[rel_path] = sha256

    return changed
