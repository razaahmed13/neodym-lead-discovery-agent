from pathlib import Path

from typer.testing import CliRunner

from neodym_lead_discovery.cli import app
from neodym_lead_discovery.website_context import discover_whitelisted_urls, extract_main_markdown

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


def test_extract_main_markdown_keeps_whole_page_text_except_layout_chrome() -> None:
    html = """
    <html><body>
      <header>Top navigation and login</header>
      <main>
        <h1>Primary product page</h1>
        <p>Core product description from main content.</p>
      </main>
      <aside>Related article sidebar should be removed.</aside>
      <div class="right-sidebar">Newsletter signup sidebar should be removed.</div>
      <section>
        <h2>FAQ outside main</h2>
        <p>Important page details that simple visible-text extraction should keep.</p>
      </section>
      <footer>Privacy Policy Terms and Conditions</footer>
    </body></html>
    """

    markdown = extract_main_markdown(html, url="https://example.com/product")

    assert "Primary product page" in markdown
    assert "Core product description" in markdown
    assert "FAQ outside main" in markdown
    assert "Important page details" in markdown
    assert "Top navigation" not in markdown
    assert "Related article sidebar" not in markdown
    assert "Newsletter signup sidebar" not in markdown
    assert "Privacy Policy" not in markdown


def test_extract_main_markdown_keeps_contact_details_from_simple_visible_text() -> None:
    html = """
    <html><body>
      <header><nav>Resources Blog FAQ Careers Claims Log In</nav></header>
      <main>
        <h1>Contact us</h1>
        <h2>Support</h2>
        <p>Call us at (800) 585-0705</p>
        <p>Email us at support@example.com</p>
        <p>Monday - Friday 7 a.m. - 8 p.m. CT</p>
        <h2>Agents</h2>
        <p>(650) 426-0546</p>
      </main>
      <footer>Privacy Policy Terms and Conditions Copyright 2026</footer>
    </body></html>
    """

    markdown = extract_main_markdown(html, url="https://example.com/contact-us")

    assert "Call us at (800) 585-0705" in markdown
    assert "Email us at support@example.com" in markdown
    assert "Monday - Friday 7 a.m. - 8 p.m. CT" in markdown
    assert "(650) 426-0546" in markdown
    assert "Privacy Policy" not in markdown


def test_extract_main_markdown_decodes_cloudflare_protected_email() -> None:
    html = """
    <html><body>
      <main>
        <p>Email us at
          <a href="/cdn-cgi/l/email-protection#ddaea8adadb2afa99db5b4adadb2f3beb2b0">
            <span
              class="__cf_email__"
              data-cfemail="8af9fffafae5f8fecae2e3fafae5a4e9e5e7"
            >[email&#160;protected]</span>
          </a>
        </p>
      </main>
    </body></html>
    """

    markdown = extract_main_markdown(html, url="https://example.com/contact-us")

    assert "support@hippo.com" in markdown
    assert "[email" not in markdown


def test_discover_whitelisted_urls_uses_strict_router_from_homepage_links() -> None:
    homepage_html = """
    <html><body>
      <a href="/home">Home</a>
      <a href="/about">About</a>
      <a href="/about-us">About us</a>
      <a href="/who-we-are">Who we are</a>
      <a href="/our-company">Our company</a>
      <a href="/what-we-do">What we do</a>
      <a href="/services/">Services</a>
      <a href="/solutions?ref=nav">Solutions</a>
      <a href="/capabilities">Capabilities</a>
      <a href="/industries">Industries</a>
      <a href="/careers">Careers</a>
      <a href="/jobs">Jobs</a>
      <a href="/join-us">Join us</a>
      <a href="/contact#form">Contact</a>
      <a href="/contact-us">Contact us</a>
      <a href="/get-in-touch">Get in touch</a>
      <a href="/support">Support</a>
      <a href="/blog">Blog</a>
      <a href="/articles/how-to-automate">Article</a>
      <a href="https://other.example/about">External About</a>
    </body></html>
    """

    def fake_fetch_url(url: str) -> str | None:
        assert url in {"https://example.com", "https://example.com/sitemap.xml"}
        if url.endswith("sitemap.xml"):
            return None
        return homepage_html

    urls = discover_whitelisted_urls("https://example.com", fetcher=fake_fetch_url)

    assert urls == [
        "https://example.com/",
        "https://example.com/home",
        "https://example.com/about",
        "https://example.com/about-us",
        "https://example.com/who-we-are",
        "https://example.com/our-company",
        "https://example.com/what-we-do",
        "https://example.com/services/",
        "https://example.com/solutions?ref=nav",
        "https://example.com/capabilities",
        "https://example.com/industries",
        "https://example.com/careers",
        "https://example.com/jobs",
        "https://example.com/join-us",
        "https://example.com/contact#form",
        "https://example.com/contact-us",
        "https://example.com/get-in-touch",
        "https://example.com/support",
    ]


def test_discover_whitelisted_urls_prefers_sitemap_when_available() -> None:
    sitemap_xml = """
    <urlset xmlns="http://www.sitemaps.org/schemas/sitemap/0.9">
      <url><loc>https://example.com/home</loc></url>
      <url><loc>https://example.com/about</loc></url>
      <url><loc>https://example.com/about-us</loc></url>
      <url><loc>https://example.com/who-we-are</loc></url>
      <url><loc>https://example.com/services</loc></url>
      <url><loc>https://example.com/solutions</loc></url>
      <url><loc>https://example.com/careers</loc></url>
      <url><loc>https://example.com/jobs</loc></url>
      <url><loc>https://example.com/blog</loc></url>
      <url><loc>https://example.com/contact</loc></url>
      <url><loc>https://example.com/contact-us</loc></url>
      <url><loc>https://example.com/get-in-touch</loc></url>
      <url><loc>https://other.example/services</loc></url>
    </urlset>
    """

    def fake_fetch_url(url: str) -> str | None:
        assert url == "https://example.com/sitemap.xml"
        return sitemap_xml

    urls = discover_whitelisted_urls("https://example.com", fetcher=fake_fetch_url)

    assert urls == [
        "https://example.com/",
        "https://example.com/home",
        "https://example.com/about",
        "https://example.com/about-us",
        "https://example.com/who-we-are",
        "https://example.com/services",
        "https://example.com/solutions",
        "https://example.com/careers",
        "https://example.com/jobs",
        "https://example.com/contact",
        "https://example.com/contact-us",
        "https://example.com/get-in-touch",
    ]


def test_fetch_website_command_writes_multiple_whitelisted_pages(
    tmp_path: Path,
    monkeypatch,
) -> None:
    output_path = tmp_path / "example-context.md"

    about_html = HTML_WITH_BOILERPLATE.replace(
        "Automating invoice processing for small manufacturers",
        "About Example Automation Agency",
    )
    services_html = HTML_WITH_BOILERPLATE.replace(
        "Automating invoice processing for small manufacturers",
        "Services for operations teams",
    )
    pages = {
        "https://example.com/sitemap.xml": None,
        "https://example.com": (
            '<a href="/about">About</a><a href="/services">Services</a><a href="/blog">Blog</a>'
        ),
        "https://example.com/": HTML_WITH_BOILERPLATE,
        "https://example.com/about": about_html,
        "https://example.com/services": services_html,
    }

    def fake_fetch_url(url: str) -> str | None:
        return pages[url]

    monkeypatch.setattr("neodym_lead_discovery.website_context.fetch_url", fake_fetch_url)

    result = CliRunner().invoke(
        app,
        ["fetch-website", "https://example.com", "--output", str(output_path)],
    )

    assert result.exit_code == 0, result.output
    assert "Wrote website context from 3 page(s)" in result.output
    markdown = output_path.read_text()
    assert markdown.startswith("# Website context")
    assert "## Source: https://example.com/" in markdown
    assert "## Source: https://example.com/about" in markdown
    assert "## Source: https://example.com/services" in markdown
    assert "About Example Automation Agency" in markdown
    assert "Services for operations teams" in markdown
    assert "blog" not in markdown.lower()
    assert "Terms of Service" not in markdown
    assert "Privacy Policy" not in markdown
