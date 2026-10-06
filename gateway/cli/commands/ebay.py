from __future__ import annotations
import json as json_mod
import click
from gateway.cli import client, fmt


@click.group()
def group() -> None:
    """eBay listings (Browse API)."""


@group.command("get")
@click.argument("url-or-id")
@click.option("--json", "as_json", is_flag=True)
@click.pass_obj
def get(obj: dict, url_or_id: str, as_json: bool) -> None:
    """Get a listing by URL, short link (ebay.io/m/...) or item ID."""
    try:
        data = client.call_tool(obj["server"], "get_ebay_listing", {"url_or_id": url_or_id})
    except client.GatewayError as e:
        raise click.ClickException(str(e))
    click.echo(json_mod.dumps(data, indent=2) if as_json else fmt.ebay_listing(data))


@group.command("search")
@click.argument("query")
@click.option("--limit", default=10, show_default=True)
@click.option("--offset", default=0, show_default=True)
@click.option("--sort", default="", help="price, -price, newlyListed, endingSoonest")
@click.option("--filter", "filter_", default="", help='Browse API filter, e.g. "conditions:{USED}"')
@click.option("--marketplace", default="", help="e.g. EBAY_DE, EBAY_GB (default from server config)")
@click.option("--json", "as_json", is_flag=True)
@click.pass_obj
def search(obj: dict, query: str, limit: int, offset: int, sort: str, filter_: str, marketplace: str,
           as_json: bool) -> None:
    """Search listings by keyword."""
    try:
        data = client.call_tool(obj["server"], "search_ebay", {
            "query": query, "limit": limit, "offset": offset, "sort": sort, "filter": filter_,
            "marketplace": marketplace,
        })
    except client.GatewayError as e:
        raise click.ClickException(str(e))
    click.echo(json_mod.dumps(data, indent=2) if as_json else fmt.ebay_search(data))
