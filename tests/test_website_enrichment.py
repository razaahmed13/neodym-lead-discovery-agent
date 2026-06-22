from neodym_lead_discovery.enrichment.website import extract_website_profile
from neodym_lead_discovery.models import LeadCandidate

HTML = """
<html>
<head>
  <title>ABC Logistics | Freight and Dispatch</title>
  <meta name="description"
        content="Regional logistics company handling freight dispatch and customer updates.">
</head>
<body>
  <h1>Freight operations for growing shippers</h1>
  <h2>Services</h2>
  <p>We provide dispatch coordination, warehousing, and customer support workflows.</p>
  <a href="/about">About Us</a>
  <a href="https://abclogistics.example/contact">Contact</a>
  <a href="/careers">Careers</a>
</body>
</html>
"""


def test_extract_website_profile_from_static_html():
    candidate = LeadCandidate(
        company_name="ABC Logistics",
        website="https://abclogistics.example",
        source_links=["https://abclogistics.example"],
    )

    enriched = extract_website_profile(
        candidate,
        HTML,
        source_url="https://abclogistics.example",
    )

    assert enriched.website_title == "ABC Logistics | Freight and Dispatch"
    assert "Regional logistics company" in enriched.website_summary
    assert "https://abclogistics.example/about" in enriched.candidate.source_links
    assert "https://abclogistics.example/contact" in enriched.candidate.source_links
    assert "dispatch coordination" in enriched.evidence[0].snippet.lower()
    assert "dispatch" in enriched.operational_complexity_signals
