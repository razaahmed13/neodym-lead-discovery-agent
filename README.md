# Neodym Lead Discovery & Qualification Agent

AI-powered lead discovery and qualification system for identifying US-based companies that could benefit from Neodym's AI consulting, automation, and product development services.

## Goal

This project is not a generic lead scraper. It is designed to produce actionable outreach intelligence: which companies Neodym should contact, why they are a fit, what pain points likely exist, what AI opportunity Neodym could offer, and who to contact where public information is available.

## Current Status

Implemented so far:

- Python CLI project scaffold with `uv`, Typer, pytest, and ruff.
- Pydantic data models for raw discovery candidates, scoring evidence, and final qualified leads.
- SQLite storage for candidates, pipeline runs, and future qualified leads.
- Manual CSV/Apollo-export import via `lead-discovery discover --csv/--apollo-csv`.
- Automated Apollo API company discovery via `lead-discovery discover --apollo-api` or by setting `APOLLO_API_KEY` and running `discover` with no CSV.
- Deterministic company/domain normalization and candidate upsert deduplication.
- Local discovery dashboard showing fetched candidates.
- Tests for the implemented behavior.

Removed intentionally:

- The previous post-discovery website/careers/contact enrichment workflow.
- The `enrich` CLI command, enrichment package, enriched-company model/storage table, and enrichment dashboard sections.

Still pending:

- New post-discovery context-building approach.
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

Default Apollo filters target US organizations in Tier 1/Tier 2 workflow-automation markets: insurance, healthcare, medical practices, mental health, legal/law, staffing/recruiting, HR, logistics/supply chain, transportation/trucking/railroad, warehousing, facilities services, construction, real estate, financial services, accounting, consumer services, and automotive. Apollo industry values are post-filtered locally with accepted wording variations, so related tags such as `Hospitals and Health Care`, `Medical Practices`, `Truck Transportation`, `Warehousing and Storage`, and `Real Estate Agents and Brokers` are kept while noisy industries such as `Publishing` are rejected.

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

The original enrichment path has been discarded. The current committed foundation is intentionally limited to discovery, storage, UI inspection, scoring/reporting models, and placeholder downstream commands until the new post-discovery context-building approach is designed.

## Repository Contents

- `docs/extracted-specification.md` — searchable text extracted from the provided DOCX project statement.
- `src/neodym_lead_discovery/discovery/apollo_api.py` — Apollo API discovery adapter.
- `src/neodym_lead_discovery/discovery/csv_importer.py` — CSV/Apollo-export importer.
- `src/neodym_lead_discovery/storage.py` — SQLite persistence.
- `tests/` — automated verification suite.

## Verification

```bash
uv run ruff check .
uv run pytest -q
```
