"""eBay listings via the Browse API, against an in-process fake (see
`_FakeEbay` in conftest). Field names in the seeded payloads follow eBay's
Browse OpenAPI contract (Item, ItemSummary, ConvertedAmount, ...).
"""
from __future__ import annotations

import json

import pytest

import gateway.tools.ebay as ebay
from gateway.config import EbayConfig

ITEM = {
    "itemId": "v1|820201318060|0",
    "legacyItemId": "820201318060",
    "title": "Makita DHP482 Akku-Schlagbohrschrauber",
    "subtitle": "Kaum benutzt",
    "price": {"value": "89.00", "currency": "EUR"},
    "condition": "Gebraucht",
    "conditionDescription": "Leichte Gebrauchsspuren",
    "buyingOptions": ["FIXED_PRICE", "BEST_OFFER"],
    "categoryPath": "Heimwerker|Elektrowerkzeuge",
    "itemWebUrl": "https://www.ebay.de/itm/820201318060",
    "seller": {"username": "werkzeugkiste", "feedbackScore": 412, "feedbackPercentage": "99.8"},
    "itemLocation": {"city": "Berlin", "postalCode": "10*", "country": "DE"},
    "shippingOptions": [{
        "type": "Standardversand",
        "shippingCost": {"value": "5.99", "currency": "EUR"},
        "minEstimatedDeliveryDate": "2026-10-08T00:00:00.000Z",
        "maxEstimatedDeliveryDate": "2026-10-10T00:00:00.000Z",
    }],
    "returnTerms": {"returnsAccepted": True, "returnPeriod": {"value": 30, "unit": "CALENDAR_DAY"}},
    "localizedAspects": [
        {"type": "STRING", "name": "Marke", "value": "Makita"},
        {"type": "STRING", "name": "Modell", "value": "DHP482"},
    ],
    "shortDescription": "Schlagbohrschrauber ohne Akku",
    "description": "<style>p{color:red}</style><p>Ohne Akku &amp; Ladeger&auml;t.</p><p>Abholung m&ouml;glich.</p>"
                   "<script>track()</script>",
    "image": {"imageUrl": "https://i.ebayimg.com/1.jpg"},
    "additionalImages": [{"imageUrl": "https://i.ebayimg.com/2.jpg"}],
}

AUCTION = {
    "itemId": "v1|111|0",
    "legacyItemId": "111",
    "title": "Old radio",
    "price": {"value": "10.00", "currency": "EUR"},
    "currentBidPrice": {"value": "12.50", "currency": "EUR"},
    "bidCount": 3,
    "itemEndDate": "2026-10-09T18:00:00.000Z",
    "buyingOptions": ["AUCTION"],
}


@pytest.fixture
def eb(ebay_server, ebay_client_id):
    base_url, fake = ebay_server
    ebay.init(EbayConfig(client_id=ebay_client_id, client_secret="secret"), api_url=base_url)
    fake.seed_item(ebay_client_id, "820201318060", ITEM)
    fake.seed_item(ebay_client_id, "111", AUCTION)
    return fake


def _db(eb, ebay_client_id):
    return eb.client(ebay_client_id)


# --- get_ebay_listing: input forms -----------------------------------

def test_get_listing_by_bare_item_id(eb):
    result = json.loads(ebay.get_ebay_listing("820201318060"))
    assert result["title"] == "Makita DHP482 Akku-Schlagbohrschrauber"
    assert result["legacy_item_id"] == "820201318060"


def test_get_listing_by_item_url_with_tracking_params(eb):
    url = "https://www.ebay.de/itm/820201318060?mkevt=1&mkcid=16&media=COPY"
    result = json.loads(ebay.get_ebay_listing(url))
    assert result["legacy_item_id"] == "820201318060"


def test_get_listing_by_slugged_item_url(eb):
    result = json.loads(ebay.get_ebay_listing("https://www.ebay.com/itm/makita-drill/820201318060"))
    assert result["legacy_item_id"] == "820201318060"


def test_get_listing_follows_a_short_link(eb, ebay_server):
    base_url, fake = ebay_server
    fake.short_links["abc"] = "https://www.ebay.de/itm/820201318060?mkevt=1"
    result = json.loads(ebay.get_ebay_listing(f"{base_url}/m/abc"))
    assert result["legacy_item_id"] == "820201318060"


def test_get_listing_passes_the_variation_from_the_url(eb, ebay_client_id):
    eb.seed_item(ebay_client_id, "820201318060", {**ITEM, "title": "Blue one"}, variation_id="555")
    result = json.loads(ebay.get_ebay_listing("https://www.ebay.de/itm/820201318060?var=555"))
    assert result["title"] == "Blue one"


def test_get_listing_rejects_input_without_an_item_id(eb):
    with pytest.raises(ValueError, match="item"):
        ebay.get_ebay_listing("https://www.ebay.de/b/Elektrowerkzeuge/bn_123")


def test_get_listing_unknown_item_surfaces_ebays_message(eb):
    with pytest.raises(RuntimeError, match="not found"):
        ebay.get_ebay_listing("999")


# --- marketplace ---------------------------------------------------------

def test_marketplace_comes_from_the_url_domain(eb, ebay_client_id):
    ebay.get_ebay_listing("https://www.ebay.co.uk/itm/820201318060")
    assert _db(eb, ebay_client_id)["requests"][-1]["marketplace"] == "EBAY_GB"


def test_marketplace_falls_back_to_config_default(eb, ebay_client_id):
    ebay.get_ebay_listing("820201318060")
    assert _db(eb, ebay_client_id)["requests"][-1]["marketplace"] == "EBAY_DE"


# --- auth ----------------------------------------------------------------

def test_access_token_is_cached_between_calls(eb, ebay_client_id):
    ebay.get_ebay_listing("820201318060")
    ebay.get_ebay_listing("111")
    ebay.search_ebay("makita")
    assert _db(eb, ebay_client_id)["token_requests"] == 1


def test_unconfigured_raises_a_helpful_error():
    ebay.init(EbayConfig())
    with pytest.raises(AssertionError, match="GATEWAY_EBAY__CLIENT_ID"):
        ebay.get_ebay_listing("820201318060")


# --- get_ebay_listing: shape ---------------------------------------------

def test_listing_summary_shape(eb):
    r = json.loads(ebay.get_ebay_listing("820201318060"))
    assert r["price"] == "89.00 EUR"
    assert r["condition"] == "Gebraucht"
    assert r["condition_description"] == "Leichte Gebrauchsspuren"
    assert r["buying_options"] == ["FIXED_PRICE", "BEST_OFFER"]
    assert r["url"] == "https://www.ebay.de/itm/820201318060"
    assert r["seller"] == {"username": "werkzeugkiste", "feedback_score": 412, "feedback_percentage": "99.8"}
    assert r["location"] == "Berlin, 10*, DE"
    assert r["shipping"] == [{"type": "Standardversand", "cost": "5.99 EUR",
                              "min_delivery": "2026-10-08", "max_delivery": "2026-10-10"}]
    assert r["returns"] == "30 CALENDAR_DAY"
    assert r["item_specifics"] == {"Marke": "Makita", "Modell": "DHP482"}
    assert r["images"] == ["https://i.ebayimg.com/1.jpg", "https://i.ebayimg.com/2.jpg"]
    assert r["marketplace"] == "EBAY_DE"


def test_listing_description_is_plain_text(eb):
    r = json.loads(ebay.get_ebay_listing("820201318060"))
    assert r["description"] == "Ohne Akku & Ladegerät.\nAbholung möglich."


def test_auction_fields(eb):
    r = json.loads(ebay.get_ebay_listing("111"))
    assert r["current_bid"] == "12.50 EUR"
    assert r["bid_count"] == 3
    assert r["end_date"] == "2026-10-09T18:00:00.000Z"


def test_missing_optional_fields_are_none_not_errors(eb):
    r = json.loads(ebay.get_ebay_listing("111"))
    assert r["seller"] is None
    assert r["location"] is None
    assert r["shipping"] == []
    assert r["returns"] is None
    assert r["description"] == ""


# --- search_ebay ---------------------------------------------------------

SUMMARIES = [
    {"itemId": "v1|1|0", "legacyItemId": "1", "title": "Makita drill", "price": {"value": "50.00", "currency": "EUR"},
     "condition": "Gebraucht", "buyingOptions": ["FIXED_PRICE"], "itemWebUrl": "https://www.ebay.de/itm/1",
     "seller": {"username": "a", "feedbackScore": 1, "feedbackPercentage": "100.0"},
     "itemLocation": {"postalCode": "10*", "country": "DE"},
     "shippingOptions": [{"shippingCostType": "FIXED", "shippingCost": {"value": "0.00", "currency": "EUR"}}],
     "image": {"imageUrl": "https://i.ebayimg.com/a.jpg"}},
    {"itemId": "v1|2|0", "legacyItemId": "2", "title": "Makita saw", "price": {"value": "70.00", "currency": "EUR"},
     "currentBidPrice": {"value": "71.00", "currency": "EUR"}, "bidCount": 2, "buyingOptions": ["AUCTION"],
     "itemEndDate": "2026-10-09T18:00:00.000Z"},
    {"itemId": "v1|3|0", "legacyItemId": "3", "title": "Bosch drill"},
]


@pytest.fixture
def seeded_search(eb, ebay_client_id):
    eb.seed_summaries(ebay_client_id, SUMMARIES)
    return eb


def test_search_returns_matching_summaries(seeded_search):
    r = json.loads(ebay.search_ebay("makita"))
    assert r["total"] == 2
    assert [i["title"] for i in r["items"]] == ["Makita drill", "Makita saw"]
    first = r["items"][0]
    assert first["legacy_item_id"] == "1"
    assert first["price"] == "50.00 EUR"
    assert first["shipping_cost"] == "0.00 EUR"
    assert first["location"] == "10*, DE"
    assert first["url"] == "https://www.ebay.de/itm/1"
    assert r["items"][1]["current_bid"] == "71.00 EUR"


def test_search_passes_paging_sort_filter_and_marketplace(seeded_search, ebay_client_id):
    ebay.search_ebay("makita", limit=1, offset=1, sort="price", filter="buyingOptions:{AUCTION}",
                     marketplace="EBAY_GB")
    req = _db(seeded_search, ebay_client_id)["requests"][-1]
    assert req["params"] == {"q": "makita", "limit": "1", "offset": "1", "sort": "price",
                             "filter": "buyingOptions:{AUCTION}"}
    assert req["marketplace"] == "EBAY_GB"


def test_search_omits_empty_optional_params(seeded_search, ebay_client_id):
    ebay.search_ebay("makita")
    req = _db(seeded_search, ebay_client_id)["requests"][-1]
    assert req["params"] == {"q": "makita", "limit": "10", "offset": "0"}
    assert req["marketplace"] == "EBAY_DE"


def test_search_with_no_hits(seeded_search):
    r = json.loads(ebay.search_ebay("nothing-matches"))
    assert r == {"total": 0, "offset": 0, "items": []}


# --- registration ------------------------------------------------------------

async def test_server_registers_the_ebay_tools():
    from gateway.config import Config
    from gateway.main import create_server
    names = {t.name for t in await create_server(Config(_env_file=None)).list_tools()}
    assert {"get_ebay_listing", "search_ebay"} <= names
