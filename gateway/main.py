from __future__ import annotations
import argparse
from mcp.server.fastmcp import FastMCP
from gateway.config import Config
from gateway.tools import calendar, reminders, contacts, email, obsidian, karakeep, owntracks, vikunja


def create_server(config: Config) -> FastMCP:
    mcp = FastMCP("gateway", host=config.server.host, port=config.server.port, stateless_http=True)

    calendar.register(mcp)
    reminders.register(mcp)
    contacts.register(mcp)

    email.init(config.imap)
    email.register(mcp)

    obsidian.init(config.obsidian)
    obsidian.register(mcp)

    karakeep.init(config.karakeep)
    karakeep.register(mcp)

    owntracks.init(config.owntracks)
    owntracks.register(mcp)

    vikunja.init(config.vikunja)
    vikunja.register(mcp)

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
        mcp.run(transport="streamable-http")


if __name__ == "__main__":
    main()
