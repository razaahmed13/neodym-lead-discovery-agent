from __future__ import annotations

import json
import os
import subprocess
import sys
from pathlib import Path
from time import sleep
from typing import Annotated

import typer

from neodym_lead_discovery import __version__
from neodym_lead_discovery.discovery.apollo_api import (
    DEFAULT_APOLLO_INDUSTRIES,
    DEFAULT_APOLLO_KEYWORDS,
    DEFAULT_APOLLO_LOCATIONS,
    DEFAULT_MAX_EMPLOYEES,
    DEFAULT_MIN_EMPLOYEES,
    ApolloApiError,
    ApolloClient,
    discover_from_apollo,
)
from neodym_lead_discovery.discovery.csv_importer import import_csv
from neodym_lead_discovery.storage import LeadStorage
from neodym_lead_discovery.website_context import (
    DEFAULT_MAX_CHARS,
    WebsiteContextError,
    fetch_website_context,
    write_website_context,
)
from neodym_lead_discovery.website_reader import (
    DEFAULT_READER_MODEL,
    DEFAULT_READER_TIMEOUT_SECONDS,
    ReaderError,
    extract_reader_facts,
)

app = typer.Typer(
    help="Discover, analyze, score, report, and evaluate Neodym lead opportunities.",
    no_args_is_help=True,
)

DEFAULT_DB_PATH = Path("data/lead_discovery.sqlite")
DEFAULT_READER_DELAY_SECONDS = 5.0
DEFAULT_READER_RETRIES = 3
DEFAULT_READER_RETRY_DELAY_SECONDS = 60.0


def _env_value(name: str, dotenv_path: Path = Path(".env")) -> str:
    """Read an env var, falling back to a local .env file without exporting secrets."""
    value = os.getenv(name, "").strip()
    if value:
        return value
    if not dotenv_path.exists():
        return ""
    for line in dotenv_path.read_text().splitlines():
        stripped = line.strip()
        if not stripped or stripped.startswith("#") or "=" not in stripped:
            continue
        key, raw_value = stripped.split("=", 1)
        if key.strip() != name:
            continue
        return _clean_dotenv_value(raw_value)
    return ""


def _clean_dotenv_value(raw_value: str) -> str:
    value = raw_value.strip()
    if " #" in value:
        value = value.split(" #", 1)[0].strip()
    if len(value) >= 2 and value[0] == value[-1] and value[0] in {"'", '"'}:
        value = value[1:-1]
    return value.strip()


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
        typer.Option(
            "--db",
            help="SQLite database path. Defaults to the shared project database.",
        ),
    ] = DEFAULT_DB_PATH,
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
    min_employees: Annotated[
        int | None,
        typer.Option("--min-employees", min=1, help="Minimum company employee count."),
    ] = DEFAULT_MIN_EMPLOYEES,
    max_employees: Annotated[
        int | None,
        typer.Option("--max-employees", min=1, help="Maximum company employee count."),
    ] = DEFAULT_MAX_EMPLOYEES,
) -> None:
    """Import or discover raw lead candidates."""
    storage = LeadStorage(db_path)
    storage.initialize()

    apollo_api_key = _env_value("APOLLO_API_KEY")
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
                min_employees=min_employees,
                max_employees=max_employees,
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


@app.command("enrich-websites")
def enrich_websites(
    db_path: Annotated[
        Path,
        typer.Option(
            "--db",
            help="SQLite database path containing discovered candidates.",
        ),
    ] = DEFAULT_DB_PATH,
    limit: Annotated[
        int | None,
        typer.Option("--limit", min=1, help="Maximum number of candidates to enrich."),
    ] = None,
    max_chars: Annotated[
        int | None,
        typer.Option(
            "--max-chars",
            min=500,
            help=(
                "Optional maximum characters to keep from extracted visible page text. "
                "By default, no truncation is applied."
            ),
        ),
    ] = DEFAULT_MAX_CHARS,
    reader_model: Annotated[
        str,
        typer.Option("--reader-model", help="Codex CLI model for the Reader extraction step."),
    ] = DEFAULT_READER_MODEL,
    reader_timeout_seconds: Annotated[
        int,
        typer.Option(
            "--reader-timeout-seconds",
            min=1,
            help="Seconds before a single Codex Reader call is killed and retried/skipped.",
        ),
    ] = DEFAULT_READER_TIMEOUT_SECONDS,
    reader_delay_seconds: Annotated[
        float,
        typer.Option(
            "--reader-delay-seconds",
            min=0,
            help="Seconds to pause between Codex Reader calls.",
        ),
    ] = DEFAULT_READER_DELAY_SECONDS,
    reader_retries: Annotated[
        int,
        typer.Option(
            "--reader-retries",
            min=0,
            help="Retry count for transient Codex Reader failures such as timeouts.",
        ),
    ] = DEFAULT_READER_RETRIES,
    reader_retry_delay_seconds: Annotated[
        float,
        typer.Option(
            "--reader-retry-delay-seconds",
            min=0,
            help="Seconds to wait before retrying transient Codex Reader failures.",
        ),
    ] = DEFAULT_READER_RETRY_DELAY_SECONDS,
) -> None:
    """Fetch candidate websites, run Reader extraction, and save structured facts only."""
    storage = LeadStorage(db_path)
    storage.initialize()
    run_id = storage.start_run(
        stage="enrich_websites",
        metadata={
            "limit": limit,
            "reader_model": reader_model,
            "reader_timeout_seconds": reader_timeout_seconds,
            "reader_delay_seconds": reader_delay_seconds,
            "reader_retries": reader_retries,
            "reader_retry_delay_seconds": reader_retry_delay_seconds,
        },
    )
    enriched_count = 0
    skipped_count = 0
    failed_count = 0
    candidate_rows = storage.list_candidates(limit=limit)

    for index, (candidate_id, candidate) in enumerate(candidate_rows):
        if not candidate.website:
            skipped_count += 1
            continue
        try:
            # Keep raw website context in memory only. Do not write it to disk or SQLite.
            website_context, page_count = fetch_website_context(
                candidate.website,
                max_chars=max_chars,
            )
            reader_facts = _extract_reader_facts_with_retries(
                website_context,
                model=reader_model,
                timeout_seconds=reader_timeout_seconds,
                retries=reader_retries,
                retry_delay_seconds=reader_retry_delay_seconds,
            )
            storage.save_candidate_website_facts(
                candidate_id=candidate_id,
                candidate=candidate,
                facts=reader_facts,
                page_count=page_count,
            )
            enriched_count += 1
        except (WebsiteContextError, ReaderError) as exc:
            failed_count += 1
            typer.echo(f"Failed to enrich {candidate.company_name}: {exc}", err=True)
        if reader_delay_seconds > 0 and index < len(candidate_rows) - 1:
            sleep(reader_delay_seconds)

    status = "completed" if failed_count == 0 else "completed_with_errors"
    storage.finish_run(
        run_id,
        status=status,
        metadata={
            "enriched_count": enriched_count,
            "skipped_count": skipped_count,
            "failed_count": failed_count,
        },
    )
    typer.echo(
        f"Enriched {enriched_count} candidate website(s); "
        f"skipped {skipped_count}; failed {failed_count}."
    )


def _extract_reader_facts_with_retries(
    website_context: str,
    *,
    model: str,
    timeout_seconds: int,
    retries: int,
    retry_delay_seconds: float,
) -> dict[str, object]:
    attempt = 0
    while True:
        try:
            return extract_reader_facts(
                website_context,
                model=model,
                timeout_seconds=timeout_seconds,
            )
        except ReaderError as exc:
            if attempt >= retries or not _is_retryable_reader_error(exc):
                raise
            attempt += 1
            typer.echo(
                f"Reader hit a transient Codex error; retrying in "
                f"{retry_delay_seconds:g}s ({attempt}/{retries}).",
                err=True,
            )
            if retry_delay_seconds > 0:
                sleep(retry_delay_seconds)


def _is_retryable_reader_error(exc: ReaderError) -> bool:
    message = str(exc).lower()
    retryable_markers = (
        "http 429",
        "http 500",
        "http 502",
        "http 503",
        "http 504",
        "rate limit",
        "timeout",
        "timed out",
        "temporarily unavailable",
        "exit code 124",
    )
    return any(marker in message for marker in retryable_markers)


@app.command("fetch-website")
def fetch_website(
    url: Annotated[str, typer.Argument(help="Website URL to fetch and prune for LLM context.")],
    output_path: Annotated[
        Path,
        typer.Option(
            "--output",
            "-o",
            help="Markdown file where the extracted website context will be written.",
        ),
    ],
    max_chars: Annotated[
        int | None,
        typer.Option(
            "--max-chars",
            min=500,
            help=(
                "Optional maximum characters to keep from extracted visible page text. "
                "By default, no truncation is applied."
            ),
        ),
    ] = DEFAULT_MAX_CHARS,
    reader_output_path: Annotated[
        Path | None,
        typer.Option(
            "--reader-output",
            help="JSON file where the cheap Reader LLM fact sheet will be written.",
        ),
    ] = None,
    reader_model: Annotated[
        str,
        typer.Option("--reader-model", help="Codex CLI model for the Reader extraction step."),
    ] = DEFAULT_READER_MODEL,
    reader_timeout_seconds: Annotated[
        int,
        typer.Option(
            "--reader-timeout-seconds",
            min=1,
            help="Seconds before the Codex Reader call is killed.",
        ),
    ] = DEFAULT_READER_TIMEOUT_SECONDS,
) -> None:
    """Fetch one website and write visible-text Markdown context."""
    try:
        written_path, page_count = write_website_context(
            url=url,
            output_path=output_path,
            max_chars=max_chars,
        )
    except WebsiteContextError as exc:
        typer.echo(str(exc), err=True)
        raise typer.Exit(code=1) from exc
    typer.echo(f"Wrote website context from {page_count} page(s) to {written_path}")

    if reader_output_path is None:
        return

    try:
        reader_facts = extract_reader_facts(
            written_path.read_text(),
            model=reader_model,
            timeout_seconds=reader_timeout_seconds,
        )
    except ReaderError as exc:
        typer.echo(str(exc), err=True)
        raise typer.Exit(code=1) from exc

    reader_output_path.parent.mkdir(parents=True, exist_ok=True)
    reader_output_path.write_text(json.dumps(reader_facts, indent=2) + "\n")
    typer.echo(f"Wrote reader fact sheet to {reader_output_path}")


@app.command()
def analyze() -> None:
    """Export/import reasoning batches."""
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


@app.command()
def ui(
    db_path: Annotated[
        Path,
        typer.Option(
            "--db",
            help="SQLite database path to inspect in the local UI.",
        ),
    ] = DEFAULT_DB_PATH,
    port: Annotated[
        int,
        typer.Option("--port", min=1, max=65535, help="Local UI server port."),
    ] = 8501,
) -> None:
    """Launch the local dashboard for discovered candidates."""
    env = os.environ.copy()
    env["LEAD_DISCOVERY_DB"] = str(db_path)
    typer.echo(f"Starting Lead Discovery UI for {db_path} on http://localhost:{port}")
    subprocess.run(
        [
            sys.executable,
            "-m",
            "neodym_lead_discovery.ui",
            "--db",
            str(db_path),
            "--port",
            str(port),
        ],
        env=env,
        check=True,
    )


@app.command("run-all")
def run_all() -> None:
    """Run the full local pipeline end to end."""
    typer.echo("run-all: not implemented yet")


if __name__ == "__main__":
    app()
