from __future__ import annotations
import click
from gateway.cli.commands import calendar, reminders, contacts, email, obsidian


@click.group()
@click.option(
    "--server",
    envvar="GATEWAY_URL",
    default="http://127.0.0.1:4000/mcp",
    show_default=True,
    help="Gateway server URL (or set GATEWAY_URL)",
)
@click.pass_context
def main(ctx: click.Context, server: str) -> None:
    """gw — gateway CLI. Requires the gateway server to be running."""
    ctx.ensure_object(dict)
    ctx.obj["server"] = server


main.add_command(calendar.group, "calendar")
main.add_command(reminders.group, "reminders")
main.add_command(contacts.group, "contacts")
main.add_command(email.group, "email")
main.add_command(obsidian.group, "notes")
