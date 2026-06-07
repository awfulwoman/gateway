from __future__ import annotations
import json as json_mod
import click
from gateway.cli import client, fmt


@click.group()
def group() -> None:
    """Contacts."""


@group.command("lookup")
@click.argument("name")
@click.option("--json", "as_json", is_flag=True)
@click.pass_obj
def lookup(obj: dict, name: str, as_json: bool) -> None:
    """Look up contacts by name."""
    try:
        data = client.call_tool(obj["server"], "lookup_contact", {"name": name})
    except client.GatewayError as e:
        raise click.ClickException(str(e))
    click.echo(json_mod.dumps(data, indent=2) if as_json else fmt.contacts(data))


@group.command("search")
@click.argument("query")
@click.option("--json", "as_json", is_flag=True)
@click.pass_obj
def search(obj: dict, query: str, as_json: bool) -> None:
    """Search contacts by name, email, or phone."""
    try:
        data = client.call_tool(obj["server"], "search_contacts", {"query": query})
    except client.GatewayError as e:
        raise click.ClickException(str(e))
    click.echo(json_mod.dumps(data, indent=2) if as_json else fmt.contacts(data))


@group.command("list")
@click.option("--limit", default=50, show_default=True)
@click.option("--json", "as_json", is_flag=True)
@click.pass_obj
def list_contacts(obj: dict, limit: int, as_json: bool) -> None:
    """List contacts alphabetically."""
    try:
        data = client.call_tool(obj["server"], "list_contacts", {"limit": limit})
    except client.GatewayError as e:
        raise click.ClickException(str(e))
    click.echo(json_mod.dumps(data, indent=2) if as_json else fmt.contacts(data))
