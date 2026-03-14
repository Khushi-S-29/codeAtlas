from __future__ import annotations

import logging
import re
import time
from pathlib import Path

from code_atlas.core.config import DEFAULT_INGESTION_CONFIG, REPOS_DIR, MANIFESTS_DIR, IngestionConfig
from code_atlas.core.models import FileRecord, FileStatus, IngestionSource, RepoManifest
from code_atlas.ingestion.git_cloner import GitRepoInfo, clone_or_update, get_repo_info
from code_atlas.ingestion.manifest_store import ManifestStore
from code_atlas.ingestion.scanner import scan_repository

logger = logging.getLogger(__name__)

_URL_PATTERN = re.compile(r"^(https?://|git@|ssh://|git://)", re.IGNORECASE)

def run_ingestion(
    source: str | Path,
    branch: str | None = None,
    config: IngestionConfig | None = None,
    manifests_dir: Path | None = None,
    repos_dir: Path | None = None,
) -> RepoManifest:
    cfg = config or DEFAULT_INGESTION_CONFIG
    source_str = str(source)
    t_start = time.perf_counter()

    _manifests_dir = manifests_dir or MANIFESTS_DIR
    _repos_dir = repos_dir or REPOS_DIR
    _manifests_dir.mkdir(parents=True, exist_ok=True)
    _repos_dir.mkdir(parents=True, exist_ok=True)

    logger.info("═══ Phase 1: Ingestion ═══")
    logger.info("Source: %s", source_str)

    repo_info, source_type = _resolve_source(source_str, branch, cfg, _repos_dir)
    logger.info("Repo ID  : %s", repo_info.repo_id)
    logger.info("Local    : %s", repo_info.local_path)
    logger.info("Branch   : %s", repo_info.branch)
    logger.info("Commit   : %s", repo_info.commit_sha)

    store = ManifestStore(repo_info.repo_id, manifests_dir=_manifests_dir)
    stored_hashes = store.load_snapshot()
    prev_indexed_at = store.last_indexed_at()

    is_incremental = bool(stored_hashes)
    logger.info(
        "%s run — %d files in stored snapshot.",
        "Incremental" if is_incremental else "First-time",
        len(stored_hashes),
    )

    records: list[FileRecord] = scan_repository(
        root=repo_info.local_path,
        stored_hashes=stored_hashes,
        config=cfg,
    )

    store.save_records(records)
    store.save_repo_meta(
        source=source_str,
        source_type=source_type.value,
        git_branch=repo_info.branch,
        git_commit=repo_info.commit_sha,
    )

    manifest = RepoManifest(
        repo_id=repo_info.repo_id,
        source=source_str,
        source_type=source_type,
        local_path=str(repo_info.local_path),
        git_branch=repo_info.branch,
        git_commit=repo_info.commit_sha,
        previous_index_at=prev_indexed_at,
        files=records,
    )

    elapsed = time.perf_counter() - t_start
    logger.info("Phase 1 complete in %.2fs", elapsed)
    logger.info("\n%s", manifest.summary())

    return manifest

def _resolve_source(
    source: str,
    branch: str | None,
    cfg: IngestionConfig,
    repos_dir: Path,
) -> tuple[GitRepoInfo, IngestionSource]:
    if _URL_PATTERN.match(source):
        repo_info = clone_or_update(
            url=source,
            dest_dir=repos_dir,
            branch=branch,
            depth=cfg.clone_depth,
        )
        return repo_info, IngestionSource.GIT_URL
    else:
        local_path = Path(source).expanduser().resolve()
        if not local_path.exists():
            raise FileNotFoundError(f"Local path does not exist: {local_path}")
        if not local_path.is_dir():
            raise NotADirectoryError(f"Source must be a directory: {local_path}")
        repo_info = get_repo_info(local_path)
        return repo_info, IngestionSource.LOCAL_PATH


# This file is the orchestrator of the entire ingestion phase.

# Everything you've seen so far connects here.



'''
Step-by-step execution
Step 1 — Setup configuration
cfg = config or DEFAULT_INGESTION_CONFIG

Loads ingestion settings.

Step 2 — Prepare directories

Creates:

repos/
manifests/

Inside .code_atlas.

Step 3 — Resolve source

Function:

_resolve_source()

Determines whether input is:

Git URL
OR
Local directory

Example inputs:

https://github.com/user/project
~/projects/project

If URL:

clone_or_update()

If local path:

get_repo_info()
Step 4 — Load previous snapshot
stored_hashes = store.load_snapshot()

This gives:

previous file hashes

Used for incremental detection.

Step 5 — Scan repository

Calls:

scan_repository()

This is where most ingestion logic happens.

Step 6 — Save results
store.save_records(records)

Saves new metadata.

Step 7 — Save repo metadata

Stores:

git branch
git commit
index timestamp
Step 8 — Create RepoManifest
RepoManifest(...)

This object contains:

repo info
file records
change status

Example structure:

RepoManifest
 ├ repo_id
 ├ source
 ├ files
 │   ├ FileRecord
 │   ├ FileRecord
Step 9 — Logging summary
manifest.summary()

Example output:

Repo      : github-user-project
Files     : 120 (14,000 lines)
New       : 10
Modified  : 4
Unchanged : 106
Deleted   : 0
Languages : {'python': 70, 'js': 50}
'''