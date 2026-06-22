from neodym_lead_discovery.enrichment.contacts import identify_contact_candidates

TEAM_TEXT = """
Leadership
Jane Miller, Founder and CEO - jane@example.com
Raj Patel, CTO
Maria Gomez, Head of Operations
"""


def test_identify_contact_candidates_extracts_public_names_roles_and_emails():
    contacts = identify_contact_candidates(TEAM_TEXT, source_url="https://example.com/team")

    assert contacts[0].name == "Jane Miller"
    assert contacts[0].role == "Founder and CEO"
    assert contacts[0].email == "jane@example.com"
    assert contacts[1].role == "CTO"
    assert contacts[2].role == "Head of Operations"
    assert all(contact.source_url == "https://example.com/team" for contact in contacts)


def test_identify_contact_candidates_suggests_role_without_fabricating_name():
    contacts = identify_contact_candidates(
        "Our logistics platform coordinates dispatch and warehouse operations.",
        source_url="https://example.com/about",
    )

    assert len(contacts) == 1
    assert contacts[0].name is None
    assert contacts[0].role == "Head of Operations"
    assert contacts[0].email is None
