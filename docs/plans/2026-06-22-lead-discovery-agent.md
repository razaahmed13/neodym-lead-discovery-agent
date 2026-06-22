# Lead Discovery & Qualification Agent Implementation Plan

> **For Hermes:** Use subagent-driven-development skill to implement this plan task-by-task.

**Goal:** Build a local-first AI-assisted system that discovers, enriches, scores, and reports US-based company leads that are genuinely relevant for Neodym's AI consulting, automation, and product development services.

**Architecture:** Use a Python CLI pipeline with clear stages: candidate ingestion, normalization, enrichment, AI analysis, scoring, reporting, evaluation, and optional weekly digest delivery. Keep data-source adapters and AI-provider adapters modular so the MVP can operate with approved tooling/free tiers now while remaining ready for future production LLM APIs.

**Tech Stack:** Python 3.11+, `uv`, Typer CLI, Pydantic models, SQLite for local persistence/cache, pytest, ruff, httpx/BeautifulSoup for public web enrichment, optional Playwright later for dynamic pages, provider interface for Hermes/Codex/manual JSON now and OpenAI-compatible APIs later.

---

## 1. Understanding of the Project Statement

### Product objective

Neodym needs an AI-powered lead discovery and qualification system that finds companies where AI could create measurable business value. The output must help Neodym decide:

- Which companies should be contacted.
- Why each company is a good fit.
- What likely pain point Neodym can solve.
- What AI opportunity should be pitched.
- Who the likely decision-maker is, where public information is available.

### Target lead profile

US-based organizations that may benefit from:

- Workflow automation.
- AI-powered internal tools.
- AI agents.
- Customer support automation.
- Document processing.
- Knowledge retrieval systems.
- Operational efficiency improvements.
- Custom AI products.

Promising verticals include healthcare, legal, small businesses without strong web presence, logistics, insurance, recruiting, professional services, SMB software companies, and growing technology companies.

### Required outputs

- `lead_list.json` with at least: company, website, industry, contact, fit score, reason, pain point, opportunity, source links.
- `lead_report.md` ranked with the highest-quality opportunities first.
- README covering setup, architecture, data sources, scoring methodology, AI usage, limitations, and future improvements.
- Agent usage log covering AI tools used, how they were used, manually verified items, problems, and lessons learned.
- Evaluation documentation and runnable checks for schema validity, duplicate detection, lead scoring consistency, and source grounding.

### Important product constraint

Lead quality matters more than quantity. The system must demonstrate the ability to identify and evaluate at least 50 potential leads, but ten highly qualified opportunities are more valuable than fifty mediocre ones.

---

## 2. MVP Scope, Non-Scope, and Feasibility Decisions

### In scope for MVP

- Local CLI application that can run from the terminal.
- CSV/manual seed input plus at least one public/free discovery source.
- Local SQLite cache for repeatable runs and source-grounding metadata.
- Deterministic normalization and duplicate detection.
- Public website/job-page/search-result enrichment.
- AI-assisted analysis through an adapter that can use approved local workflows now.
- Explainable scoring rubric producing 1-10 fit scores.
- `lead_list.json` and `lead_report.md` generation.
- Evaluations runnable with `pytest` and a CLI command.
- Example generated output for 50 evaluated leads.
- Optional weekly digest command that renders top 10 leads and can later be wired to email.

### Out of scope for MVP

- Paid scraping APIs as a required dependency.
- Unapproved personal LLM API keys.
- Full CRM integration.
- Automated cold email sending.
- Aggressive scraping of LinkedIn or sites that prohibit automated scraping.
- Production web dashboard.
- Fully automated contact email discovery when sources do not make emails public.

### Feasibility decisions

- Use public/free data and CSV imports first; Apollo exports can be supported as an input format without requiring Apollo API access.
- Use a provider abstraction for AI analysis. The MVP can support a `manual-json`/approved-tooling workflow and later add OpenAI-compatible API clients when production LLM access exists.
- Store source links and evidence snippets with every lead so scores can be audited.
- Prefer fewer, higher-confidence leads over large unverified lists.
- Avoid violating terms of service; LinkedIn should be represented by manual/export input or user-provided public information, not brittle scraping.

---

## 3. Proposed Repository Structure

```text
neodym-lead-discovery-agent/
  README.md
  pyproject.toml
  .env.example
  docs/
    extracted-specification.md
    scoring-methodology.md
    data-sources.md
    ai-usage-log.md
    evaluation.md
    limitations.md
    plans/
      2026-06-22-lead-discovery-agent.md
  src/
    neodym_lead_discovery/
      __init__.py
      cli.py
      config.py
      models.py
      storage.py
      discovery/
        __init__.py
        base.py
        csv_importer.py
        directory_seed.py
        search_seed.py
      enrichment/
        __init__.py
        website.py
        jobs.py
        contacts.py
      ai/
        __init__.py
        base.py
        heuristic.py
        manual_json.py
        prompts.py
      scoring/
        __init__.py
        rubric.py
      reporting/
        __init__.py
        json_report.py
        markdown_report.py
        weekly_digest.py
      evaluation/
        __init__.py
        checks.py
  tests/
    fixtures/
    test_models.py
    test_csv_importer.py
    test_dedupe.py
    test_scoring.py
    test_reporting.py
    test_evaluation.py
  data/
    seeds/
      sample_companies.csv
  outputs/
    .gitkeep
```

---

## 4. Data Model

### Lead candidate

Fields:

- `company_name`: string.
- `website`: optional URL.
- `industry`: optional string.
- `location`: optional string.
- `description`: optional string.
- `company_size`: optional string.
- `source_links`: list of URLs.
- `raw_sources`: list of evidence snippets.
- `discovery_source`: enum such as `csv`, `directory`, `search`, `apollo_export`, `jobs`.

### Enriched company

Additional fields:

- `website_title`.
- `website_summary`.
- `services_or_products`.
- `job_signals`.
- `growth_signals`.
- `operational_complexity_signals`.
- `contact_candidates`.

### Qualified lead

Required output fields:

- `company`.
- `website`.
- `industry`.
- `contact`.
- `fit_score`.
- `reason`.
- `pain_point`.
- `opportunity`.
- `source_links`.

Additional recommended audit fields:

- `score_breakdown`.
- `confidence`.
- `evidence`.
- `limitations`.
- `generated_at`.

---

## 5. Explainable Scoring Methodology

Use a 10-point rubric with sub-scores normalized into a final `fit_score`:

| Factor | Weight | Signals |
| --- | ---: | --- |
| Industry relevance | 20% | Healthcare, legal, logistics, insurance, recruiting, professional services, SMB software, growing tech |
| Operational complexity | 20% | Multi-step workflows, dispatch, claims, intake, support, documents, scheduling, compliance |
| AI opportunity clarity | 25% | Clear customer support, document processing, internal copilot, knowledge retrieval, sales/CRM, or automation use case |
| Growth/hiring/activity signals | 15% | Hiring pages, new roles, expansion language, active news/blog updates |
| Company size / buyer fit | 10% | Large enough to pay for services but likely not fully saturated with in-house AI teams |
| Source quality and confidence | 10% | Grounded website/source evidence, multiple corroborating links, current public data |

Scoring rules:

- 9-10: Strong immediate outreach candidate with clear pain, clear AI opportunity, and strong source evidence.
- 7-8.9: Good fit with plausible opportunity and adequate evidence.
- 5-6.9: Possible fit but weaker evidence or less urgent pain.
- 1-4.9: Low fit, poor evidence, irrelevant industry, or unclear business value.

---

## 6. Device Access and Automation Strategy

The system cannot magically read private laptops, private Apollo accounts, LinkedIn sessions, or team machines. MVP access paths must be explicit:

1. **Local CLI input:** users place CSV exports in `data/seeds/` or pass a path via CLI.
2. **Public web fetches:** the app fetches public company websites and public pages only.
3. **Approved AI tooling:** AI analysis runs through a pluggable adapter. Local/approved workflows are documented; production API integration is a later adapter.
4. **Weekly digest:** initially a local command that generates Markdown/email body. Actual email sending is optional and requires explicit SMTP/provider configuration.

---

## 7. Implementation Tasks

### Task 1: Initialize Python project metadata

**Objective:** Add minimal project configuration and developer tooling.

**Files:**
- Create: `pyproject.toml`
- Create: `.env.example`

**Steps:**
1. Add project metadata with Python `>=3.11`, Typer, Pydantic, httpx, BeautifulSoup, pytest, ruff.
2. Configure ruff and pytest.
3. Add `.env.example` with placeholders for optional future providers only.
4. Run `uv sync`.
5. Run `uv run pytest` and expect zero tests collected or pass.
6. Commit: `chore: initialize python project`.

### Task 2: Create core package and CLI skeleton

**Objective:** Provide an executable CLI entrypoint.

**Files:**
- Create: `src/neodym_lead_discovery/__init__.py`
- Create: `src/neodym_lead_discovery/cli.py`
- Create: `tests/test_cli.py`

**Steps:**
1. Write a failing test for `--help` output using Typer's test runner.
2. Implement a Typer app with commands: `discover`, `enrich`, `analyze`, `score`, `report`, `evaluate`, `digest`, `run-all`.
3. Run the CLI help test and verify pass.
4. Commit: `feat: add cli skeleton`.

### Task 3: Define Pydantic data models

**Objective:** Create typed models for candidates, enrichment, contacts, scoring, and output leads.

**Files:**
- Create: `src/neodym_lead_discovery/models.py`
- Create: `tests/test_models.py`

**Steps:**
1. Write tests requiring `QualifiedLead` to serialize with the exact required output fields.
2. Add validators for `fit_score` range 1-10 and non-empty `source_links` for final leads.
3. Add models: `SourceEvidence`, `ContactCandidate`, `LeadCandidate`, `EnrichedCompany`, `ScoreBreakdown`, `QualifiedLead`.
4. Run model tests.
5. Commit: `feat: define lead data models`.

### Task 4: Add SQLite storage and run state

**Objective:** Persist candidates, enrichments, analyses, scores, and generated outputs locally.

**Files:**
- Create: `src/neodym_lead_discovery/storage.py`
- Create: `tests/test_storage.py`

**Steps:**
1. Write tests using a temporary SQLite file.
2. Implement schema creation for candidates, enriched companies, analyses, qualified leads, and source evidence.
3. Implement upsert by normalized company name + website.
4. Verify duplicate upsert does not create duplicate rows.
5. Commit: `feat: add sqlite storage`.

### Task 5: Implement CSV/Apollo export importer

**Objective:** Support user-provided CSV exports as the safest first data source.

**Files:**
- Create: `src/neodym_lead_discovery/discovery/base.py`
- Create: `src/neodym_lead_discovery/discovery/csv_importer.py`
- Create: `tests/fixtures/sample_companies.csv`
- Create: `tests/test_csv_importer.py`

**Steps:**
1. Write fixture CSV with varied headers: company, website, industry, location, description, linkedin/company URL.
2. Write tests for mapping common Apollo-like headers to `LeadCandidate`.
3. Implement header normalization and flexible field mapping.
4. Add CLI: `discover --csv path/to/file.csv`.
5. Verify imported candidates are saved.
6. Commit: `feat: import lead candidates from csv`.

### Task 6: Implement deterministic normalization and duplicate detection

**Objective:** Prevent duplicate leads across data sources.

**Files:**
- Create: `src/neodym_lead_discovery/discovery/dedupe.py`
- Create: `tests/test_dedupe.py`

**Steps:**
1. Test duplicate detection for name variants like `ABC Logistics LLC` vs `ABC Logistics` and URL variants like `https://www.example.com/` vs `example.com`.
2. Implement URL canonicalization, suffix cleanup, and normalized company keys.
3. Integrate with storage upsert.
4. Commit: `feat: add lead duplicate detection`.

### Task 7: Add public website enrichment

**Objective:** Fetch company website pages and extract basic business signals.

**Files:**
- Create: `src/neodym_lead_discovery/enrichment/website.py`
- Create: `tests/test_website_enrichment.py`

**Steps:**
1. Write tests with static HTML fixtures for title, meta description, headings, contact/about links.
2. Implement safe HTTP fetch with timeout, user-agent, redirect handling, and robots/ToS caution in docs.
3. Parse title, meta description, H1/H2 text, about/contact links, and page text snippet.
4. Save evidence snippets with source URL.
5. Commit: `feat: enrich leads from public websites`.

### Task 8: Add public job/careers signal enrichment

**Objective:** Detect growth and operational signals from careers pages when available.

**Files:**
- Create: `src/neodym_lead_discovery/enrichment/jobs.py`
- Create: `tests/test_jobs_enrichment.py`

**Steps:**
1. Test extraction from sample careers HTML with operations, support, engineering, data, and AI terms.
2. Discover likely careers URLs from homepage links and common paths (`/careers`, `/jobs`, `/work-with-us`).
3. Extract roles and map them to growth/activity signals.
4. Save source links and snippets.
5. Commit: `feat: detect hiring and growth signals`.

### Task 9: Add contact candidate identification

**Objective:** Identify likely public decision-maker roles without overclaiming unavailable contact data.

**Files:**
- Create: `src/neodym_lead_discovery/enrichment/contacts.py`
- Create: `tests/test_contacts.py`

**Steps:**
1. Test role prioritization: Founder, CEO, CTO, Head of Operations, VP Engineering, Director of Technology.
2. Extract names/roles only from public website text when available.
3. If no person is found, output a suggested role like `Head of Operations` rather than fabricating a person.
4. Keep emails only if they appear publicly in source text.
5. Commit: `feat: identify public contact candidates`.

### Task 10: Design AI analysis provider interface

**Objective:** Support meaningful AI reasoning while avoiding dependency on unavailable production API access.

**Files:**
- Create: `src/neodym_lead_discovery/ai/base.py`
- Create: `src/neodym_lead_discovery/ai/prompts.py`
- Create: `tests/test_ai_prompts.py`

**Steps:**
1. Define `AIAnalyzer` protocol returning structured analysis: pain point, opportunity, reason, confidence, evidence references.
2. Create prompt templates for opportunity detection, pain-point analysis, and score reasoning.
3. Write tests that prompts include source evidence and forbid unsupported claims.
4. Commit: `feat: define ai analysis interface`.

### Task 11: Implement heuristic fallback analyzer

**Objective:** Provide a deterministic baseline for tests and offline operation.

**Files:**
- Create: `src/neodym_lead_discovery/ai/heuristic.py`
- Create: `tests/test_heuristic_analyzer.py`

**Steps:**
1. Write tests mapping logistics signals to dispatch/workflow automation, legal signals to document workflows, support-heavy businesses to support automation.
2. Implement keyword/signal rules that produce structured analysis with confidence.
3. Document this as fallback, not replacement for AI-assisted reasoning.
4. Commit: `feat: add heuristic analysis fallback`.

### Task 12: Implement manual/approved-tooling JSON analyzer

**Objective:** Allow analysis produced by Hermes/Codex/approved tools to be imported and validated.

**Files:**
- Create: `src/neodym_lead_discovery/ai/manual_json.py`
- Create: `tests/test_manual_json_analyzer.py`

**Steps:**
1. Define JSON schema for batch analysis outputs.
2. Add CLI command to export analysis prompts for a batch of enriched companies.
3. Add CLI command to import completed analysis JSON.
4. Validate imported analysis against company IDs and source evidence IDs.
5. Commit: `feat: support approved-tooling ai analysis import`.

### Task 13: Implement explainable scoring rubric

**Objective:** Convert evidence and analysis into consistent fit scores.

**Files:**
- Create: `src/neodym_lead_discovery/scoring/rubric.py`
- Create: `tests/test_scoring.py`

**Steps:**
1. Write tests for score bands and weighted factors.
2. Implement sub-score calculation for industry, operational complexity, opportunity clarity, growth signals, company size, and source quality.
3. Generate score reason from top positive and negative factors.
4. Ensure final score is clamped to 1-10.
5. Commit: `feat: add explainable lead scoring`.

### Task 14: Generate `lead_list.json`

**Objective:** Produce the required structured output.

**Files:**
- Create: `src/neodym_lead_discovery/reporting/json_report.py`
- Create: `tests/test_json_report.py`

**Steps:**
1. Write tests verifying every lead includes company, website, industry, contact, fit score, reason, pain point, opportunity, source links.
2. Sort leads by fit score descending.
3. Write JSON to `outputs/lead_list.json` by default.
4. Commit: `feat: generate lead list json`.

### Task 15: Generate `lead_report.md`

**Objective:** Produce a human-readable ranked report for Neodym.

**Files:**
- Create: `src/neodym_lead_discovery/reporting/markdown_report.py`
- Create: `tests/test_markdown_report.py`

**Steps:**
1. Write tests for Markdown sections and ranking order.
2. Include summary stats, top opportunities, each lead's reason, pain point, opportunity, suggested contact, and source links.
3. Write report to `outputs/lead_report.md` by default.
4. Commit: `feat: generate markdown lead report`.

### Task 16: Add evaluation checks

**Objective:** Validate output quality as required by the project statement.

**Files:**
- Create: `src/neodym_lead_discovery/evaluation/checks.py`
- Create: `tests/test_evaluation.py`
- Create: `docs/evaluation.md`

**Steps:**
1. Implement schema validation for `lead_list.json`.
2. Implement duplicate detection across final leads.
3. Implement scoring consistency checks: score must match rubric bands and contain a non-empty reason.
4. Implement source grounding checks: every lead has at least one source link and evidence-backed reason.
5. Add CLI: `evaluate outputs/lead_list.json`.
6. Document commands and expected results.
7. Commit: `feat: add output evaluation checks`.

### Task 17: Add end-to-end `run-all` pipeline

**Objective:** Allow one command to produce outputs from seeds.

**Files:**
- Modify: `src/neodym_lead_discovery/cli.py`
- Create: `tests/test_run_all.py`

**Steps:**
1. Write integration test with small local fixtures.
2. Implement command: `run-all --csv data/seeds/sample_companies.csv --limit 50`.
3. Pipeline order: discover -> enrich -> analyze -> score -> report -> evaluate.
4. Verify outputs are created.
5. Commit: `feat: add end-to-end lead pipeline`.

### Task 18: Create seed data workflow for 50 evaluated leads

**Objective:** Demonstrate the system on at least 50 potential leads.

**Files:**
- Create: `data/seeds/README.md`
- Potentially create: `data/seeds/sample_companies.csv` with public/example seed companies if allowed.
- Generate: `outputs/lead_list.json`
- Generate: `outputs/lead_report.md`

**Steps:**
1. Decide seed source: user-provided CSV, public directory list, or curated public companies.
2. Run `run-all --limit 50`.
3. Inspect top 10 manually for obvious hallucinations or bad fits.
4. Run `evaluate` and fix failures.
5. Commit only generated outputs if they are intended as deliverables and contain no private/sensitive data.
6. Commit: `docs: add generated lead outputs` or `data: add sample lead outputs`.

### Task 19: Add weekly digest renderer

**Objective:** Create the weekly top-10 lead digest content.

**Files:**
- Create: `src/neodym_lead_discovery/reporting/weekly_digest.py`
- Create: `tests/test_weekly_digest.py`

**Steps:**
1. Write tests confirming digest includes top 10 leads and required fields.
2. Render Markdown/email body from `lead_list.json`.
3. Add CLI: `digest --input outputs/lead_list.json --output outputs/weekly_digest.md`.
4. Document future email-provider integration points.
5. Commit: `feat: render weekly lead digest`.

### Task 20: Optional email sending adapter

**Objective:** Send digest to internal Neodym address only when explicit SMTP/provider config exists.

**Files:**
- Create: `src/neodym_lead_discovery/reporting/email_sender.py`
- Create: `tests/test_email_sender.py`
- Modify: `.env.example`

**Steps:**
1. Add config variables for SMTP host, port, username, sender, recipient.
2. Require `--send` flag; default should only render the digest locally.
3. Add dry-run mode.
4. Test that no email sends without config.
5. Commit: `feat: add optional digest email sender`.

### Task 21: Complete documentation

**Objective:** Ensure README and docs satisfy project deliverables.

**Files:**
- Modify: `README.md`
- Create: `docs/scoring-methodology.md`
- Create: `docs/data-sources.md`
- Create: `docs/ai-usage-log.md`
- Create: `docs/limitations.md`

**Steps:**
1. Document setup with `uv sync` and CLI commands.
2. Document architecture and module responsibilities.
3. Document data sources and their limitations.
4. Document scoring methodology and examples.
5. Document AI usage: tools used, prompt design, where future API integrations fit.
6. Document limitations: free data quality, contact availability, source freshness, no aggressive scraping.
7. Commit: `docs: complete project documentation`.

### Task 22: Final verification and demo

**Objective:** Prove the project works from a clean checkout.

**Files:**
- No new files required unless fixes are found.

**Steps:**
1. Run `uv sync`.
2. Run `uv run pytest`.
3. Run `uv run ruff check .`.
4. Run the end-to-end pipeline against seed data.
5. Run evaluation checks.
6. Inspect `outputs/lead_report.md` manually.
7. Update `docs/ai-usage-log.md` with manual verification notes, problems encountered, and lessons learned.
8. Commit final fixes: `chore: verify lead discovery agent`.

---

## 8. Testing Strategy

- **Unit tests:** models, dedupe, CSV import, scoring, report rendering.
- **Integration tests:** end-to-end pipeline with local fixtures and no external network.
- **Network tests:** optional and marked separately; should not be required for CI.
- **Evaluation tests:** validate actual generated `lead_list.json` and `lead_report.md`.
- **Manual review:** inspect top leads for business relevance and unsupported claims.

---

## 9. Data Source Strategy

Recommended initial order:

1. User-provided CSV/Apollo export input.
2. Public company websites.
3. Public directories that permit browsing/access.
4. Public search results or manually curated seed lists.
5. Public careers/job pages.

Avoid:

- Scraping LinkedIn pages directly unless compliant and explicitly permitted.
- Treating guessed emails as contact information.
- Treating weak search snippets as high-confidence evidence.

---

## 10. AI Usage Strategy

AI must be used for meaningful reasoning, not simple scraping. The AI layer should support:

- Opportunity identification.
- Pain-point detection.
- Company analysis.
- Score reasoning.

Because production LLM API access is not currently available, the system should:

- Export structured prompts for approved AI tooling.
- Import validated AI-generated JSON.
- Keep a heuristic fallback for tests/offline use.
- Clearly mark where future OpenAI-compatible/provider integrations can be added.

---

## 11. Acceptance Criteria

The project is complete when:

- A fresh clone can install dependencies and run locally.
- At least 50 leads can be discovered/imported and evaluated.
- `outputs/lead_list.json` exists and passes schema/evaluation checks.
- `outputs/lead_report.md` ranks leads and explains business value clearly.
- Each lead has source links and does not rely on unsupported claims.
- README documents setup, architecture, sources, scoring, AI usage, limitations, and future improvements.
- Agent usage log documents AI tools used, manual verification, problems, and lessons learned.
- Tests and lint pass.

---

## 12. Future Improvements

- Production LLM API adapter with batch processing and cost controls.
- Browser-assisted enrichment for pages that require JavaScript, with compliance checks.
- CRM export/integration.
- Email deliverability and outreach sequence drafting.
- Dashboard for reviewing and approving leads.
- Human feedback loop to improve scoring weights.
- Scheduled weekly runs with digest delivery.
- More robust contact enrichment through approved data providers.
