from __future__ import annotations
import json
import uuid
import xml.etree.ElementTree as ET
import caldav
import vobject
from gateway.config import RadicaleConfig

_config: RadicaleConfig | None = None
_client_cache: caldav.DAVClient | None = None
_ab_url_cache: str | None = None

_DAV_NS = {"d": "DAV:"}
_MKCOL_ADDRESSBOOK_BODY = (
    '<?xml version="1.0" encoding="utf-8"?>'
    '<mkcol xmlns="DAV:" xmlns:CR="urn:ietf:params:xml:ns:carddav">'
    "<set><prop>"
    "<resourcetype><collection/><CR:addressbook/></resourcetype>"
    "<displayname>Contacts</displayname>"
    "</prop></set></mkcol>"
)


def init(config: RadicaleConfig) -> None:
    global _config, _client_cache, _ab_url_cache
    _config = config
    _client_cache = None
    _ab_url_cache = None


def _client() -> caldav.DAVClient:
    global _client_cache
    if _client_cache is None:
        assert _config and _config.base_url, "Radicale not configured (GATEWAY_RADICALE__BASE_URL required)"
        _client_cache = caldav.DAVClient(
            url=_config.base_url,
            username=_config.username,
            password=_config.password,
        )
    return _client_cache


def _addressbook_url() -> str:
    global _ab_url_cache
    if _ab_url_cache is not None:
        return _ab_url_cache
    client = _client()
    principal = client.principal()  # also provisions the user's home collection

    if _config.contacts_path:
        path = _config.contacts_path
        url = path if path.startswith("http") else _config.base_url.rstrip("/") + "/" + path.lstrip("/")
    else:
        url = str(principal.url).rstrip("/") + "/contacts/"
    if not url.endswith("/"):
        url += "/"

    if client.request(url, "PROPFIND", headers={"Depth": "0"}).status == 404:
        r = client.mkcol(url, _MKCOL_ADDRESSBOOK_BODY)
        if r.status not in (200, 201):
            raise RuntimeError(f"failed to create addressbook collection at {url}: {r.status}")

    _ab_url_cache = url
    return url


def _card_url(id: str) -> str:
    return _addressbook_url() + f"{id}.vcf"


def _split_csv(v: str) -> list[str]:
    return [t.strip() for t in v.split(",") if t.strip()]


def _vcard_to_dict(text: str) -> dict:
    card = vobject.readOne(text)

    def val(name):
        return str(getattr(card, name).value) if hasattr(card, name) else ""

    emails = [str(e.value) for e in card.contents.get("email", [])]
    phones = [str(t.value) for t in card.contents.get("tel", [])]
    urls = [str(u.value) for u in card.contents.get("url", [])]

    addresses = []
    for a in card.contents.get("adr", []):
        addr = a.value
        addresses.append({
            "street": addr.street or "",
            "city": addr.city or "",
            "state": addr.region or "",
            "postal_code": addr.code or "",
            "country": addr.country or "",
        })

    return {
        "id": val("uid"),
        "name": val("fn"),
        "nickname": val("nickname"),
        "organisation": (card.org.value[0] if hasattr(card, "org") and card.org.value else ""),
        "job_title": val("title"),
        "emails": emails,
        "phones": phones,
        "addresses": addresses,
        "birthday": val("bday") or None,
        "urls": urls,
    }


def _dict_to_vcard(contact: dict) -> str:
    card = vobject.vCard()
    card.add("uid").value = contact["id"]
    card.add("fn").value = contact["name"]

    parts = contact["name"].split(" ", 1)
    given, family = (parts[0], parts[1]) if len(parts) > 1 else (parts[0], "")
    card.add("n").value = vobject.vcard.Name(family=family, given=given)

    if contact.get("nickname"):
        card.add("nickname").value = contact["nickname"]
    if contact.get("organisation"):
        card.add("org").value = [contact["organisation"]]
    if contact.get("job_title"):
        card.add("title").value = contact["job_title"]
    for e in contact.get("emails") or []:
        card.add("email").value = e
    for p in contact.get("phones") or []:
        card.add("tel").value = p
    for a in contact.get("addresses") or []:
        adr = card.add("adr")
        adr.value = vobject.vcard.Address(
            street=a.get("street", ""),
            city=a.get("city", ""),
            region=a.get("state", ""),
            code=a.get("postal_code", ""),
            country=a.get("country", ""),
        )
    if contact.get("birthday"):
        card.add("bday").value = contact["birthday"]
    for u in contact.get("urls") or []:
        card.add("url").value = u

    return card.serialize()


def _list_card_urls() -> list[str]:
    client = _client()
    body = '<?xml version="1.0" encoding="utf-8"?><propfind xmlns="DAV:"><prop><resourcetype/></prop></propfind>'
    r = client.propfind(_addressbook_url(), body, depth=1)
    root = ET.fromstring(r.raw)
    base = _config.base_url.rstrip("/")
    urls = []
    for resp in root.findall("d:response", _DAV_NS):
        href = resp.find("d:href", _DAV_NS).text
        prop = resp.find("d:propstat/d:prop", _DAV_NS)
        rt = prop.find("d:resourcetype", _DAV_NS) if prop is not None else None
        is_collection = rt is not None and rt.find("d:collection", _DAV_NS) is not None
        if is_collection or not href.endswith(".vcf"):
            continue
        urls.append(base + href)
    return urls


def _fetch_all() -> list[dict]:
    client = _client()
    contacts = []
    for url in _list_card_urls():
        r = client.request(url, "GET")
        if r.status == 200:
            contacts.append(_vcard_to_dict(r.raw))
    return contacts


def lookup_contact(name: str) -> str:
    """Look up contacts by name. Returns full details including email, phone, address, birthday, organisation, and notes."""
    q = name.lower()
    results = [c for c in _fetch_all() if q in c["name"].lower() or q in (c.get("nickname") or "").lower()]
    return json.dumps(results)


def search_contacts(query: str) -> str:
    """Search contacts by name, email address, or phone number. Returns full contact details for matches."""
    q = query.lower()
    results = []
    for c in _fetch_all():
        name_match = q in c["name"].lower() or q in (c.get("nickname") or "").lower()
        email_match = any(q in e.lower() for e in c["emails"])
        phone_match = any(q in p.lower() for p in c["phones"])
        org_match = q in (c.get("organisation") or "").lower()
        if name_match or email_match or phone_match or org_match:
            results.append(c)
    return json.dumps(results)


def list_contacts(limit: int = 50) -> str:
    """List contacts alphabetically by name. limit controls max results (default 50)."""
    contacts = sorted(_fetch_all(), key=lambda c: c["name"].lower())
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
        "id": str(uuid.uuid4()),
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
    vcard = _dict_to_vcard(contact)
    r = _client().put(_card_url(contact["id"]), vcard, {"Content-Type": "text/vcard; charset=utf-8"})
    if r.status not in (200, 201, 204):
        return json.dumps({"error": f"failed to create contact: {r.status}"})
    return json.dumps(contact)


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
    client = _client()
    r = client.request(_card_url(id), "GET")
    if r.status != 200:
        return json.dumps({"error": f"no contact with id {id!r}"})
    existing = _vcard_to_dict(r.raw)

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
    vcard = _dict_to_vcard(contact)
    put_r = client.put(_card_url(id), vcard, {"Content-Type": "text/vcard; charset=utf-8"})
    if put_r.status not in (200, 201, 204):
        return json.dumps({"error": f"failed to update contact: {put_r.status}"})
    return json.dumps(contact)


def delete_contact(id: str) -> str:
    """Delete a contact by id (see the "id" field returned by lookup/search/list)."""
    r = _client().request(_card_url(id), "DELETE")
    if r.status not in (200, 204, 404):
        return json.dumps({"error": f"failed to delete contact: {r.status}"})
    return json.dumps({"status": "deleted", "id": id})


def register(mcp) -> None:
    for fn in [lookup_contact, search_contacts, list_contacts, create_contact, update_contact, delete_contact]:
        mcp.tool()(fn)
