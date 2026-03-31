from code_atlas.ingestion.pipeline import run_ingestion
from code_atlas.parsing.pipeline import run_parsing
from code_atlas.graph.builder import CodeGraphBuilder
from code_atlas.retrieval.build_index import build_index
from code_atlas.retrieval.load_graph import load_graph
import logging

logger = logging.getLogger(__name__)


def run_full_pipeline(repo_path: str):
    """
    Complete CodeAtlas pipeline:
    1. Ingestion
    2. Parsing
    3. Graph building
    4. Indexing
    """

    manifest = run_ingestion(repo_path)

    parsed_manifest = run_parsing(manifest)

    graph = None
    if getattr(parsed_manifest, "files_parsed", 0) > 0:
        builder = CodeGraphBuilder(parsed_manifest.repo_id)
        graph = builder.build()
    else:
        try:
            graph = load_graph(parsed_manifest.repo_id)
        except FileNotFoundError:
            logger.warning(
                "No new files parsed and no existing graph found. Graph will be empty."
            )

    if graph:
        build_index(parsed_manifest.repo_id, graph)
    else:
        build_index(parsed_manifest.repo_id)

    logger.info(" Pipeline completed successfully!")


if __name__ == "__main__":
    run_full_pipeline("/app_repo")