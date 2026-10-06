from __future__ import annotations
from unittest.mock import patch
from click.testing import CliRunner
from gateway.cli import main

LISTING = {
    "item_id": "v1|820201318060|0", "legacy_item_id": "820201318060", "title": "Makita DHP482",
    "subtitle": None, "url": "https://www.ebay.de/itm/820201318060", "marketplace": "EBAY_DE",
    "price": "89.00 EUR", "current_bid": None, "bid_count": None, "end_date": None,
    "buying_options": ["FIXED_PRICE"], "condition": "Gebraucht", "condition_description": None,
    "category": None, "seller": {"username": "werkzeugkiste", "feedback_score": 412, "feedback_percentage": "99.8"},
    "location": "Berlin, DE", "shipping": [{"type": "Standard", "cost": "5.99 EUR", "min_delivery": None,
                                             "max_delivery": None}],
    "returns": "30 CALENDAR_DAY", "item_specifics": {"Marke": "Makita"}, "short_description": None,
    "description": "Ohne Akku.", "images": [],
}
SEARCH = {"total": 1, "offset": 0, "items": [{
    "item_id": "v1|1|0", "legacy_item_id": "1", "title": "Makita drill", "price": "50.00 EUR",
    "current_bid": None, "bid_count": None, "end_date": None, "buying_options": ["FIXED_PRICE"],
    "condition": "Gebraucht", "seller": None, "location": "DE", "shipping_cost": "0.00 EUR",
    "url": "https://www.ebay.de/itm/1", "image": None,
}]}

runner = CliRunner()


def test_get():
    with patch("gateway.cli.client.call_tool", return_value=LISTING) as mock:
        r = runner.invoke(main, ["ebay", "get", "https://ebay.io/m/5SMMZb"])
    assert r.exit_code == 0
    assert "Makita DHP482" in r.output
    assert "89.00 EUR" in r.output
    assert "werkzeugkiste" in r.output
    assert "Marke: Makita" in r.output
    assert "Ohne Akku." in r.output
    mock.assert_called_once_with("http://127.0.0.1:4000/mcp", "get_ebay_listing", {"url_or_id": "https://ebay.io/m/5SMMZb"})


def test_search():
    with patch("gateway.cli.client.call_tool", return_value=SEARCH) as mock:
        r = runner.invoke(main, ["ebay", "search", "makita", "--sort", "price", "--filter", "conditions:{USED}"])
    assert r.exit_code == 0
    assert "Makita drill" in r.output
    assert "50.00 EUR" in r.output
    mock.assert_called_once_with("http://127.0.0.1:4000/mcp", "search_ebay", {
        "query": "makita", "limit": 10, "offset": 0, "sort": "price", "filter": "conditions:{USED}", "marketplace": "",
    })


def test_search_no_results():
    with patch("gateway.cli.client.call_tool", return_value={"total": 0, "offset": 0, "items": []}):
        r = runner.invoke(main, ["ebay", "search", "nothing"])
    assert r.exit_code == 0
    assert "No listings." in r.output
