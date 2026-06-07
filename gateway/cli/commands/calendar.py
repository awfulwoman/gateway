from __future__ import annotations
import json as json_mod
import click
from gateway.cli import client, fmt


@click.group()
def group() -> None:
    """Calendar events."""


@group.command("list-calendars")
@click.option("--json", "as_json", is_flag=True)
@click.pass_obj
def list_calendars(obj: dict, as_json: bool) -> None:
    """List available calendars."""
    try:
        data = client.call_tool(obj["server"], "list_calendars", {})
    except client.GatewayError as e:
        raise click.ClickException(str(e))
    click.echo(json_mod.dumps(data, indent=2) if as_json else fmt.calendars(data))


@group.command("list-events")
@click.argument("period")
@click.option("--json", "as_json", is_flag=True)
@click.pass_obj
def list_events(obj: dict, period: str, as_json: bool) -> None:
    """List events. PERIOD: today, tomorrow, week, month, YYYY-MM-DD:YYYY-MM-DD."""
    try:
        data = client.call_tool(obj["server"], "list_calendar_events", {"period": period})
    except client.GatewayError as e:
        raise click.ClickException(str(e))
    click.echo(json_mod.dumps(data, indent=2) if as_json else fmt.calendar_events(data))


@group.command("search")
@click.argument("query")
@click.option("--days-ahead", default=90, show_default=True)
@click.option("--json", "as_json", is_flag=True)
@click.pass_obj
def search(obj: dict, query: str, days_ahead: int, as_json: bool) -> None:
    """Search events by title, location, or notes."""
    try:
        data = client.call_tool(obj["server"], "search_calendar_events", {"query": query, "days_ahead": days_ahead})
    except client.GatewayError as e:
        raise click.ClickException(str(e))
    click.echo(json_mod.dumps(data, indent=2) if as_json else fmt.calendar_events(data))


@group.command("create")
@click.argument("title")
@click.argument("start")
@click.argument("end")
@click.option("--location", default="")
@click.option("--notes", default="")
@click.option("--calendar", "calendar_name", default="")
@click.option("--json", "as_json", is_flag=True)
@click.pass_obj
def create(obj: dict, title: str, start: str, end: str, location: str, notes: str, calendar_name: str, as_json: bool) -> None:
    """Create a calendar event. START and END are ISO 8601 (e.g. 2026-06-08T14:00:00)."""
    try:
        data = client.call_tool(obj["server"], "create_calendar_event", {
            "title": title, "start_iso": start, "end_iso": end,
            "location": location, "notes": notes, "calendar_name": calendar_name,
        })
    except client.GatewayError as e:
        raise click.ClickException(str(e))
    click.echo(json_mod.dumps(data, indent=2) if as_json else f"Created: {data.get('title')} ({data.get('start')})")


@group.command("update")
@click.argument("event-id")
@click.option("--title", default="")
@click.option("--start", default="")
@click.option("--end", default="")
@click.option("--location", default="")
@click.option("--notes", default="")
@click.option("--json", "as_json", is_flag=True)
@click.pass_obj
def update(obj: dict, event_id: str, title: str, start: str, end: str, location: str, notes: str, as_json: bool) -> None:
    """Update fields on an existing event."""
    try:
        data = client.call_tool(obj["server"], "update_calendar_event", {
            "event_id": event_id, "title": title, "start_iso": start,
            "end_iso": end, "location": location, "notes": notes,
        })
    except client.GatewayError as e:
        raise click.ClickException(str(e))
    click.echo(json_mod.dumps(data, indent=2) if as_json else f"Updated: {event_id}")


@group.command("delete")
@click.argument("event-id")
@click.option("--json", "as_json", is_flag=True)
@click.pass_obj
def delete(obj: dict, event_id: str, as_json: bool) -> None:
    """Delete a calendar event by ID."""
    try:
        data = client.call_tool(obj["server"], "delete_calendar_event", {"event_id": event_id})
    except client.GatewayError as e:
        raise click.ClickException(str(e))
    click.echo(json_mod.dumps(data, indent=2) if as_json else f"Deleted: {event_id}")
