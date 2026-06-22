from __future__ import annotations

from pathlib import Path
from typing import Annotated

import typer

from neodym_lead_discovery import __version__
from neodym_lead_discovery.discovery.csv_importer import import_csv
from neodym_lead_discovery.storage import LeadStorage

app = typer.Typer(
    help="Discover, enrich, analyze, score, report, and evaluate Neodym lead opportunities.",
    no_args_is_help=True,
)


def _version_callback(value: bool) -> None:
    if value:
        typer.echo(f"neodym-lead-discovery-agent {__version__}")
        raise typer.Exit()


@app.callback()
def main(
    version: bool = typer.Option(
        False,
        "--version",
        callback=_version_callback,
        is_eager=True,
        help="Print package version and exit.",
    ),
) -> None:
    """Lead discovery pipeline command group."""


@app.command()
def discover(
    csv_path: Annotated[
        Path | None,
        typer.Option(
            "--csv",
            "--apollo-csv",
            exists=True,
            readable=True,
            help="Path to an Apollo/user CSV export to import.",
        ),
    ] = None,
    db_path: Annotated[
        Path,
        typer.Option("--db", help="SQLite database path."),
    ] = Path("data/lead_discovery.sqlite"),
    source: Annotated[str, typer.Option("--source", help="Discovery source label.")] = "csv",
) -> None:
    """Import or discover raw lead candidates."""
    if csv_path is None:
        typer.echo("No discovery source provided. Pass --csv or --apollo-csv.", err=True)
        raise typer.Exit(code=2)
    storage = LeadStorage(db_path)
    storage.initialize()
    candidates = import_csv(csv_path, discovery_source=source)
    imported_ids = [storage.upsert_candidate(candidate) for candidate in candidates]
    typer.echo(f"Imported {len(imported_ids)} lead candidates into {db_path}")


@app.command()
def enrich() -> None:
    """Enrich lead candidates from public sources."""
    typer.echo("enrich: not implemented yet")


@app.command()
def analyze() -> None:
    """Export/import Codex CLI reasoning batches."""
    typer.echo("analyze: not implemented yet")


@app.command()
def score() -> None:
    """Calculate deterministic fit scores from criterion statuses."""
    typer.echo("score: not implemented yet")


@app.command()
def report() -> None:
    """Generate JSON and Markdown lead reports."""
    typer.echo("report: not implemented yet")


@app.command()
def evaluate() -> None:
    """Evaluate generated outputs for schema, duplicates, scoring, and grounding."""
    typer.echo("evaluate: not implemented yet")


@app.command()
def digest() -> None:
    """Render the weekly top-lead digest."""
    typer.echo("digest: not implemented yet")


@app.command("run-all")
def run_all() -> None:
    """Run the full local pipeline end to end."""
    typer.echo("run-all: not implemented yet")


if __name__ == "__main__":
    app()
