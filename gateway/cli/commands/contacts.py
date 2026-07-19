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


@group.command("create")
@click.argument("name")
@click.option("--nickname", default="")
@click.option("--org", "organisation", default="")
@click.option("--title", "job_title", default="")
@click.option("--emails", default="", help="Comma-separated")
@click.option("--phones", default="", help="Comma-separated")
@click.option("--urls", default="", help="Comma-separated")
@click.option("--birthday", default="", help="YYYY-MM-DD")
@click.option("--address-street", default="")
@click.option("--address-city", default="")
@click.option("--address-state", default="")
@click.option("--address-postal-code", default="")
@click.option("--address-country", default="")
@click.option("--json", "as_json", is_flag=True)
@click.pass_obj
def create(obj: dict, name: str, nickname: str, organisation: str, job_title: str, emails: str, phones: str, urls: str, birthday: str, address_street: str, address_city: str, address_state: str, address_postal_code: str, address_country: str, as_json: bool) -> None:
    """Create a contact."""
    try:
        data = client.call_tool(obj["server"], "create_contact", {
            "name": name, "nickname": nickname, "organisation": organisation, "job_title": job_title,
            "emails": emails, "phones": phones, "urls": urls, "birthday": birthday,
            "address_street": address_street, "address_city": address_city, "address_state": address_state,
            "address_postal_code": address_postal_code, "address_country": address_country,
        })
    except client.GatewayError as e:
        raise click.ClickException(str(e))
    click.echo(json_mod.dumps(data, indent=2) if as_json else f"Created: {data.get('name')}")


@group.command("update")
@click.argument("contact_id")
@click.option("--name", default="")
@click.option("--nickname", default="")
@click.option("--org", "organisation", default="")
@click.option("--title", "job_title", default="")
@click.option("--emails", default="", help="Comma-separated; replaces the existing list")
@click.option("--phones", default="", help="Comma-separated; replaces the existing list")
@click.option("--urls", default="", help="Comma-separated; replaces the existing list")
@click.option("--birthday", default="", help="YYYY-MM-DD")
@click.option("--address-street", default="")
@click.option("--address-city", default="")
@click.option("--address-state", default="")
@click.option("--address-postal-code", default="")
@click.option("--address-country", default="")
@click.option("--json", "as_json", is_flag=True)
@click.pass_obj
def update(obj: dict, contact_id: str, name: str, nickname: str, organisation: str, job_title: str, emails: str, phones: str, urls: str, birthday: str, address_street: str, address_city: str, address_state: str, address_postal_code: str, address_country: str, as_json: bool) -> None:
    """Update a contact by id. Fields left blank keep their existing value."""
    try:
        data = client.call_tool(obj["server"], "update_contact", {
            "id": contact_id, "name": name, "nickname": nickname, "organisation": organisation, "job_title": job_title,
            "emails": emails, "phones": phones, "urls": urls, "birthday": birthday,
            "address_street": address_street, "address_city": address_city, "address_state": address_state,
            "address_postal_code": address_postal_code, "address_country": address_country,
        })
    except client.GatewayError as e:
        raise click.ClickException(str(e))
    click.echo(json_mod.dumps(data, indent=2) if as_json else f"Updated: {data.get('name')}")


@group.command("delete")
@click.argument("contact_id")
@click.option("--json", "as_json", is_flag=True)
@click.pass_obj
def delete(obj: dict, contact_id: str, as_json: bool) -> None:
    """Delete a contact by id."""
    try:
        data = client.call_tool(obj["server"], "delete_contact", {"id": contact_id})
    except client.GatewayError as e:
        raise click.ClickException(str(e))
    click.echo(json_mod.dumps(data, indent=2) if as_json else f"Deleted: {contact_id}")
