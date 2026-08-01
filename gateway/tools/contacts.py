from __future__ import annotations
import json
from gateway.config import ContactsServerConfig
from gateway.contacts_server import store

_config: ContactsServerConfig | None = None


def init(config: ContactsServerConfig) -> None:
    global _config
    _config = config
    store.init(config)


def _split_csv(v: str) -> list[str]:
    return [t.strip() for t in v.split(",") if t.strip()]


def lookup_contact(name: str) -> str:
    """Look up contacts by name. Returns full details including email, phone, address, birthday, organisation, and notes."""
    q = name.lower()
    results = [c for c in store.list_contacts() if q in c["name"].lower() or q in (c.get("nickname") or "").lower()]
    return json.dumps(results)


def search_contacts(query: str) -> str:
    """Search contacts by name, email address, or phone number. Returns full contact details for matches."""
    q = query.lower()
    results = []
    for c in store.list_contacts():
        name_match = q in c["name"].lower() or q in (c.get("nickname") or "").lower()
        email_match = any(q in e.lower() for e in c["emails"])
        phone_match = any(q in p.lower() for p in c["phones"])
        org_match = q in (c.get("organisation") or "").lower()
        if name_match or email_match or phone_match or org_match:
            results.append(c)
    return json.dumps(results)


def list_contacts(limit: int = 50) -> str:
    """List contacts alphabetically by name. limit controls max results (default 50)."""
    contacts = store.list_contacts()  # already sorted by name by the server
    return json.dumps(contacts[:limit])


def create_contact(
    name: str,
    nickname: str = "",
    organisation: str = "",
    job_title: str = "",
    emails: str = "",
    phones: str = "",
    urls: str = "",
    birthday: str = "",
    address_street: str = "",
    address_city: str = "",
    address_state: str = "",
    address_postal_code: str = "",
    address_country: str = "",
) -> str:
    """Create a contact. emails, phones, and urls are comma-separated lists. birthday is
    YYYY-MM-DD. Address fields describe a single postal address (all optional)."""
    addresses = []
    if any([address_street, address_city, address_state, address_postal_code, address_country]):
        addresses.append({
            "street": address_street, "city": address_city, "state": address_state,
            "postal_code": address_postal_code, "country": address_country,
        })
    contact = {
        "id": store.new_id(),
        "name": name,
        "nickname": nickname,
        "organisation": organisation,
        "job_title": job_title,
        "emails": _split_csv(emails),
        "phones": _split_csv(phones),
        "addresses": addresses,
        "birthday": birthday or None,
        "urls": _split_csv(urls),
    }
    try:
        stored = store.upsert(contact)
    except ValueError as e:
        return json.dumps({"error": f"failed to create contact: {e}"})
    return json.dumps(stored)


def update_contact(
    id: str,
    name: str = "",
    nickname: str = "",
    organisation: str = "",
    job_title: str = "",
    emails: str = "",
    phones: str = "",
    urls: str = "",
    birthday: str = "",
    address_street: str = "",
    address_city: str = "",
    address_state: str = "",
    address_postal_code: str = "",
    address_country: str = "",
) -> str:
    """Update a contact by id (see the "id" field returned by lookup/search/list). Any
    field left blank keeps its existing value; emails/phones/urls are comma-separated
    and, if provided, replace the existing list entirely."""
    existing = store.get(id)
    if existing is None:
        return json.dumps({"error": f"no contact with id {id!r}"})

    addresses = existing["addresses"]
    if any([address_street, address_city, address_state, address_postal_code, address_country]):
        addresses = [{
            "street": address_street, "city": address_city, "state": address_state,
            "postal_code": address_postal_code, "country": address_country,
        }]

    contact = {
        "id": id,
        "name": name or existing["name"],
        "nickname": nickname or existing["nickname"],
        "organisation": organisation or existing["organisation"],
        "job_title": job_title or existing["job_title"],
        "emails": _split_csv(emails) if emails else existing["emails"],
        "phones": _split_csv(phones) if phones else existing["phones"],
        "addresses": addresses,
        "birthday": birthday or existing["birthday"],
        "urls": _split_csv(urls) if urls else existing["urls"],
    }
    try:
        stored = store.upsert(contact)
    except ValueError as e:
        return json.dumps({"error": f"failed to update contact: {e}"})
    return json.dumps(stored)


def delete_contact(id: str) -> str:
    """Delete a contact by id (see the "id" field returned by lookup/search/list)."""
    store.delete(id)  # idempotent: deleting an already-gone id is not an error
    return json.dumps({"status": "deleted", "id": id})


def register(mcp) -> None:
    for fn in [lookup_contact, search_contacts, list_contacts, create_contact, update_contact, delete_contact]:
        mcp.tool()(fn)
