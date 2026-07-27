import os
import pickle
import logging
import sys

from code_atlas.ingestion.pipeline import run_ingestion
from code_atlas.parsing.pipeline import run_parsing
from code_atlas.graph.builder import CodeGraphBuilder
from code_atlas.retrieval.build_index import build_index
from code_atlas.retrieval.load_graph import load_graph

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

        os.makedirs("/root/.code_atlas/graphs", exist_ok=True)

        with open(
            f"/root/.code_atlas/graphs/{parsed_manifest.repo_id}.pkl",
            "wb"
        ) as f:
            pickle.dump(graph, f)

        logger.info("Graph saved successfully.")

    else:
        try:
            graph = load_graph(parsed_manifest.repo_id)

        except FileNotFoundError:

            logger.warning(
                "No new files parsed and no existing graph found. Building graph from IR store."
            )

            builder = CodeGraphBuilder(parsed_manifest.repo_id)
            graph = builder.build()

            os.makedirs("/root/.code_atlas/graphs", exist_ok=True)

            with open(
                f"/root/.code_atlas/graphs/{parsed_manifest.repo_id}.pkl",
                "wb"
            ) as f:
                pickle.dump(graph, f)

            logger.info("Graph saved successfully.")

    if graph:
        build_index(parsed_manifest.repo_id, graph)
    else:
        build_index(parsed_manifest.repo_id)

    os.makedirs("/root/.code_atlas", exist_ok=True)

    with open("/root/.code_atlas/current_repo.txt", "w") as f:
        f.write(parsed_manifest.repo_id)

    logger.info(
        f"Current repository set to: {parsed_manifest.repo_id}"
    )

    logger.info("Pipeline completed successfully!")


if __name__ == "__main__":

    if len(sys.argv) < 2:
        raise ValueError(
            "Usage: python -m code_atlas.pipeline.main_pipeline <repo_path>"
        )

    repo_path = sys.argv[1]

    run_full_pipeline(repo_path)