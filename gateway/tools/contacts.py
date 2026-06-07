from __future__ import annotations
import json
import threading

_cn_store = None


def _get_store():
    global _cn_store
    if _cn_store is not None:
        return _cn_store
    import Contacts

    store = Contacts.CNContactStore.alloc().init()
    done = threading.Event()

    def cb(granted, error):
        done.set()

    store.requestAccessForEntityType_completionHandler_(Contacts.CNEntityTypeContacts, cb)
    done.wait(timeout=10)
    _cn_store = store
    return store


def _all_keys():
    import Contacts
    return [
        Contacts.CNContactGivenNameKey,
        Contacts.CNContactFamilyNameKey,
        Contacts.CNContactMiddleNameKey,
        Contacts.CNContactNicknameKey,
        Contacts.CNContactOrganizationNameKey,
        Contacts.CNContactJobTitleKey,
        Contacts.CNContactEmailAddressesKey,
        Contacts.CNContactPhoneNumbersKey,
        Contacts.CNContactPostalAddressesKey,
        Contacts.CNContactBirthdayKey,
        Contacts.CNContactUrlAddressesKey,
        Contacts.CNContactSocialProfilesKey,
    ]


def _contact_to_dict(c) -> dict:
    emails = [str(e.value()) for e in (c.emailAddresses() or [])]
    phones = [str(p.value().stringValue()) for p in (c.phoneNumbers() or [])]

    addresses = []
    for pa in (c.postalAddresses() or []):
        a = pa.value()
        addresses.append({
            "street": str(a.street() or ""),
            "city": str(a.city() or ""),
            "state": str(a.state() or ""),
            "postal_code": str(a.postalCode() or ""),
            "country": str(a.country() or ""),
        })

    birthday = None
    if c.birthday():
        dc = c.birthday()
        try:
            birthday = f"{dc.year():04d}-{dc.month():02d}-{dc.day():02d}"
        except Exception:
            birthday = str(dc)

    urls = [str(u.value()) for u in (c.urlAddresses() or [])]

    return {
        "name": f"{c.givenName()} {c.familyName()}".strip(),
        "nickname": str(c.nickname() or ""),
        "organisation": str(c.organizationName() or ""),
        "job_title": str(c.jobTitle() or ""),
        "emails": emails,
        "phones": phones,
        "addresses": addresses,
        "birthday": birthday,
        "urls": urls,
    }


def lookup_contact(name: str) -> str:
    """Look up contacts by name. Returns full details including email, phone, address, birthday, organisation, and notes."""
    import Contacts
    store = _get_store()
    pred = Contacts.CNContact.predicateForContactsMatchingName_(name)
    contacts, error = store.unifiedContactsMatchingPredicate_keysToFetch_error_(pred, _all_keys(), None)
    if error:
        return json.dumps({"error": str(error)})
    return json.dumps([_contact_to_dict(c) for c in (contacts or [])])


def search_contacts(query: str) -> str:
    """Search contacts by name, email address, or phone number. Returns full contact details for matches."""
    import Contacts
    store = _get_store()
    q = query.lower()

    # Fetch all contacts and filter in Python since CNContactStore doesn't support email/phone predicates
    fetch_request = Contacts.CNContactFetchRequest.alloc().initWithKeysToFetch_(_all_keys())
    results = []
    error_ref = [None]

    found: list = []

    def handler(contact, stop):
        found.append(contact)

    store.enumerateContactsWithFetchRequest_error_usingBlock_(fetch_request, None, handler)

    for c in found:
        name_match = q in f"{c.givenName()} {c.familyName()}".lower() or q in str(c.nickname() or "").lower()
        email_match = any(q in str(e.value()).lower() for e in (c.emailAddresses() or []))
        phone_match = any(q in str(p.value().stringValue()).lower() for p in (c.phoneNumbers() or []))
        org_match = q in str(c.organizationName() or "").lower()
        if name_match or email_match or phone_match or org_match:
            results.append(_contact_to_dict(c))

    return json.dumps(results)


def list_contacts(limit: int = 50) -> str:
    """List contacts alphabetically by name. limit controls max results (default 50)."""
    import Contacts
    store = _get_store()
    fetch_request = Contacts.CNContactFetchRequest.alloc().initWithKeysToFetch_(_all_keys())

    found: list = []

    def handler(contact, stop):
        found.append(contact)

    store.enumerateContactsWithFetchRequest_error_usingBlock_(fetch_request, None, handler)

    found.sort(key=lambda c: f"{c.familyName()} {c.givenName()}".lower())
    return json.dumps([_contact_to_dict(c) for c in found[:limit]])


def register(mcp) -> None:
    for fn in [lookup_contact, search_contacts, list_contacts]:
        mcp.tool()(fn)
