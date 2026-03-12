"""Utility script for building and visualizing a code graph.

This used to be hard‑coded for the `codeAtlas` repository, but it can
now operate on *any* repository.  For most use cases the primary
interface is the `code-atlas` Typer CLI, but the standalone script is
handy for quick experiments or CI tasks.

Examples:

    python visualize.py https://github.com/org/repo            # full
pipeline
    python visualize.py test_repo_id --skip-ingest            # already
indexed
    python visualize.py /path/to/local/checkout               # local path

By default the generated HTML is written to `graph.html` but the
output filename is configurable via `--output`.
"""

from __future__ import annotations

import typer

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


def main(
    repo: str = typer.Argument(..., help="Git URL / local path to analyze, or an existing repo_id."),
    output: str = typer.Option(
        "graph.html",
        "--output",
        "-o",
        help="HTML file to write visualization to.",
    ),
    skip_ingest: bool = typer.Option(
        False,
        "--skip-ingest",
        help=(
            "Treat the `repo` argument as an existing repo_id and skip "
            "ingestion/parsing steps."
        ),
    ),
) -> None:
    """Build and visualize a dependency graph for **any** repository.

    The behaviour mirrors the former argparse-based script; the main
    change is that options are now defined with Typer, making the
    generated help text consistent with the rest of the project.
    """

    if skip_ingest:
        repo_id = repo
    else:
        if run_ingestion is None or run_parsing is None:
            typer.echo("code-atlas ingestion/parsing dependencies are not installed", err=True)
            raise typer.Exit(1)

        typer.echo("🛠 running ingestion...")
        manifest = run_ingestion(repo)
        repo_id = manifest.repo_id

        typer.echo("🛠 running parsing...")
        run_parsing(manifest)

    typer.echo(f"📦 building graph for '{repo_id}'...")
    graph = build_graph(repo_id)

    typer.echo("🔍 analyzing dead functions...")
    dead = find_dead_functions(graph)
    if dead:
        typer.echo(f"Dead functions ({len(dead)}):")
        for node in dead:
            data = graph.nodes[node]
            typer.echo(
                f"{data.get('name','?')} ({data.get('file','?')}:{data.get('start_line','?')})"
            )
    else:
        typer.echo("No dead functions detected.")

    typer.echo(f"🖼 generating visualization at {output}...")
    viz = GraphVisualizer(graph)
    viz.build_html(output)
    typer.echo("✅ Graph visualization generated.")


if __name__ == "__main__":
    typer.run(main)
