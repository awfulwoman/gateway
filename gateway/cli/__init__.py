from __future__ import annotations
import click


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
