from __future__ import annotations
import json
import pytest
import gateway.tools.contacts as contacts
from gateway.config import RadicaleConfig


@pytest.fixture
def cn(radicale_server, radicale_user):
    contacts.init(RadicaleConfig(base_url=radicale_server, username=radicale_user, password="x"))
    return contacts


def test_list_contacts_empty(cn):
    assert json.loads(cn.list_contacts()) == []


def test_create_then_list(cn):
    created = json.loads(cn.create_contact("Alice Smith", organisation="ACME", emails="alice@example.com,alice@work.com"))
    assert created["name"] == "Alice Smith"
    assert created["organisation"] == "ACME"
    assert created["emails"] == ["alice@example.com", "alice@work.com"]
    assert created["id"]

    listed = json.loads(cn.list_contacts())
    assert len(listed) == 1
    assert listed[0]["name"] == "Alice Smith"


def test_create_with_phones_urls_birthday_address(cn):
    created = json.loads(cn.create_contact(
        "Bob Jones",
        phones="+1 555-1234",
        urls="https://example.com",
        birthday="1990-05-01",
        address_street="1 Main St",
        address_city="Berlin",
        address_postal_code="10115",
        address_country="Germany",
    ))
    assert created["phones"] == ["+1 555-1234"]
    assert created["urls"] == ["https://example.com"]
    assert created["birthday"] == "1990-05-01"
    assert created["addresses"] == [{
        "street": "1 Main St", "city": "Berlin", "state": "", "postal_code": "10115", "country": "Germany",
    }]


def test_lookup_contact_matches_name(cn):
    cn.create_contact("Alice Smith")
    cn.create_contact("Bob Jones")
    results = json.loads(cn.lookup_contact("Alice"))
    assert len(results) == 1
    assert results[0]["name"] == "Alice Smith"


def test_search_contacts_matches_email(cn):
    cn.create_contact("Alice Smith", emails="alice@example.com")
    cn.create_contact("Bob Jones", emails="bob@example.com")
    results = json.loads(cn.search_contacts("alice@example.com"))
    assert len(results) == 1
    assert results[0]["name"] == "Alice Smith"


def test_search_contacts_matches_phone_and_org(cn):
    cn.create_contact("Alice Smith", phones="+1 555-1234", organisation="ACME")
    assert len(json.loads(cn.search_contacts("555-1234"))) == 1
    assert len(json.loads(cn.search_contacts("ACME"))) == 1


def test_list_contacts_sorted_and_limited(cn):
    cn.create_contact("Charlie")
    cn.create_contact("Alice")
    cn.create_contact("Bob")
    names = [c["name"] for c in json.loads(cn.list_contacts(limit=2))]
    assert names == ["Alice", "Bob"]


def test_update_contact_changes_only_given_fields(cn):
    created = json.loads(cn.create_contact("Alice Smith", organisation="ACME", emails="alice@example.com"))
    updated = json.loads(cn.update_contact(created["id"], job_title="Engineer"))
    assert updated["name"] == "Alice Smith"
    assert updated["organisation"] == "ACME"
    assert updated["job_title"] == "Engineer"
    assert updated["emails"] == ["alice@example.com"]


def test_update_contact_replaces_emails_when_given(cn):
    created = json.loads(cn.create_contact("Alice Smith", emails="old@example.com"))
    updated = json.loads(cn.update_contact(created["id"], emails="new@example.com"))
    assert updated["emails"] == ["new@example.com"]


def test_update_contact_missing_id_errors(cn):
    result = json.loads(cn.update_contact("nonexistent", name="X"))
    assert "error" in result


def test_delete_contact(cn):
    created = json.loads(cn.create_contact("Alice Smith"))
    result = json.loads(cn.delete_contact(created["id"]))
    assert result["status"] == "deleted"
    assert json.loads(cn.list_contacts()) == []


def test_delete_contact_missing_is_a_noop(cn):
    result = json.loads(cn.delete_contact("nonexistent"))
    assert result["status"] == "deleted"
