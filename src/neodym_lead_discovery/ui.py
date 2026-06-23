# ruff: noqa: E501

from __future__ import annotations

import argparse
import html
import json
import os
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from typing import Any
from urllib.parse import urlparse

from neodym_lead_discovery.models import EnrichedCompany, LeadCandidate
from neodym_lead_discovery.storage import LeadStorage

DEFAULT_DB_ENV = "LEAD_DISCOVERY_DB"


def load_dashboard_data(db_path: str | Path) -> dict[str, Any]:
    """Load candidate/enrichment records and return UI-friendly summary data."""
    storage = LeadStorage(db_path)
    storage.initialize()
    candidates = storage.list_candidates()
    enriched_companies = storage.list_enriched_companies()
    enriched_domains = {
        (company.candidate.website or "").strip().lower() for company in enriched_companies
    }
    enriched_names = {company.candidate.company_name for company in enriched_companies}

    candidate_rows = [
        _candidate_row(candidate, enriched_domains=enriched_domains, enriched_names=enriched_names)
        for _, candidate in candidates
    ]
    enriched_rows = [_enriched_company_row(company) for company in enriched_companies]
    automation_opportunities = sum(len(row["automation_opportunities"]) for row in enriched_rows)
    manual_process_signals = sum(len(row["manual_process_signals"]) for row in enriched_rows)

    return {
        "metrics": {
            "candidates": len(candidate_rows),
            "enriched_companies": len(enriched_rows),
            "automation_opportunities": automation_opportunities,
            "manual_process_signals": manual_process_signals,
        },
        "candidates": candidate_rows,
        "enriched_companies": enriched_rows,
    }


def render_dashboard_html(db_path: str | Path) -> str:
    """Render a self-contained minimalist dashboard as HTML."""
    dashboard = load_dashboard_data(db_path)
    metrics = dashboard["metrics"]
    candidates = dashboard["candidates"]
    enriched = dashboard["enriched_companies"]
    return f"""<!doctype html>
<html lang="en">
<head>
  <meta charset="utf-8" />
  <meta name="viewport" content="width=device-width, initial-scale=1" />
  <title>Neodym Lead Discovery</title>
  <style>{_CSS}</style>
</head>
<body>
  <main class="shell">
    <section class="hero">
      <div>
        <p class="eyebrow">Neodym Lead Discovery Agent</p>
        <h1>Lead intelligence dashboard</h1>
        <p class="muted">Review fetched candidates, enriched companies, page evidence, manual process signals, and automation opportunities.</p>
      </div>
      <div class="db-pill">{_escape(str(db_path))}</div>
    </section>

    <section class="metrics">
      {_metric_card('Candidates', metrics['candidates'])}
      {_metric_card('Enriched', metrics['enriched_companies'])}
      {_metric_card('Automation opportunities', metrics['automation_opportunities'])}
      {_metric_card('Manual process signals', metrics['manual_process_signals'])}
    </section>

    <section class="panel">
      <div class="section-heading">
        <div>
          <p class="eyebrow">Discovery</p>
          <h2>Fetched candidates</h2>
        </div>
        <span class="count">{len(candidates)} total</span>
      </div>
      {_candidate_table(candidates)}
    </section>

    <section class="panel">
      <div class="section-heading">
        <div>
          <p class="eyebrow">Enrichment</p>
          <h2>Enriched companies</h2>
        </div>
        <span class="count">{len(enriched)} enriched</span>
      </div>
      {_company_cards(enriched)}
    </section>
  </main>
  <script>
    const search = document.createElement('input');
    search.placeholder = 'Filter companies, industries, signals...';
    search.className = 'search';
    document.querySelector('.shell').insertBefore(search, document.querySelector('.metrics'));
    search.addEventListener('input', () => {{
      const q = search.value.toLowerCase();
      document.querySelectorAll('[data-filter]').forEach((node) => {{
        node.style.display = node.dataset.filter.includes(q) ? '' : 'none';
      }});
    }});
  </script>
</body>
</html>"""


def serve_ui(db_path: str | Path, port: int = 8501) -> None:
    """Serve the dashboard with a tiny stdlib HTTP server."""
    resolved_db_path = Path(db_path)

    class Handler(BaseHTTPRequestHandler):
        def do_GET(self) -> None:  # noqa: N802 - stdlib method name
            parsed = urlparse(self.path)
            if parsed.path == "/api/data":
                _send_json(self, load_dashboard_data(resolved_db_path))
                return
            if parsed.path not in {"/", "/index.html"}:
                self.send_error(404)
                return
            _send_html(self, render_dashboard_html(resolved_db_path))

        def log_message(self, format: str, *args: object) -> None:
            return

    server = ThreadingHTTPServer(("127.0.0.1", port), Handler)
    print(f"Lead Discovery UI running at http://127.0.0.1:{port}")
    server.serve_forever()


def main() -> None:
    parser = argparse.ArgumentParser(description="Serve the Neodym Lead Discovery dashboard.")
    parser.add_argument("--db", default=os.getenv(DEFAULT_DB_ENV, "data/lead_discovery.sqlite"))
    parser.add_argument("--port", type=int, default=8501)
    args = parser.parse_args()
    serve_ui(args.db, args.port)


def _candidate_row(
    candidate: LeadCandidate,
    *,
    enriched_domains: set[str],
    enriched_names: set[str],
) -> dict[str, str]:
    website = candidate.website or ""
    is_enriched = website.strip().lower() in enriched_domains or candidate.company_name in enriched_names
    return {
        "company": candidate.company_name,
        "website": website,
        "industry": candidate.industry or "—",
        "employees": candidate.company_size or "—",
        "source": candidate.discovery_source,
        "status": "enriched" if is_enriched else "discovered",
    }


def _enriched_company_row(company: EnrichedCompany) -> dict[str, Any]:
    structured = company.structured_profile
    llm_context = structured.llm_context if structured else {}
    page_evidence = llm_context.get("page_evidence", [])
    if not isinstance(page_evidence, list):
        page_evidence = []
    manual_signals = _collect_page_list(page_evidence, "manual_process_signals")
    opportunities = _collect_page_list(page_evidence, "automation_opportunities")
    limitations = _collect_page_list(page_evidence, "limitations")

    return {
        "company": company.candidate.company_name,
        "website": company.candidate.website or "",
        "industry": company.candidate.industry or "—",
        "summary": (structured.summary if structured else None)
        or company.website_summary
        or "No summary available.",
        "services_or_products": company.services_or_products,
        "operational_signals": company.operational_complexity_signals,
        "pages_crawled": llm_context.get("pages_crawled", len(page_evidence)),
        "manual_process_signals": manual_signals,
        "automation_opportunities": opportunities,
        "limitations": limitations,
        "page_evidence": page_evidence,
        "source_urls": structured.source_urls if structured else company.candidate.source_links,
    }


def _collect_page_list(page_evidence: list[object], key: str) -> list[str]:
    values: list[str] = []
    for page in page_evidence:
        if not isinstance(page, dict):
            continue
        raw_items = page.get(key, [])
        if not isinstance(raw_items, list):
            continue
        values.extend(item for item in raw_items if isinstance(item, str) and item.strip())
    return values


def _metric_card(label: str, value: object) -> str:
    return f"<article class='metric'><span>{_escape(label)}</span><strong>{_escape(str(value))}</strong></article>"


def _candidate_table(rows: list[dict[str, str]]) -> str:
    if not rows:
        return "<p class='empty'>No candidates yet. Run discovery first.</p>"
    body = "".join(
        "<tr data-filter='{filter_text}'>"
        "<td><strong>{company}</strong></td><td>{website}</td><td>{industry}</td>"
        "<td>{employees}</td><td>{source}</td><td><span class='badge'>{status}</span></td></tr>".format(
            filter_text=_escape(_filter_text(row)),
            company=_escape(row["company"]),
            website=_link(row["website"]),
            industry=_escape(row["industry"]),
            employees=_escape(row["employees"]),
            source=_escape(row["source"]),
            status=_escape(row["status"]),
        )
        for row in rows
    )
    return f"""<div class="table-wrap"><table>
<thead><tr><th>Company</th><th>Website</th><th>Industry</th><th>Employees</th><th>Source</th><th>Status</th></tr></thead>
<tbody>{body}</tbody></table></div>"""


def _company_cards(rows: list[dict[str, Any]]) -> str:
    if not rows:
        return "<p class='empty'>No enriched companies yet. Run enrichment first.</p>"
    return "".join(_company_card(row) for row in rows)


def _company_card(row: dict[str, Any]) -> str:
    opportunities = _list_items(row["automation_opportunities"][:8])
    manual = _list_items(row["manual_process_signals"][:8])
    limitations = _list_items(row["limitations"][:6])
    services = _chips(row["services_or_products"][:10])
    signals = _chips(row["operational_signals"])
    pages = "".join(_page_evidence_card(page) for page in row["page_evidence"] if isinstance(page, dict))
    return f"""<article class="company-card" data-filter="{_escape(_filter_text(row))}">
  <div class="company-top">
    <div><h3>{_escape(row['company'])}</h3><p>{_link(row['website'])}</p></div>
    <span class="badge">{_escape(str(row['pages_crawled']))} pages</span>
  </div>
  <p class="summary">{_escape(row['summary'])}</p>
  <div class="chips">{services}{signals}</div>
  <div class="grid-two">
    <div><h4>Automation opportunities</h4>{opportunities or '<p class="muted">None detected yet.</p>'}</div>
    <div><h4>Manual process signals</h4>{manual or '<p class="muted">None detected yet.</p>'}</div>
  </div>
  <details><summary>Limitations / uncertainty</summary>{limitations or '<p class="muted">No limitations recorded.</p>'}</details>
  <details><summary>Page evidence</summary>{pages or '<p class="muted">No page evidence recorded.</p>'}</details>
</article>"""


def _page_evidence_card(page: dict[str, object]) -> str:
    title = page.get("title") or page.get("page_type") or "Page"
    url = str(page.get("url") or "")
    summary = str(page.get("page_summary") or "No page summary available.")
    excerpt = str(page.get("supporting_excerpt") or "")
    return f"""<div class="page-card">
      <strong>{_escape(str(title))}</strong> · {_link(url)}
      <p>{_escape(summary)}</p>
      {f'<blockquote>{_escape(excerpt)}</blockquote>' if excerpt else ''}
    </div>"""


def _list_items(items: list[str]) -> str:
    if not items:
        return ""
    return "<ul>" + "".join(f"<li>{_escape(item)}</li>" for item in items) + "</ul>"


def _chips(items: list[str]) -> str:
    return "".join(f"<span>{_escape(item)}</span>" for item in items if item)


def _filter_text(row: dict[str, Any]) -> str:
    return json.dumps(row, default=str).lower()


def _link(url: str) -> str:
    if not url:
        return "—"
    safe_url = _escape(url)
    return f"<a href='{safe_url}' target='_blank' rel='noreferrer'>{safe_url}</a>"


def _escape(value: str) -> str:
    return html.escape(value, quote=True)


def _send_html(handler: BaseHTTPRequestHandler, body: str) -> None:
    encoded = body.encode("utf-8")
    handler.send_response(200)
    handler.send_header("Content-Type", "text/html; charset=utf-8")
    handler.send_header("Content-Length", str(len(encoded)))
    handler.end_headers()
    handler.wfile.write(encoded)


def _send_json(handler: BaseHTTPRequestHandler, payload: dict[str, Any]) -> None:
    encoded = json.dumps(payload, default=str).encode("utf-8")
    handler.send_response(200)
    handler.send_header("Content-Type", "application/json; charset=utf-8")
    handler.send_header("Content-Length", str(len(encoded)))
    handler.end_headers()
    handler.wfile.write(encoded)


_CSS = """
:root { color-scheme: dark; font-family: Inter, ui-sans-serif, system-ui, -apple-system, sans-serif; }
* { box-sizing: border-box; }
body { margin: 0; background: radial-gradient(circle at 8% 0%, #22304a 0, #0b0f16 34%, #050609 100%); color: #edf2ff; }
a { color: #9db7ff; text-decoration: none; }
.shell { width: min(1180px, calc(100% - 40px)); margin: 0 auto; padding: 42px 0 80px; }
.hero { display: flex; justify-content: space-between; gap: 24px; align-items: flex-start; margin-bottom: 24px; }
.eyebrow { color: #7f91ff; font-size: 12px; text-transform: uppercase; letter-spacing: .18em; margin: 0 0 8px; }
h1 { font-size: clamp(36px, 6vw, 72px); line-height: .9; margin: 0 0 16px; letter-spacing: -.06em; }
h2 { margin: 0; font-size: 26px; letter-spacing: -.03em; }
h3 { font-size: 24px; margin: 0 0 4px; }
h4 { margin: 0 0 10px; color: #dfe6ff; }
.muted { color: #98a2b8; max-width: 720px; }
.db-pill, .count, .badge { border: 1px solid rgba(145,165,255,.22); background: rgba(145,165,255,.08); color: #dce5ff; border-radius: 999px; padding: 8px 12px; font-size: 13px; }
.search { width: 100%; margin: 0 0 20px; padding: 16px 18px; border-radius: 18px; border: 1px solid rgba(255,255,255,.12); background: rgba(255,255,255,.06); color: #fff; outline: none; }
.metrics { display: grid; grid-template-columns: repeat(4, minmax(0, 1fr)); gap: 14px; margin: 24px 0; }
.metric, .panel, .company-card { border: 1px solid rgba(255,255,255,.09); background: rgba(8,12,20,.72); backdrop-filter: blur(18px); border-radius: 26px; box-shadow: 0 24px 80px rgba(0,0,0,.25); }
.metric { padding: 18px; }
.metric span { display: block; color: #98a2b8; font-size: 13px; }
.metric strong { display: block; margin-top: 8px; font-size: 34px; letter-spacing: -.04em; }
.panel { padding: 22px; margin: 18px 0; }
.section-heading, .company-top { display: flex; justify-content: space-between; gap: 16px; align-items: flex-start; margin-bottom: 18px; }
.table-wrap { overflow-x: auto; border-radius: 18px; border: 1px solid rgba(255,255,255,.08); }
table { width: 100%; border-collapse: collapse; min-width: 780px; }
th, td { padding: 14px 16px; text-align: left; border-bottom: 1px solid rgba(255,255,255,.07); }
th { color: #98a2b8; font-size: 12px; text-transform: uppercase; letter-spacing: .12em; }
.company-card { padding: 22px; margin: 16px 0; }
.summary { color: #d8def0; font-size: 16px; line-height: 1.6; }
.chips { display: flex; flex-wrap: wrap; gap: 8px; margin: 14px 0; }
.chips span { background: rgba(255,255,255,.07); border: 1px solid rgba(255,255,255,.08); border-radius: 999px; padding: 7px 10px; color: #cfd8ef; font-size: 13px; }
.grid-two { display: grid; grid-template-columns: repeat(2, minmax(0, 1fr)); gap: 18px; margin: 18px 0; }
ul { padding-left: 20px; color: #d9e1f7; }
li { margin: 8px 0; }
details { border-top: 1px solid rgba(255,255,255,.08); padding-top: 14px; margin-top: 14px; }
summary { cursor: pointer; color: #b9c7ff; font-weight: 650; }
.page-card { margin: 12px 0; padding: 14px; border: 1px solid rgba(255,255,255,.08); background: rgba(255,255,255,.04); border-radius: 16px; }
blockquote { margin: 10px 0 0; padding-left: 12px; border-left: 3px solid #7285ff; color: #aeb8cd; }
.empty { color: #98a2b8; padding: 18px; border: 1px dashed rgba(255,255,255,.16); border-radius: 16px; }
@media (max-width: 860px) { .hero, .section-heading, .company-top { flex-direction: column; } .metrics, .grid-two { grid-template-columns: 1fr; } }
"""


if __name__ == "__main__":
    main()
