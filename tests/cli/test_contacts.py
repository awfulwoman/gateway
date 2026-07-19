from __future__ import annotations
from unittest.mock import patch
from click.testing import CliRunner
from gateway.cli import main

CONTACTS = [{"name": "Alice Smith", "nickname": "", "organisation": "ACME", "job_title": "", "emails": ["alice@example.com"], "phones": ["+1 555-1234"], "addresses": [], "birthday": None, "urls": [], "note": ""}]

runner = CliRunner()


def test_lookup():
    with patch("gateway.cli.client.call_tool", return_value=CONTACTS) as mock:
        r = runner.invoke(main, ["contacts", "lookup", "Alice"])
    assert r.exit_code == 0
    assert "Alice Smith" in r.output
    mock.assert_called_once_with("http://127.0.0.1:4000/mcp", "lookup_contact", {"name": "Alice"})


def test_search():
    with patch("gateway.cli.client.call_tool", return_value=CONTACTS) as mock:
        r = runner.invoke(main, ["contacts", "search", "alice@example.com"])
    assert r.exit_code == 0
    mock.assert_called_once_with("http://127.0.0.1:4000/mcp", "search_contacts", {"query": "alice@example.com"})


def test_list_contacts():
    with patch("gateway.cli.client.call_tool", return_value=CONTACTS) as mock:
        r = runner.invoke(main, ["contacts", "list"])
    assert r.exit_code == 0
    mock.assert_called_once_with("http://127.0.0.1:4000/mcp", "list_contacts", {"limit": 50})


def test_create():
    with patch("gateway.cli.client.call_tool", return_value=CONTACTS[0]) as mock:
        r = runner.invoke(main, ["contacts", "create", "Alice Smith", "--org", "ACME", "--emails", "alice@example.com"])
    assert r.exit_code == 0
    assert "Created: Alice Smith" in r.output
    mock.assert_called_once_with("http://127.0.0.1:4000/mcp", "create_contact", {
        "name": "Alice Smith", "nickname": "", "organisation": "ACME", "job_title": "",
        "emails": "alice@example.com", "phones": "", "urls": "", "birthday": "",
        "address_street": "", "address_city": "", "address_state": "",
        "address_postal_code": "", "address_country": "",
    })


def test_update():
    with patch("gateway.cli.client.call_tool", return_value=CONTACTS[0]) as mock:
        r = runner.invoke(main, ["contacts", "update", "contact-id-1", "--title", "Engineer"])
    assert r.exit_code == 0
    assert "Updated: Alice Smith" in r.output
    mock.assert_called_once_with("http://127.0.0.1:4000/mcp", "update_contact", {
        "id": "contact-id-1", "name": "", "nickname": "", "organisation": "", "job_title": "Engineer",
        "emails": "", "phones": "", "urls": "", "birthday": "",
        "address_street": "", "address_city": "", "address_state": "",
        "address_postal_code": "", "address_country": "",
    })


def test_delete():
    with patch("gateway.cli.client.call_tool", return_value={"status": "deleted", "id": "contact-id-1"}) as mock:
        r = runner.invoke(main, ["contacts", "delete", "contact-id-1"])
    assert r.exit_code == 0
    assert "Deleted: contact-id-1" in r.output
    mock.assert_called_once_with("http://127.0.0.1:4000/mcp", "delete_contact", {"id": "contact-id-1"})
