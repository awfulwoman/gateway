from __future__ import annotations
import json as json_mod
import click
from gateway.cli import client, fmt


@click.group()
def group() -> None:
    """Location (OwnTracks)."""


@group.command("current")
@click.option("--user", default="")
@click.option("--device", default="")
@click.option("--json", "as_json", is_flag=True)
@click.pass_obj
def current(obj: dict, user: str, device: str, as_json: bool) -> None:
    """Get the most recent known location."""
    try:
        data = client.call_tool(obj["server"], "get_current_location", {"user": user, "device": device})
    except client.GatewayError as e:
        raise click.ClickException(str(e))
    click.echo(json_mod.dumps(data, indent=2) if as_json else fmt.location(data))


@group.command("history")
@click.option("--from", "from_time", default="")
@click.option("--to", "to_time", default="")
@click.option("--user", default="")
@click.option("--device", default="")
@click.option("--limit", default=100, show_default=True)
@click.option("--json", "as_json", is_flag=True)
@click.pass_obj
def history(obj: dict, from_time: str, to_time: str, user: str, device: str, limit: int, as_json: bool) -> None:
    """Get location history."""
    try:
        data = client.call_tool(obj["server"], "get_location_history", {"from_time": from_time, "to_time": to_time, "user": user, "device": device, "limit": limit})
    except client.GatewayError as e:
        raise click.ClickException(str(e))
    click.echo(json_mod.dumps(data, indent=2) if as_json else fmt.location_history(data))


@group.command("devices")
@click.option("--json", "as_json", is_flag=True)
@click.pass_obj
def devices(obj: dict, as_json: bool) -> None:
    """List all tracked users and devices."""
    try:
        data = client.call_tool(obj["server"], "list_tracked_devices", {})
    except client.GatewayError as e:
        raise click.ClickException(str(e))
    click.echo(json_mod.dumps(data, indent=2) if as_json else fmt.devices(data))
