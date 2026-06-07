from __future__ import annotations
import json as json_mod
import click
from gateway.cli import client, fmt


@click.group()
def group() -> None:
    """Email (IMAP)."""


@group.command("folders")
@click.option("--json", "as_json", is_flag=True)
@click.pass_obj
def folders(obj: dict, as_json: bool) -> None:
    """List all IMAP folders."""
    try:
        data = client.call_tool(obj["server"], "list_folders", {})
    except client.GatewayError as e:
        raise click.ClickException(str(e))
    click.echo(json_mod.dumps(data, indent=2) if as_json else fmt.folders(data))


@group.command("list")
@click.option("--folder", default="INBOX", show_default=True)
@click.option("--limit", default=20, show_default=True)
@click.option("--json", "as_json", is_flag=True)
@click.pass_obj
def list_emails(obj: dict, folder: str, limit: int, as_json: bool) -> None:
    """List recent emails in a folder."""
    try:
        data = client.call_tool(obj["server"], "list_emails", {"folder": folder, "max_count": limit})
    except client.GatewayError as e:
        raise click.ClickException(str(e))
    click.echo(json_mod.dumps(data, indent=2) if as_json else fmt.emails(data))


@group.command("unread")
@click.option("--limit", default=10, show_default=True)
@click.option("--json", "as_json", is_flag=True)
@click.pass_obj
def unread(obj: dict, limit: int, as_json: bool) -> None:
    """Fetch unread emails from INBOX."""
    try:
        data = client.call_tool(obj["server"], "fetch_unread_emails", {"max_count": limit})
    except client.GatewayError as e:
        raise click.ClickException(str(e))
    click.echo(json_mod.dumps(data, indent=2) if as_json else fmt.emails(data))


@group.command("search")
@click.argument("query")
@click.option("--in", "search_in", default="all", type=click.Choice(["all", "subject", "from", "body"]), show_default=True)
@click.option("--folder", default="INBOX", show_default=True)
@click.option("--limit", default=20, show_default=True)
@click.option("--json", "as_json", is_flag=True)
@click.pass_obj
def search(obj: dict, query: str, search_in: str, folder: str, limit: int, as_json: bool) -> None:
    """Search emails."""
    try:
        data = client.call_tool(obj["server"], "search_emails", {"query": query, "search_in": search_in, "folder": folder, "max_results": limit})
    except client.GatewayError as e:
        raise click.ClickException(str(e))
    click.echo(json_mod.dumps(data, indent=2) if as_json else fmt.emails(data))


@group.command("read")
@click.argument("message-id")
@click.option("--json", "as_json", is_flag=True)
@click.pass_obj
def read(obj: dict, message_id: str, as_json: bool) -> None:
    """Fetch the full body of an email by Message-ID."""
    try:
        data = client.call_tool(obj["server"], "fetch_email_body", {"message_id": message_id})
    except client.GatewayError as e:
        raise click.ClickException(str(e))
    click.echo(json_mod.dumps(data, indent=2) if as_json else fmt.email_body(data))


@group.command("mark-read")
@click.argument("message-id")
@click.option("--json", "as_json", is_flag=True)
@click.pass_obj
def mark_read(obj: dict, message_id: str, as_json: bool) -> None:
    """Mark an email as read by Message-ID."""
    try:
        data = client.call_tool(obj["server"], "mark_email_read", {"message_id": message_id})
    except client.GatewayError as e:
        raise click.ClickException(str(e))
    click.echo(json_mod.dumps(data, indent=2) if as_json else f"Marked read: {message_id}")
