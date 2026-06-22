# Neodym Lead Discovery & Qualification Agent

AI-powered lead discovery and qualification system for identifying US-based companies that could benefit from Neodym's AI consulting, automation, and product development services.

## Goal

This project is not a generic lead scraper. It is designed to produce actionable outreach intelligence: which companies Neodym should contact, why they are a fit, what pain points likely exist, what AI opportunity Neodym could offer, and who to contact where public information is available.

## Current Status

Implemented so far:

- Python CLI project scaffold with `uv`, Typer, pytest, and ruff.
- Pydantic data models for raw candidates, enriched companies, scoring evidence, and final qualified leads.
- SQLite storage for candidates, pipeline runs, and future qualified leads.
- Manual CSV/Apollo-export import via `lead-discovery discover --csv/--apollo-csv`.
- Automated Apollo API company discovery via `lead-discovery discover --apollo-api` or by setting `APOLLO_API_KEY` and running `discover` with no CSV.
- Deterministic company/domain normalization and candidate upsert deduplication.
- Reusable public website, careers/job-signal, and contact-candidate extraction helpers.
- Tests for the implemented behavior.

Still pending:

- Wiring website/careers/contact enrichment into the `enrich` CLI command.
- AI/Codex reasoning export/import.
- Deterministic fit scoring.
- `lead_list.json` and `lead_report.md` generation.
- Evaluation and weekly digest commands.

## Setup

```bash
cd /home/ahmedraza/projects/neodym-lead-discovery-agent
uv sync --extra dev
```

Copy environment template if you want local env-file based configuration:

```bash
cp .env.example .env
```

For automated Apollo discovery, set:

```bash
export APOLLO_API_KEY="your_apollo_api_key"
```

## Current Discovery Usage

### Automated Apollo API discovery

With `APOLLO_API_KEY` set, this discovers companies directly from Apollo and writes them to SQLite:

```bash
uv run lead-discovery discover \
  --apollo-api \
  --max-results 50 \
  --db data/lead_discovery.sqlite
```

If `APOLLO_API_KEY` is set and no CSV is provided, Apollo API discovery is the default:

```bash
uv run lead-discovery discover --db data/lead_discovery.sqlite
```

Default Apollo filters target US organizations in Neodym-relevant categories such as healthcare, legal services, logistics, insurance, recruiting, professional services, and software, with operational/automation keywords.

You can override filters:

```bash
uv run lead-discovery discover \
  --apollo-api \
  --location "United States" \
  --industry "logistics" \
  --industry "insurance" \
  --keyword "workflow automation" \
  --keyword "customer support" \
  --max-results 50 \
  --db data/lead_discovery.sqlite
```

### Manual CSV/Apollo export import

```bash
uv run lead-discovery discover \
  --apollo-csv data/seeds/apollo-export.csv \
  --db data/lead_discovery.sqlite \
  --source apollo_export
```

## Inspect Imported Candidates

```bash
python3 - <<'PY'
import json, sqlite3

conn = sqlite3.connect("data/lead_discovery.sqlite")
conn.row_factory = sqlite3.Row

print("candidate_count=", conn.execute("select count(*) from candidates").fetchone()[0])
for row in conn.execute("select id, normalized_name, normalized_domain, payload_json from candidates order by id limit 20"):
    payload = json.loads(row["payload_json"])
    print(row["id"], payload["company_name"], payload.get("website"), payload.get("industry"), payload.get("location"))
PY
```

## Planned Architecture

The implementation plan in `docs/plans/2026-06-22-lead-discovery-agent.md` proposes a local-first Python CLI pipeline:

1. Ingest companies from Apollo API, CSV exports, and public/free web sources.
2. Normalize and deduplicate lead candidates.
3. Enrich companies from websites, search snippets, job pages, and public metadata.
4. Run AI-assisted analysis through a provider abstraction that supports approved local/Hermes/Codex workflows now and production LLM APIs later.
5. Score leads with an explainable rubric.
6. Generate JSON and Markdown reports.
7. Evaluate output quality and optionally send a weekly internal digest.

## Repository Contents

- `docs/extracted-specification.md` — searchable text extracted from the provided DOCX project statement.
- `docs/plans/2026-06-22-lead-discovery-agent.md` — detailed end-to-end implementation plan.
- `src/neodym_lead_discovery/discovery/apollo_api.py` — Apollo API discovery adapter.
- `src/neodym_lead_discovery/discovery/csv_importer.py` — CSV/Apollo-export importer.
- `src/neodym_lead_discovery/storage.py` — SQLite persistence.
- `tests/` — automated verification suite.

## Verification

```bash
uv run ruff check .
uv run pytest -q
```
