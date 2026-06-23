from pathlib import Path

from typer.testing import CliRunner

from neodym_lead_discovery.cli import app
from neodym_lead_discovery.website_context import extract_main_markdown

HTML_WITH_BOILERPLATE = """
<html>
  <head><title>Example Automation Agency</title></head>
  <body>
    <header>
      <nav>Home | Terms of Service | Privacy Policy | Careers | Login</nav>
      <div class="cookie">We use cookies. Accept all cookies.</div>
    </header>
    <main>
      <article>
        <h1>Automating invoice processing for small manufacturers</h1>
        <p>Example Automation Agency builds workflow automations for finance teams.</p>
        <p>Our implementation replaces spreadsheet handoffs, manual PDF review,
        and repetitive email follow-up.</p>
        <h2>Services</h2>
        <p>We connect ERP systems, OCR tools, approvals, and customer support inboxes.</p>
      </article>
    </main>
    <footer>Terms of Service | Privacy Policy | Careers | Copyright 2026</footer>
  </body>
</html>
"""


def test_extract_main_markdown_prunes_navigation_footer_and_cookie_boilerplate() -> None:
    markdown = extract_main_markdown(HTML_WITH_BOILERPLATE, url="https://example.com")

    assert "Automating invoice processing for small manufacturers" in markdown
    assert "spreadsheet handoffs" in markdown
    assert "ERP systems" in markdown
    assert "Terms of Service" not in markdown
    assert "Privacy Policy" not in markdown
    assert "Accept all cookies" not in markdown


def test_fetch_website_command_writes_short_llm_ready_markdown_file(
    tmp_path: Path, monkeypatch
) -> None:
    output_path = tmp_path / "example-context.md"

    def fake_fetch_url(url: str) -> str:
        assert url == "https://example.com"
        return HTML_WITH_BOILERPLATE

    monkeypatch.setattr("neodym_lead_discovery.website_context.fetch_url", fake_fetch_url)

    result = CliRunner().invoke(
        app,
        ["fetch-website", "https://example.com", "--output", str(output_path)],
    )

    assert result.exit_code == 0, result.output
    assert "Wrote pruned website context" in result.output
    markdown = output_path.read_text()
    assert markdown.startswith("# Website context")
    assert "Source URL: https://example.com" in markdown
    assert "Automating invoice processing" in markdown
    assert "Terms of Service" not in markdown
    assert "Privacy Policy" not in markdown
