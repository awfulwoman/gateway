from __future__ import annotations
import json as json_mod
import click
from gateway.cli import client, fmt


@click.group()
def group() -> None:
    """Reminders."""


@group.command("lists")
@click.option("--json", "as_json", is_flag=True)
@click.pass_obj
def reminder_lists(obj: dict, as_json: bool) -> None:
    """List all reminder lists."""
    try:
        data = client.call_tool(obj["server"], "list_reminder_lists", {})
    except client.GatewayError as e:
        raise click.ClickException(str(e))
    click.echo(json_mod.dumps(data, indent=2) if as_json else fmt.reminder_lists(data))


@group.command("list")
@click.option("--list", "list_name", default="", help="Filter by list name")
@click.option("--completed", "include_completed", is_flag=True)
@click.option("--json", "as_json", is_flag=True)
@click.pass_obj
def list_reminders(obj: dict, list_name: str, include_completed: bool, as_json: bool) -> None:
    """List reminders."""
    try:
        data = client.call_tool(obj["server"], "list_reminders", {"include_completed": include_completed, "list_name": list_name})
    except client.GatewayError as e:
        raise click.ClickException(str(e))
    click.echo(json_mod.dumps(data, indent=2) if as_json else fmt.reminders(data))


@group.command("search")
@click.argument("query")
@click.option("--json", "as_json", is_flag=True)
@click.pass_obj
def search(obj: dict, query: str, as_json: bool) -> None:
    """Search reminders by title or notes."""
    try:
        data = client.call_tool(obj["server"], "search_reminders", {"query": query})
    except client.GatewayError as e:
        raise click.ClickException(str(e))
    click.echo(json_mod.dumps(data, indent=2) if as_json else fmt.reminders(data))


@group.command("create")
@click.argument("title")
@click.option("--list", "list_name", default="")
@click.option("--due", "due_iso", default="")
@click.option("--notes", default="")
@click.option("--priority", default=0, type=int)
@click.option("--location", "location_name", default="")
@click.option("--arrive-or-leave", default="arrive", type=click.Choice(["arrive", "leave"]))
@click.option("--radius", "radius_m", default=150, type=int, help="Geofence radius in metres")
@click.option("--json", "as_json", is_flag=True)
@click.pass_obj
def create(obj: dict, title: str, list_name: str, due_iso: str, notes: str, priority: int, location_name: str, arrive_or_leave: str, radius_m: int, as_json: bool) -> None:
    """Create a reminder."""
    try:
        data = client.call_tool(obj["server"], "create_reminder", {
            "title": title, "due_iso": due_iso, "notes": notes, "list_name": list_name,
            "priority": priority, "location_name": location_name, "arrive_or_leave": arrive_or_leave,
            "radius_m": radius_m,
        })
    except client.GatewayError as e:
        raise click.ClickException(str(e))
    click.echo(json_mod.dumps(data, indent=2) if as_json else f"Created: {data.get('title')}")


@group.command("complete")
@click.argument("title")
@click.option("--json", "as_json", is_flag=True)
@click.pass_obj
def complete(obj: dict, title: str, as_json: bool) -> None:
    """Complete a reminder by title (substring match)."""
    try:
        data = client.call_tool(obj["server"], "complete_reminder", {"title": title})
    except client.GatewayError as e:
        raise click.ClickException(str(e))
    click.echo(json_mod.dumps(data, indent=2) if as_json else f"Completed: {data.get('title')}")


@group.command("delete")
@click.argument("title")
@click.option("--json", "as_json", is_flag=True)
@click.pass_obj
def delete(obj: dict, title: str, as_json: bool) -> None:
    """Delete a reminder by title (substring match)."""
    try:
        data = client.call_tool(obj["server"], "delete_reminder", {"title": title})
    except client.GatewayError as e:
        raise click.ClickException(str(e))
    click.echo(json_mod.dumps(data, indent=2) if as_json else f"Deleted: {data.get('title')}")
