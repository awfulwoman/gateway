from __future__ import annotations
import json as json_mod
import click
from gateway.cli import client, fmt


@click.group()
def group() -> None:
    """Email (mail-archive-server)."""


@group.command("list")
@click.option("--account", default="", help="omit for every account in scope")
@click.option("--since", default="")
@click.option("--until", default="")
@click.option("--order", default="date_desc", type=click.Choice(["date_desc", "date_asc"]), show_default=True)
@click.option("--cursor", default="", help="continue a previous walk")
@click.option("--limit", default=20, show_default=True)
@click.option("--json", "as_json", is_flag=True)
@click.pass_obj
def list_emails(obj: dict, account: str, since: str, until: str, order: str, cursor: str, limit: int, as_json: bool) -> None:
    """List emails in date order."""
    try:
        data = client.call_tool(obj["server"], "list_emails",
                                 {"account": account, "since": since, "until": until, "order": order,
                                  "cursor": cursor, "limit": limit})
    except client.GatewayError as e:
        raise click.ClickException(str(e))
    click.echo(json_mod.dumps(data, indent=2) if as_json else fmt.emails(data))


@group.command("unread")
@click.option("--limit", default=10, show_default=True)
@click.option("--json", "as_json", is_flag=True)
@click.pass_obj
def unread(obj: dict, limit: int, as_json: bool) -> None:
    """Fetch unread emails across every account in scope."""
    try:
        data = client.call_tool(obj["server"], "fetch_unread_emails", {"limit": limit})
    except client.GatewayError as e:
        raise click.ClickException(str(e))
    click.echo(json_mod.dumps(data, indent=2) if as_json else fmt.emails(data))


@group.command("search")
@click.argument("query")
@click.option("--account", default="", help="omit for every account in scope")
@click.option("--sender", default="")
@click.option("--subject", default="")
@click.option("--since", default="")
@click.option("--until", default="")
@click.option("--order", default="date_desc", type=click.Choice(["date_desc", "date_asc"]), show_default=True)
@click.option("--cursor", default="", help="continue a previous walk")
@click.option("--limit", default=20, show_default=True)
@click.option("--json", "as_json", is_flag=True)
@click.pass_obj
def search(obj: dict, query: str, account: str, sender: str, subject: str, since: str, until: str,
           order: str, cursor: str, limit: int, as_json: bool) -> None:
    """Search emails."""
    try:
        data = client.call_tool(obj["server"], "search_emails",
                                 {"query": query, "account": account, "sender": sender, "subject": subject,
                                  "since": since, "until": until, "order": order, "cursor": cursor, "limit": limit})
    except client.GatewayError as e:
        raise click.ClickException(str(e))
    click.echo(json_mod.dumps(data, indent=2) if as_json else fmt.emails(data))


@group.command("read")
@click.argument("id")
@click.option("--json", "as_json", is_flag=True)
@click.pass_obj
def read(obj: dict, id: str, as_json: bool) -> None:
    """Fetch the full body of an email by its mail-archive-server id."""
    try:
        data = client.call_tool(obj["server"], "fetch_email_body", {"id": id})
    except client.GatewayError as e:
        raise click.ClickException(str(e))
    click.echo(json_mod.dumps(data, indent=2) if as_json else fmt.email_body(data))


@group.command("mark-read")
@click.argument("id")
@click.option("--json", "as_json", is_flag=True)
@click.pass_obj
def mark_read(obj: dict, id: str, as_json: bool) -> None:
    """Mark an email as read. Local to the archive only for now -- does not
    yet reach the real mailbox over IMAP (mail-archive-server#3)."""
    try:
        data = client.call_tool(obj["server"], "mark_email_read", {"id": id})
    except client.GatewayError as e:
        raise click.ClickException(str(e))
    if as_json:
        click.echo(json_mod.dumps(data, indent=2))
    else:
        click.echo(f"Marked read (local only, not yet synced upstream): {id}")


@group.command("accounts")
@click.option("--json", "as_json", is_flag=True)
@click.pass_obj
def accounts(obj: dict, as_json: bool) -> None:
    """List mail accounts the gateway can see, with sync health."""
    try:
        data = client.call_tool(obj["server"], "list_email_accounts", {})
    except client.GatewayError as e:
        raise click.ClickException(str(e))
    if as_json:
        click.echo(json_mod.dumps(data, indent=2))
    else:
        click.echo("\n".join(a["name"] for a in data) if data else "No accounts.")
