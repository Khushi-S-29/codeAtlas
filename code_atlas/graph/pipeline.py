from __future__ import annotations

from rich.console import Console
from rich.table import Table
from rich import box

from code_atlas.graph.builder import CodeGraphBuilder
from code_atlas.graph.store import save_graph

console = Console()


def build_graph(repo_id: str):
    builder = CodeGraphBuilder(repo_id)

    with console.status("[bold cyan]Building dependency graph…[/bold cyan]"):
        graph = builder.build()

    stats = builder.stats()
    path  = save_graph(repo_id, graph)

    # ── summary table ──────────────────────────────────────────────
    console.rule("[bold green]Graph Summary[/bold green]")
    table = Table(show_header=False, box=box.SIMPLE, padding=(0, 2))
    table.add_column("Key",   style="dim")
    table.add_column("Value", style="bold cyan")
    table.add_row("Nodes",      str(stats["nodes"]))
    table.add_row("Edges",      str(stats["edges"]))
    table.add_row("Saved to",   str(path))
    console.print(table)

    return graph