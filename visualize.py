"""Utility script for building and visualizing a code graph.

This used to be hard-coded for the `codeAtlas` repository, but it
can now operate on *any* repository. You may pass a Git URL or local
path and the script will ingest/parse the code before constructing
and visualizing the graph. Alternatively, if you already have a
`repo_id` from a previous run you can skip ingestion/parsing by using
`--skip-ingest`.

Usage examples:

    python visualize.py https://github.com/org/repo        # full pipeline
    python visualize.py test_repo_id --skip-ingest         # already indexed
    python visualize.py /path/to/local/checkout            # local path

By default the generated HTML is written to `graph.html` but the
output filename is configurable via `--output`.
"""

import argparse
import sys

from code_atlas.graph.pipeline import build_graph
from code_atlas.graph.visualiser import GraphVisualizer
from code_atlas.graph.deadcodeanalysis import find_dead_functions

# optional imports for ingestion/parsing phases
try:
    from code_atlas.ingestion.pipeline import run_ingestion
    from code_atlas.parsing.pipeline import run_parsing
except ImportError:
    run_ingestion = None  # type: ignore
    run_parsing = None  # type: ignore


def main():
    parser = argparse.ArgumentParser(
        description="Build and visualize a dependency graph for any repo."
    )
    parser.add_argument(
        "repo",
        help="Git URL / local path to analyze, or an existing repo_id."
    )
    parser.add_argument(
        "--output",
        "-o",
        default="graph.html",
        help="HTML file to write visualization to.",
    )
    parser.add_argument(
        "--skip-ingest",
        action="store_true",
        help=(
            "Treat the `repo` argument as an existing repo_id and skip "
            "ingestion/parsing steps."
        ),
    )
    args = parser.parse_args()

    if args.skip_ingest:
        repo_id = args.repo
    else:
        if run_ingestion is None or run_parsing is None:
            parser.error(
                "code-atlas ingestion/parsing dependencies are not installed"
            )

        print("🛠 running ingestion...")
        manifest = run_ingestion(args.repo)
        repo_id = manifest.repo_id

        print("🛠 running parsing...")
        run_parsing(manifest)

    print(f"📦 building graph for '{repo_id}'...")
    graph = build_graph(repo_id)

    print("🔍 analyzing dead functions...")
    dead = find_dead_functions(graph)
    if dead:
        print(f"Dead functions ({len(dead)}):")
        for node in dead:
            data = graph.nodes[node]
            print(
    f"{data.get('name','?')} ({data.get('file','?')}:{data.get('start_line','?')})"
)
    else:
        print("No dead functions detected.")

    print(f"🖼 generating visualization at {args.output}...")
    viz = GraphVisualizer(graph)
    viz.build_html(args.output)
    print("✅ Graph visualization generated.")


if __name__ == "__main__":
    main()