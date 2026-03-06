from __future__ import annotations

import logging
import sys as _sys
from collections import Counter
from typing import Optional

import typer
from rich.console import Console
from rich.logging import RichHandler
from rich.table import Table

console = Console()

app = typer.Typer(
    name="code-atlas",
    help=(
        "Structure-aware, graph-augmented codebase assistant.\n\n"
        "Pass a URL/path directly (runs ingest), or use a subcommand:\n\n"
        "  code-atlas https://github.com/org/repo\n"
        "  code-atlas ingest https://github.com/org/repo\n"
    ),
    add_completion=False,
    invoke_without_command=True,
    no_args_is_help=True,
)

def _setup_logging(verbose: bool) -> None:
    level = logging.DEBUG if verbose else logging.INFO
    logging.basicConfig(
        level=level,
        format="%(message)s",
        handlers=[RichHandler(console=console, rich_tracebacks=True, show_path=False)],
        force=True,
    )

def _print_manifest(manifest) -> None:
    console.rule("[bold green]Manifest Summary[/bold green]")
    table = Table(show_header=False, box=None, padding=(0, 2))
    table.add_column("Key",   style="dim")
    table.add_column("Value", style="bold")
    table.add_row("Repo ID",     manifest.repo_id)
    table.add_row("Source",      manifest.source)
    table.add_row("Source Type", manifest.source_type)
    table.add_row("Local Path",  manifest.local_path)
    table.add_row("Branch",      manifest.git_branch or "N/A")
    table.add_row("Commit",      manifest.git_commit or "N/A")
    table.add_row("Total Files", str(manifest.total_source_files))
    table.add_row("Total Lines", f"{manifest.total_lines:,}")
    table.add_row("New",         str(len([f for f in manifest.change_set if f.status == "new"])))
    table.add_row("Modified",    str(len([f for f in manifest.change_set if f.status == "modified"])))
    table.add_row("Unchanged",   str(len(manifest.unchanged_files)))
    table.add_row("Deleted",     str(len(manifest.deleted_files)))
    console.print(table)

    if manifest.language_breakdown:
        console.rule("[bold]Language Breakdown[/bold]")
        lang_table = Table("Language", "Files", box=None, padding=(0, 2))
        for lang, count in manifest.language_breakdown.items():
            lang_table.add_row(lang, str(count))
        console.print(lang_table)

    if manifest.change_set:
        console.rule(f"[bold yellow]Change Set ({len(manifest.change_set)} files)[/bold yellow]")
        for rec in manifest.change_set[:20]:
            color = "green" if rec.status == "new" else "yellow"
            console.print(f"  [{color}]{rec.status:10}[/{color}]  {rec.path}")
        if len(manifest.change_set) > 20:
            console.print(f"  ... and {len(manifest.change_set) - 20} more")
    else:
        console.print("\n[dim]No changes detected — manifest is up to date.[/dim]")


def _do_ingest(source: str, branch: Optional[str], force: bool, verbose: bool):
    from code_atlas.ingestion.pipeline import run_ingestion
    from code_atlas.ingestion.manifest_store import ManifestStore
    from code_atlas.core.config import MANIFESTS_DIR

    if force:
        import re, shutil
        slug = re.sub(r"[^\w\-]", "_", source)[:128]
        db = MANIFESTS_DIR / f"{slug}.db"
        console.print("[yellow]--force: deleting stored manifest snapshot[/yellow]")
        tmp = run_ingestion(source=source, branch=branch)
        actual_db = MANIFESTS_DIR / f"{tmp.repo_id}.db"
        if actual_db.exists():
            actual_db.unlink()
            console.print(f"[dim]Deleted {actual_db}[/dim]")

    manifest = run_ingestion(source=source, branch=branch)
    return manifest

@app.callback()
def _root_callback(ctx: typer.Context) -> None:
    pass

@app.command("ingest")
def cmd_ingest(
    source: str = typer.Argument(..., help="Git URL or local directory path."),
    branch: Optional[str] = typer.Option(None, "--branch", "-b", help="Git branch."),
    force: bool = typer.Option(False, "--force", "-f", help="Re-index all files, ignoring cache."),
    verbose: bool = typer.Option(False, "--verbose", "-v", help="Enable debug logging."),
) -> None:
    """Phase 1 — Ingest a repository and produce a file manifest."""
    _setup_logging(verbose)
    console.rule("[bold cyan]Code Atlas — Phase 1: Ingestion[/bold cyan]")

    try:
        manifest = _do_ingest(source, branch, force, verbose)
    except Exception as exc:
        console.print(f"[red]Ingestion failed:[/red] {exc}")
        if verbose:
            console.print_exception()
        raise typer.Exit(1)

    _print_manifest(manifest)
    console.rule()
    console.print(
        f"[bold green]✓ Phase 1 complete.[/bold green] "
        f"{len(manifest.change_set)} file(s) queued for Phase 2 (parsing)."
    )


@app.command("parse")
def cmd_parse(
    source: str = typer.Argument(..., help="Git URL or local directory path."),
    branch: Optional[str] = typer.Option(None, "--branch", "-b", help="Git branch."),
    force: bool = typer.Option(False, "--force", "-f", help="Re-index all files, ignoring cache."),
    verbose: bool = typer.Option(False, "--verbose", "-v", help="Enable debug logging."),
) -> None:
    _setup_logging(verbose)

    try:
        from code_atlas.parsing.pipeline import run_parsing
    except ImportError as exc:
        console.print(f"[red]Import error:[/red] {exc}")
        raise typer.Exit(1)

    console.rule("[bold cyan]Phase 1: Ingestion[/bold cyan]")
    try:
        manifest = _do_ingest(source, branch, force, verbose)
    except Exception as exc:
        console.print(f"[red]Ingestion failed:[/red] {exc}")
        if verbose:
            console.print_exception()
        raise typer.Exit(1)

    _print_manifest(manifest)

    if not manifest.change_set:
        console.print(
            "\n[dim]No changed files — Phase 2 skipped. "
            "Use --force to re-parse everything.[/dim]"
        )
        raise typer.Exit(0)

    console.rule("[bold cyan]Phase 2: Parsing & IR Extraction[/bold cyan]")
    try:
        report = run_parsing(manifest)
    except Exception as exc:
        console.print(f"[red]Parsing failed:[/red] {exc}")
        if verbose:
            console.print_exception()
        raise typer.Exit(1)

    console.rule("[bold green]Parsing Report[/bold green]")
    table = Table(show_header=False, box=None, padding=(0, 2))
    table.add_column("Key",   style="dim")
    table.add_column("Value", style="bold")
    table.add_row("Files parsed", str(len(report.results)))
    table.add_row("Total nodes",  str(report.total_nodes))
    table.add_row("Failed files", str(len(report.failed_files)))
    console.print(table)

    if report.failed_files:
        console.print("\n[yellow]Failed files:[/yellow]")
        for fp in report.failed_files[:10]:
            console.print(f"  [red]✗[/red] {fp}")

    kind_counts = Counter(n.kind for n in report.all_nodes)
    if kind_counts:
        console.rule("[bold]Node Breakdown[/bold]")
        kind_table = Table("Kind", "Count", box=None, padding=(0, 2))
        for kind, count in kind_counts.most_common():
            kind_table.add_row(kind, str(count))
        console.print(kind_table)

    console.rule()
    console.print(
        f"[bold green]✓ Phase 2 complete.[/bold green] "
        f"{report.total_nodes} IR nodes ready for graph construction (Phase 3)."
    )

def _patch_for_bare_url() -> None:
    import click

    original_parse = app.info_name  
    class _PatchedGroup(app.__class__):
        def parse_args(self, ctx, args):
            known = {c.name for c in self.commands.values()} if hasattr(self, 'commands') else set()
            if args and not args[0].startswith("-") and args[0] not in known:
                args = ["ingest"] + list(args)
            return super().parse_args(ctx, args)

    app.__class__ = _PatchedGroup

import click

_original_main = app

@click.group(invoke_without_command=True, no_args_is_help=False)
@click.argument("source", required=False)
@click.option("--branch", "-b", default=None)
@click.option("--force", "-f", is_flag=True, default=False)
@click.option("--verbose", "-v", is_flag=True, default=False)
@click.pass_context
def _bare_handler(ctx, source, branch, force, verbose):
    """Shorthand: code-atlas <url> runs ingest."""
    if ctx.invoked_subcommand is None and source is not None:
        ctx.invoke(
            ctx.parent.command.commands["ingest"] if ctx.parent else ctx.command,
        )

def main():
    args = _sys.argv[1:]

    known_cmds = {"ingest", "parse", "graph", "index", "search", "--help", "-h", "--version"}

    if args and not args[0].startswith("-") and args[0] not in known_cmds:
        _sys.argv = [_sys.argv[0], "ingest"] + args

    app()

if __name__ == "__main__":
    main()