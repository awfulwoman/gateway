"""eBay listings via the Browse API. eBay's web pages block automated
fetching, so this goes through the official API with an application
(client-credentials) token instead — read-only, no eBay user login.

Listings are looked up by their "legacy" item ID: the number in an
/itm/<id> URL. Short links (ebay.io/m/...) are resolved by following their
redirect without fetching the listing page itself.
"""
from __future__ import annotations

import html
import json
import re
import time
from urllib.parse import parse_qs, urljoin, urlparse

import httpx

from gateway.config import EbayConfig

_config: EbayConfig | None = None
_api: str = "https://api.ebay.com"
_token: tuple[str, float] | None = None  # (access token, monotonic expiry)

_SCOPE = "https://api.ebay.com/oauth/api_scope"
_MAX_REDIRECTS = 5

# eBay site domain -> Browse API marketplace ID.
_MARKETPLACES = {
    "ebay.de": "EBAY_DE",
    "ebay.at": "EBAY_AT",
    "ebay.ch": "EBAY_CH",
    "ebay.co.uk": "EBAY_GB",
    "ebay.ie": "EBAY_IE",
    "ebay.fr": "EBAY_FR",
    "ebay.it": "EBAY_IT",
    "ebay.es": "EBAY_ES",
    "ebay.nl": "EBAY_NL",
    "ebay.be": "EBAY_BE",
    "ebay.pl": "EBAY_PL",
    "ebay.com": "EBAY_US",
    "ebay.ca": "EBAY_CA",
    "ebay.com.au": "EBAY_AU",
}


def init(config: EbayConfig, api_url: str = "https://api.ebay.com") -> None:
    global _config, _api, _token
    _config = config
    _api = api_url.rstrip("/")
    _token = None


def _cfg() -> EbayConfig:
    assert _config and _config.client_id and _config.client_secret, (
        "eBay not configured — set GATEWAY_EBAY__CLIENT_ID and GATEWAY_EBAY__CLIENT_SECRET"
    )
    return _config


def _access_token() -> str:
    global _token
    cfg = _cfg()
    if _token and time.monotonic() < _token[1]:
        return _token[0]
    r = httpx.post(
        f"{_api}/identity/v1/oauth2/token",
        auth=(cfg.client_id, cfg.client_secret),
        data={"grant_type": "client_credentials", "scope": _SCOPE},
        timeout=30,
    )
    r.raise_for_status()
    data = r.json()
    # Refresh a minute early so a token never expires mid-request.
    _token = (data["access_token"], time.monotonic() + int(data.get("expires_in", 7200)) - 60)
    return _token[0]


def _get(path: str, params: dict, marketplace: str) -> dict:
    r = httpx.get(
        f"{_api}/buy/browse/v1{path}",
        params=params,
        headers={"Authorization": f"Bearer {_access_token()}", "X-EBAY-C-MARKETPLACE-ID": marketplace},
        timeout=30,
    )
    if r.status_code >= 400:
        try:
            errors = r.json().get("errors", [])
            detail = "; ".join(e.get("message", "") for e in errors) or r.text
        except ValueError:
            detail = r.text
        raise RuntimeError(f"eBay API error {r.status_code}: {detail}")
    return r.json()


def _marketplace_for(host: str) -> str | None:
    host = host.lower()
    for domain in sorted(_MARKETPLACES, key=len, reverse=True):
        if host == domain or host.endswith("." + domain):
            return _MARKETPLACES[domain]
    return None


def _item_ref(url_or_id: str, hops: int = 0) -> tuple[str, str, str | None]:
    """Returns (legacy item ID, legacy variation ID or "", marketplace or None)."""
    s = url_or_id.strip()
    if s.isdigit():
        return s, "", None
    if "://" not in s:
        s = "https://" + s
    u = urlparse(s)
    marketplace = _marketplace_for(u.hostname or "")
    m = re.search(r"/itm/(?:[^/]+/)?(\d+)", u.path)
    if m:
        variation = parse_qs(u.query).get("var", [""])[0]
        return m.group(1), variation, marketplace
    if marketplace or hops >= _MAX_REDIRECTS:
        raise ValueError(f"no eBay item ID in {url_or_id!r} — expected an item ID or an /itm/<id> URL")
    # Anything else is treated as a short link: follow one redirect hop and
    # look again, never reading the page body.
    r = httpx.get(s, follow_redirects=False, timeout=30)
    if not r.is_redirect:
        raise ValueError(f"no eBay item ID in {url_or_id!r} — not an eBay URL and not a redirect to one")
    return _item_ref(urljoin(s, r.headers["location"]), hops + 1)


def _money(amount: dict | None) -> str | None:
    if not amount:
        return None
    return f"{amount.get('value')} {amount.get('currency')}"


def _location(address: dict | None) -> str | None:
    if not address:
        return None
    parts = [address.get(k) for k in ("city", "postalCode", "country")]
    return ", ".join(p for p in parts if p) or None


def _seller(seller: dict | None) -> dict | None:
    if not seller:
        return None
    return {
        "username": seller.get("username"),
        "feedback_score": seller.get("feedbackScore"),
        "feedback_percentage": seller.get("feedbackPercentage"),
    }


def _shipping(options: list | None) -> list[dict]:
    return [
        {
            "type": o.get("type") or o.get("shippingCostType"),
            "cost": _money(o.get("shippingCost")),
            "min_delivery": (o.get("minEstimatedDeliveryDate") or "")[:10] or None,
            "max_delivery": (o.get("maxEstimatedDeliveryDate") or "")[:10] or None,
        }
        for o in options or []
    ]


def _returns(terms: dict | None) -> str | None:
    if not terms:
        return None
    if not terms.get("returnsAccepted"):
        return "not accepted"
    period = terms.get("returnPeriod")
    return f"{period.get('value')} {period.get('unit')}" if period else "accepted"


def _text(markup: str | None) -> str:
    """Listing descriptions are seller-written HTML; reduce to readable text."""
    if not markup:
        return ""
    text = re.sub(r"<(script|style)\b.*?</\1\s*>", " ", markup, flags=re.S | re.I)
    text = re.sub(r"<br\s*/?>|</(p|div|li|tr|h\d)\s*>", "\n", text, flags=re.I)
    text = html.unescape(re.sub(r"<[^>]+>", " ", text))
    lines = (re.sub(r"\s+", " ", line).strip() for line in text.splitlines())
    return "\n".join(line for line in lines if line)


def _images(item: dict) -> list[str]:
    images = [item.get("image")] + (item.get("additionalImages") or [])
    return [i["imageUrl"] for i in images if i and i.get("imageUrl")]


def get_ebay_listing(url_or_id: str) -> str:
    """Get an eBay listing's details: title, price, condition, seller, location,
    shipping, returns, item specifics, description (as plain text) and images.
    Accepts an item URL from any eBay site (tracking params are fine), an
    ebay.io / ebay.us short link, or a bare item ID. The marketplace (and so
    currency and shipping context) follows the URL's domain."""
    legacy_id, variation_id, marketplace = _item_ref(url_or_id)
    marketplace = marketplace or _cfg().marketplace
    params = {"legacy_item_id": legacy_id}
    if variation_id:
        params["legacy_variation_id"] = variation_id
    item = _get("/item/get_item_by_legacy_id", params, marketplace)
    return json.dumps({
        "item_id": item.get("itemId"),
        "legacy_item_id": item.get("legacyItemId"),
        "title": item.get("title"),
        "subtitle": item.get("subtitle"),
        "url": item.get("itemWebUrl"),
        "marketplace": marketplace,
        "price": _money(item.get("price")),
        "current_bid": _money(item.get("currentBidPrice")),
        "bid_count": item.get("bidCount"),
        "end_date": item.get("itemEndDate"),
        "buying_options": item.get("buyingOptions") or [],
        "condition": item.get("condition"),
        "condition_description": item.get("conditionDescription"),
        "category": item.get("categoryPath"),
        "seller": _seller(item.get("seller")),
        "location": _location(item.get("itemLocation")),
        "shipping": _shipping(item.get("shippingOptions")),
        "returns": _returns(item.get("returnTerms")),
        "item_specifics": {a["name"]: a.get("value") for a in item.get("localizedAspects") or [] if a.get("name")},
        "short_description": item.get("shortDescription"),
        "description": _text(item.get("description")),
        "images": _images(item),
    })


def search_ebay(query: str, limit: int = 10, offset: int = 0, sort: str = "", filter: str = "",
                marketplace: str = "") -> str:
    """Search eBay listings by keyword. `sort`: "price", "-price", "newlyListed",
    "endingSoonest" (default: best match). `filter` uses Browse API syntax, comma
    separated, e.g. "price:[10..50],priceCurrency:EUR", "buyingOptions:{AUCTION}",
    "conditions:{USED}", "itemLocationCountry:DE". `marketplace` is an ID like
    EBAY_DE or EBAY_GB (default from config). Page with `offset`."""
    marketplace = marketplace or _cfg().marketplace
    params: dict = {"q": query, "limit": min(limit, 200), "offset": offset}
    if sort:
        params["sort"] = sort
    if filter:
        params["filter"] = filter
    data = _get("/item_summary/search", params, marketplace)
    items = [
        {
            "item_id": s.get("itemId"),
            "legacy_item_id": s.get("legacyItemId"),
            "title": s.get("title"),
            "price": _money(s.get("price")),
            "current_bid": _money(s.get("currentBidPrice")),
            "bid_count": s.get("bidCount"),
            "end_date": s.get("itemEndDate"),
            "buying_options": s.get("buyingOptions") or [],
            "condition": s.get("condition"),
            "seller": _seller(s.get("seller")),
            "location": _location(s.get("itemLocation")),
            "shipping_cost": next((c for c in (o["cost"] for o in _shipping(s.get("shippingOptions"))) if c), None),
            "url": s.get("itemWebUrl"),
            "image": (s.get("image") or {}).get("imageUrl"),
        }
        for s in data.get("itemSummaries") or []
    ]
    return json.dumps({"total": data.get("total", 0), "offset": data.get("offset", offset), "items": items})


def register(mcp) -> None:
    for fn in [get_ebay_listing, search_ebay]:
        mcp.tool()(fn)
