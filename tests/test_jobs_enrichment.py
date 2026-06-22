from neodym_lead_discovery.enrichment.jobs import discover_careers_urls, extract_job_signals

HOME_HTML = """
<a href="/careers">Careers</a>
<a href="https://example.com/about">About</a>
"""

CAREERS_HTML = """
<h1>Join our team</h1>
<div>Operations Manager</div>
<div>Customer Support Specialist</div>
<div>Data Engineer</div>
<div>AI Automation Analyst</div>
"""


def test_discover_careers_urls_from_homepage_links_and_common_paths():
    urls = discover_careers_urls("https://example.com", HOME_HTML)

    assert "https://example.com/careers" in urls
    assert "https://example.com/jobs" in urls
    assert "https://example.com/work-with-us" in urls


def test_extract_job_signals_detects_growth_and_operational_roles():
    signals = extract_job_signals(CAREERS_HTML, source_url="https://example.com/careers")

    assert "Operations Manager" in signals.roles
    assert "Customer Support Specialist" in signals.roles
    assert "operations" in signals.operational_signals
    assert "support" in signals.operational_signals
    assert "engineering" in signals.growth_signals
    assert "ai_automation" in signals.growth_signals
    assert signals.evidence.url == "https://example.com/careers"
