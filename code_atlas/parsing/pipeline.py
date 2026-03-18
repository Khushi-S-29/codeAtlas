from __future__ import annotations

import concurrent.futures
import logging
import time
from pathlib import Path
from typing import Optional

from code_atlas.core.models import FileRecord, ParseResult, ParsingReport, RepoManifest
from code_atlas.parsing.ir_store import IRStore
from code_atlas.parsing.visitors import get_visitor

logger = logging.getLogger(__name__)

_SKIP_LANGUAGES = frozenset({
    "json", "yaml", "toml", "html", "css", "scss",
    "markdown", "text", "unknown",
})

_DEFAULT_WORKERS = 4


def run_parsing(
    manifest: RepoManifest,
    ir_dir: Optional[Path] = None,
    workers: int = _DEFAULT_WORKERS,
) -> ParsingReport:
    # run phase 2 for all files in *manifest.change_set*.
    t_start = time.perf_counter()
    logger.info("═══ Phase 2: Parsing & IR Extraction ═══")
    logger.info("Repo     : %s", manifest.repo_id)
    logger.info("Files    : %d in change set", len(manifest.change_set))

    store = IRStore(manifest.repo_id, ir_dir=ir_dir)
    repo_root = Path(manifest.local_path)

    parseable = [f for f in manifest.change_set if f.language not in _SKIP_LANGUAGES]
    skipped = len(manifest.change_set) - len(parseable)
    if skipped:
        logger.info("Skipping %d non-structural files (JSON/CSS/HTML/…)", skipped)

    report = ParsingReport(repo_id=manifest.repo_id)

    if not parseable:
        logger.info("Nothing to parse.")
        return report

    results: list[ParseResult] = []

    with concurrent.futures.ThreadPoolExecutor(max_workers=workers) as pool:
        future_to_file = {
            pool.submit(_parse_one, f, repo_root, manifest.repo_id): f
            for f in parseable
        }
        for future in concurrent.futures.as_completed(future_to_file):
            file_record = future_to_file[future]
            try:
                result = future.result()
                results.append(result)
                status = "✓" if result.success else "✗"
                logger.debug(
                    "%s %s  (%d nodes, %d calls, %d imports, %d inherits)",
                    status, file_record.path,
                    len(result.nodes),
                    len(result.call_edges),
                    len(result.import_edges),
                    len(result.inheritance_edges),
                )
            except Exception as exc:
                logger.warning("Unexpected error parsing %s: %s", file_record.path, exc)
                results.append(ParseResult(
                    file_path=file_record.path,
                    language=file_record.language,
                    success=False,
                    errors=[str(exc)],
                ))

    #  Persist to IR store 
    for result in results:
        store.delete_file(result.file_path)

        if result.nodes:
            store.upsert_nodes(result.nodes)

        if result.call_edges:
            store.upsert_call_edges(result.call_edges)
        if result.import_edges:
            store.upsert_import_edges(result.import_edges)
        if result.inheritance_edges:
            store.upsert_inheritance_edges(result.inheritance_edges)
        if result.reference_edges:
            store.upsert_reference_edges(result.reference_edges)

    report.results = results

    elapsed = time.perf_counter() - t_start
    logger.info("Phase 2 complete in %.2fs", elapsed)
    logger.info("\n%s", report.summary())

    stats = store.stats()
    logger.info(
        "IR store: %d nodes | %d call_edges | %d import_edges | %d inherit_edges | %s",
        stats["total_nodes"],
        stats["call_edges"],
        stats["import_edges"],
        stats["inheritance_edges"],
        " | ".join(f"{k}: {v}" for k, v in stats["by_kind"].items()),
    )

    return report

def _parse_one(file_record: FileRecord, repo_root: Path, repo_id: str) -> ParseResult:
    abs_path = repo_root / file_record.path

    try:
        source_code = abs_path.read_text(encoding="utf-8", errors="replace")
    except OSError as exc:
        return ParseResult(
            file_path=file_record.path,
            language=file_record.language,
            success=False,
            errors=[f"Could not read file: {exc}"],
        )

    visitor = get_visitor(file_record.language)
    try:
        return visitor.parse(source_code, file_record.path, repo_id)
    except Exception as exc:
        logger.warning("Visitor crashed on %s: %s", file_record.path, exc)
        return ParseResult(
            file_path=file_record.path,
            language=file_record.language,
            success=False,
            errors=[f"Visitor exception: {exc}"],
        )