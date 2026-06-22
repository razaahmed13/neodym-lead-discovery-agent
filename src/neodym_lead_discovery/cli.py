from __future__ import annotations

import os
from pathlib import Path
from typing import Annotated

import typer

from neodym_lead_discovery import __version__
from neodym_lead_discovery.discovery.apollo_api import (
    DEFAULT_APOLLO_INDUSTRIES,
    DEFAULT_APOLLO_KEYWORDS,
    DEFAULT_APOLLO_LOCATIONS,
    ApolloApiError,
    ApolloClient,
    discover_from_apollo,
)
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
    use_apollo_api: Annotated[
        bool,
        typer.Option(
            "--apollo-api",
            help="Discover companies directly from Apollo API using APOLLO_API_KEY.",
        ),
    ] = False,
    db_path: Annotated[
        Path,
        typer.Option("--db", help="SQLite database path."),
    ] = Path("data/lead_discovery.sqlite"),
    source: Annotated[str, typer.Option("--source", help="Discovery source label.")] = "csv",
    max_results: Annotated[
        int,
        typer.Option("--max-results", min=1, help="Maximum Apollo API companies to import."),
    ] = 50,
    per_page: Annotated[
        int,
        typer.Option("--per-page", min=1, max=100, help="Apollo API page size."),
    ] = 25,
    locations: Annotated[
        list[str] | None,
        typer.Option("--location", help="Apollo organization location filter. Repeatable."),
    ] = None,
    industries: Annotated[
        list[str] | None,
        typer.Option("--industry", help="Apollo industry/keyword tag filter. Repeatable."),
    ] = None,
    keywords: Annotated[
        list[str] | None,
        typer.Option("--keyword", help="Apollo organization keyword filter. Repeatable."),
    ] = None,
) -> None:
    """Import or discover raw lead candidates."""
    storage = LeadStorage(db_path)
    storage.initialize()

    apollo_api_key = os.getenv("APOLLO_API_KEY", "").strip()
    should_use_apollo_api = use_apollo_api or (csv_path is None and bool(apollo_api_key))

    if csv_path is not None:
        candidates = import_csv(csv_path, discovery_source=source)
    elif should_use_apollo_api:
        if not apollo_api_key:
            typer.echo("APOLLO_API_KEY is required for --apollo-api discovery.", err=True)
            raise typer.Exit(code=2)
        try:
            candidates = discover_from_apollo(
                client=ApolloClient(api_key=apollo_api_key),
                max_results=max_results,
                per_page=per_page,
                locations=locations or DEFAULT_APOLLO_LOCATIONS.copy(),
                industries=industries or DEFAULT_APOLLO_INDUSTRIES.copy(),
                keywords=keywords or DEFAULT_APOLLO_KEYWORDS.copy(),
            )
        except ApolloApiError as exc:
            typer.echo(str(exc), err=True)
            raise typer.Exit(code=1) from exc
    else:
        typer.echo(
            "No discovery source provided. Set APOLLO_API_KEY to automate Apollo API discovery "
            "or pass --csv/--apollo-csv for a manual import.",
            err=True,
        )
        raise typer.Exit(code=2)

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
