from __future__ import annotations
import argparse
import logging
import sys
from logging.handlers import RotatingFileHandler
import anyio
import uvicorn
from starlette.requests import ClientDisconnect
from mcp.server.fastmcp import FastMCP
from gateway import auth
from gateway.config import Config
from gateway.http_auth import BearerAuthMiddleware
from gateway.reminders import http as reminders_http
from gateway.tools import calendar, contacts, reminders, email, obsidian, karakeep, owntracks, issues, repos
from gateway.usage import UsageLogMiddleware

logger = logging.getLogger("gateway")


def configure_logging(config: Config) -> None:
    root = logging.getLogger("gateway")
    if not root.handlers:
        h = logging.StreamHandler(sys.stdout)
        h.setFormatter(logging.Formatter("%(levelname)s %(name)s %(message)s"))
        root.addHandler(h)
        root.setLevel(logging.INFO)
        root.propagate = False  # our own handler; don't double through uvicorn's root

    usage = logging.getLogger("gateway.usage")
    usage.handlers.clear()
    usage.propagate = False
    usage.setLevel(logging.INFO)
    stream = logging.StreamHandler(sys.stdout)
    stream.setFormatter(logging.Formatter("usage %(message)s"))
    usage.addHandler(stream)
    if config.usage_log.path:
        rotating = RotatingFileHandler(
            config.usage_log.path,
            maxBytes=config.usage_log.max_bytes,
            backupCount=config.usage_log.backups,
        )
        rotating.setFormatter(logging.Formatter("%(message)s"))
        usage.addHandler(rotating)


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
    configure_logging(config)
    clients = auth.parse_clients(config.server.auth_tokens)
    if not clients:
        logger.warning("MCP HTTP auth DISABLED — set GATEWAY_SERVER__AUTH_TOKENS to require a bearer token on /mcp")
    app = mcp.streamable_http_app()
    app.router.routes.extend(reminders_http.routes)
    app = BearerAuthMiddleware(app, clients)
    if config.usage_log.enabled:
        app = UsageLogMiddleware(app, clients)
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

    calendar.init(config.calendar_server)
    calendar.register(mcp)
    reminders.init(config.reminders, config.reminders_server)
    reminders.register(mcp)
    reminders_http.init(config.reminders)

    contacts.init(config.contacts_server)
    contacts.register(mcp)

    email.init(config.mail_archive_server)
    email.register(mcp)

    obsidian.init(config.obsidian)
    obsidian.register(mcp)

    karakeep.init(config.karakeep)
    karakeep.register(mcp)

    owntracks.init(config.owntracks)
    owntracks.register(mcp)

    issues.init(config.github)
    issues.register(mcp)

    repos.init(config.github)
    repos.register(mcp)

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
        configure_logging(config)
        mcp.run(transport="stdio")
    else:
        anyio.run(_run_http, mcp, config)


if __name__ == "__main__":
    main()
