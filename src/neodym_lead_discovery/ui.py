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

from neodym_lead_discovery.models import LeadCandidate
from neodym_lead_discovery.storage import LeadStorage

DEFAULT_DB_ENV = "LEAD_DISCOVERY_DB"


def load_dashboard_data(db_path: str | Path) -> dict[str, Any]:
    """Load discovered candidates and return UI-friendly summary data."""
    storage = LeadStorage(db_path)
    storage.initialize()
    candidates = storage.list_candidates()
    candidate_rows = [_candidate_row(candidate) for _, candidate in candidates]

    return {
        "metrics": {
            "candidates": len(candidate_rows),
        },
        "candidates": candidate_rows,
    }


def render_dashboard_html(db_path: str | Path) -> str:
    """Render a self-contained minimalist dashboard as HTML."""
    dashboard = load_dashboard_data(db_path)
    metrics = dashboard["metrics"]
    candidates = dashboard["candidates"]
    return f"""<!doctype html>
<html lang="en">
<head>
  <meta charset="utf-8" />
  <meta name="viewport" content="width=device-width, initial-scale=1" />
  <title>Neodym Lead Discovery</title>
  <style>{_CSS}</style>
</head>
<body>
  <aside class="sidebar">
    <div class="sidebar-brand">
      <p class="eyebrow">Navigation</p>
      <strong>Lead workspace</strong>
    </div>
    <div class="sidebar-section">
      <div class="sidebar-title">Candidates <span>{len(candidates)}</span></div>
      {_sidebar_candidates(candidates)}
    </div>
  </aside>
  <main class="shell">
    <section class="hero">
      <div>
        <p class="eyebrow">Neodym Lead Discovery Agent</p>
        <h1>Lead discovery dashboard</h1>
        <p class="muted">Review fetched lead candidates from discovery. The old post-discovery workflow has been removed so a new context-building approach can be added cleanly.</p>
      </div>
      <div class="db-pill">{_escape(str(db_path))}</div>
    </section>

    <section class="metrics">
      {_metric_card('Candidates', metrics['candidates'])}
    </section>

    <section class="panel" id="candidates">
      <div class="section-heading">
        <div>
          <p class="eyebrow">Discovery</p>
          <h2>Fetched candidates</h2>
        </div>
        <span class="count">{len(candidates)} total</span>
      </div>
      {_candidate_table(candidates)}
    </section>
  </main>
  <script>
    const search = document.createElement('input');
    search.placeholder = 'Filter companies, industries, locations...';
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


def _candidate_row(candidate: LeadCandidate) -> dict[str, str]:
    return {
        "company": candidate.company_name,
        "website": candidate.website or "",
        "industry": candidate.industry or "—",
        "location": candidate.location or "—",
        "employees": candidate.company_size or "—",
        "source": candidate.discovery_source,
        "status": "discovered",
    }


def _metric_card(label: str, value: object) -> str:
    return f"<article class='metric'><span>{_escape(label)}</span><strong>{_escape(str(value))}</strong></article>"


def _candidate_table(rows: list[dict[str, str]]) -> str:
    if not rows:
        return "<p class='empty'>No candidates yet. Run discovery first.</p>"
    body = "".join(
        "<tr data-filter='{filter_text}'>"
        "<td><strong>{company}</strong></td><td>{website}</td><td>{industry}</td>"
        "<td>{location}</td><td>{employees}</td><td>{source}</td><td><span class='badge'>{status}</span></td></tr>".format(
            filter_text=_escape(_filter_text(row)),
            company=_escape(row["company"]),
            website=_link(row["website"]),
            industry=_escape(row["industry"]),
            location=_escape(row["location"]),
            employees=_escape(row["employees"]),
            source=_escape(row["source"]),
            status=_escape(row["status"]),
        )
        for row in rows
    )
    return f"""<div class="table-wrap"><table>
<thead><tr><th>Company</th><th>Website</th><th>Industry</th><th>Location</th><th>Employees</th><th>Source</th><th>Status</th></tr></thead>
<tbody>{body}</tbody></table></div>"""


def _sidebar_candidates(rows: list[dict[str, str]]) -> str:
    if not rows:
        return "<p class='sidebar-empty'>No candidates yet</p>"
    return "".join(
        "<a class='sidebar-link' href='#candidates' data-filter='{filter_text}'>"
        "<strong>{company}</strong><span>{status} · {industry}</span></a>".format(
            filter_text=_escape(_filter_text(row)),
            company=_escape(row["company"]),
            status=_escape(row["status"]),
            industry=_escape(row["industry"]),
        )
        for row in rows
    )


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
.sidebar { position: fixed; inset: 0 auto 0 0; width: 300px; padding: 24px 18px; overflow-y: auto; border-right: 1px solid rgba(255,255,255,.09); background: rgba(4,7,12,.72); backdrop-filter: blur(20px); }
.sidebar-brand { margin-bottom: 24px; }
.sidebar-brand strong { display: block; font-size: 20px; letter-spacing: -.03em; }
.sidebar-section { margin: 22px 0; }
.sidebar-title { display: flex; align-items: center; justify-content: space-between; color: #dce5ff; font-size: 12px; text-transform: uppercase; letter-spacing: .14em; margin-bottom: 10px; }
.sidebar-title span { color: #7f91ff; }
.sidebar-link { display: block; width: 100%; margin: 8px 0; padding: 12px 12px; border-radius: 16px; border: 1px solid rgba(255,255,255,.08); background: rgba(255,255,255,.035); color: #e8edff; text-align: left; cursor: pointer; }
.sidebar-link strong { display: block; font-size: 14px; }
.sidebar-link span, .sidebar-empty { display: block; margin-top: 4px; color: #98a2b8; font-size: 12px; }
.shell { width: min(1180px, calc(100% - 360px)); margin: 0 32px 0 332px; padding: 42px 0 80px; }
.hero { display: flex; justify-content: space-between; gap: 24px; align-items: flex-start; margin-bottom: 24px; }
.eyebrow { color: #7f91ff; font-size: 12px; text-transform: uppercase; letter-spacing: .18em; margin: 0 0 8px; }
h1 { font-size: clamp(36px, 6vw, 72px); line-height: .9; margin: 0 0 16px; letter-spacing: -.06em; }
h2 { margin: 0; font-size: 26px; letter-spacing: -.03em; }
.muted { color: #98a2b8; max-width: 720px; }
.db-pill, .count, .badge { border: 1px solid rgba(145,165,255,.22); background: rgba(145,165,255,.08); color: #dce5ff; border-radius: 999px; padding: 8px 12px; font-size: 13px; }
.search { width: 100%; margin: 0 0 20px; padding: 16px 18px; border-radius: 18px; border: 1px solid rgba(255,255,255,.12); background: rgba(255,255,255,.06); color: #fff; outline: none; }
.metrics { display: grid; grid-template-columns: repeat(4, minmax(0, 1fr)); gap: 14px; margin: 24px 0; }
.metric, .panel { border: 1px solid rgba(255,255,255,.09); background: rgba(8,12,20,.72); backdrop-filter: blur(18px); border-radius: 26px; box-shadow: 0 24px 80px rgba(0,0,0,.25); }
.metric { padding: 18px; }
.metric span { display: block; color: #98a2b8; font-size: 13px; }
.metric strong { display: block; margin-top: 8px; font-size: 34px; letter-spacing: -.04em; }
.panel { padding: 22px; margin: 18px 0; }
.section-heading { display: flex; justify-content: space-between; gap: 16px; align-items: flex-start; margin-bottom: 18px; }
.table-wrap { overflow-x: auto; border-radius: 18px; border: 1px solid rgba(255,255,255,.08); }
table { width: 100%; border-collapse: collapse; min-width: 780px; }
th, td { padding: 14px 16px; text-align: left; border-bottom: 1px solid rgba(255,255,255,.07); }
th { color: #98a2b8; font-size: 12px; text-transform: uppercase; letter-spacing: .12em; }
.empty { color: #98a2b8; padding: 18px; border: 1px dashed rgba(255,255,255,.16); border-radius: 16px; }
@media (max-width: 860px) { .sidebar { position: static; width: auto; border-right: 0; border-bottom: 1px solid rgba(255,255,255,.09); } .shell { width: min(100% - 32px, 1180px); margin: 0 auto; } .hero, .section-heading { flex-direction: column; } .metrics { grid-template-columns: 1fr; } }
"""


if __name__ == "__main__":
    main()
