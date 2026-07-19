from __future__ import annotations
import click
from gateway.cli import client
from gateway.cli.commands import calendar, reminders, contacts, email, obsidian, karakeep, owntracks, issues


@click.group()
@click.option(
    "--server",
    envvar="GATEWAY_URL",
    default="http://127.0.0.1:4000/mcp",
    show_default=True,
    help="Gateway server URL (or set GATEWAY_URL)",
)
@click.option(
    "--token",
    envvar="GATEWAY_TOKEN",
    default="",
    help="Bearer token for the gateway server (or set GATEWAY_TOKEN)",
)
@click.pass_context
def main(ctx: click.Context, server: str, token: str) -> None:
    """gw — gateway CLI. Requires the gateway server to be running."""
    ctx.ensure_object(dict)
    ctx.obj["server"] = server
    client.init(token)


main.add_command(calendar.group, "calendar")
main.add_command(reminders.group, "reminders")
main.add_command(contacts.group, "contacts")
main.add_command(email.group, "email")
main.add_command(obsidian.group, "notes")
main.add_command(karakeep.group, "bookmarks")
main.add_command(owntracks.group, "location")
main.add_command(issues.group, "issues")
