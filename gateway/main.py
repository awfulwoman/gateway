from __future__ import annotations
import argparse
import logging
import anyio
import uvicorn
from starlette.requests import ClientDisconnect
from mcp.server.fastmcp import FastMCP
from gateway.config import Config
from gateway.http_auth import BearerAuthMiddleware
from gateway.reminders import http as reminders_http
from gateway.tools import calendar, contacts, reminders, email, obsidian, karakeep, owntracks, issues

logger = logging.getLogger("gateway")


class _DisconnectMiddleware:
    def __init__(self, app):
        self._app = app

    async def __call__(self, scope, receive, send):
        if scope["type"] != "http":
            await self._app(scope, receive, send)
            return
        try:
            await self._app(scope, receive, send)
        except ClientDisconnect:
            pass


async def _run_http(mcp: FastMCP, config: Config) -> None:
    if not config.server.auth_tokens:
        logger.warning("MCP HTTP auth DISABLED — set GATEWAY_SERVER__AUTH_TOKENS to require a bearer token on /mcp")
    app = mcp.streamable_http_app()
    app.router.routes.extend(reminders_http.routes)
    app = BearerAuthMiddleware(app, config.server.auth_tokens)
    app = _DisconnectMiddleware(app)
    cfg = uvicorn.Config(
        app,
        host=mcp.settings.host,
        port=mcp.settings.port,
        log_level=mcp.settings.log_level.lower(),
    )
    await uvicorn.Server(cfg).serve()


def create_server(config: Config) -> FastMCP:
    mcp = FastMCP("gateway", host=config.server.host, port=config.server.port, stateless_http=True, json_response=True)

    calendar.init(config.gcal)
    calendar.register(mcp)
    reminders.init(config.reminders, config.reminders_server)
    reminders.register(mcp)
    reminders_http.init(config.reminders)

    contacts.init(config.radicale)
    contacts.register(mcp)

    email.init(config.imap)
    email.register(mcp)

    obsidian.init(config.obsidian)
    obsidian.register(mcp)

    karakeep.init(config.karakeep)
    karakeep.register(mcp)

    owntracks.init(config.owntracks)
    owntracks.register(mcp)

    issues.init(config.obsidian)
    issues.register(mcp)

    return mcp


def main() -> None:
    parser = argparse.ArgumentParser(description="Gateway MCP server")
    parser.add_argument(
        "--transport",
        choices=["stdio", "http"],
        default="http",
        help="Transport mode: 'http' (default, stateless HTTP server) or 'stdio' (for direct Claude Code integration)",
    )
    args = parser.parse_args()

    config = Config()
    mcp = create_server(config)

    if args.transport == "stdio":
        mcp.run(transport="stdio")
    else:
        anyio.run(_run_http, mcp, config)


if __name__ == "__main__":
    main()
