from __future__ import annotations
import json as json_mod
import click
from gateway.cli import client, fmt


@click.group()
def group() -> None:
    """Bookmarks (Karakeep)."""


@group.command("search")
@click.argument("query")
@click.option("--limit", default=10, show_default=True)
@click.option("--cursor", default="")
@click.option("--json", "as_json", is_flag=True)
@click.pass_obj
def search(obj: dict, query: str, limit: int, cursor: str, as_json: bool) -> None:
    """Search bookmarks. Supports qualifiers: is:fav, is:archived, #tag, url:value."""
    try:
        data = client.call_tool(obj["server"], "search_bookmarks", {"query": query, "limit": limit, "cursor": cursor})
    except client.GatewayError as e:
        raise click.ClickException(str(e))
    click.echo(json_mod.dumps(data, indent=2) if as_json else fmt.bookmarks(data))


@group.command("get")
@click.argument("bookmark-id")
@click.option("--json", "as_json", is_flag=True)
@click.pass_obj
def get(obj: dict, bookmark_id: str, as_json: bool) -> None:
    """Get a bookmark by ID."""
    try:
        data = client.call_tool(obj["server"], "get_bookmark", {"bookmark_id": bookmark_id})
    except client.GatewayError as e:
        raise click.ClickException(str(e))
    click.echo(json_mod.dumps(data, indent=2) if as_json else fmt.bookmark_detail(data))


@group.command("content")
@click.argument("bookmark-id")
@click.option("--json", "as_json", is_flag=True)
@click.pass_obj
def content(obj: dict, bookmark_id: str, as_json: bool) -> None:
    """Get the full text content of a bookmark."""
    try:
        data = client.call_tool(obj["server"], "get_bookmark_content", {"bookmark_id": bookmark_id})
    except client.GatewayError as e:
        raise click.ClickException(str(e))
    click.echo(json_mod.dumps(data, indent=2) if as_json else data.get("content", ""))


@group.command("create")
@click.argument("url-or-text")
@click.option("--type", "bm_type", default="link", type=click.Choice(["link", "text"]), show_default=True)
@click.option("--title", default="")
@click.option("--json", "as_json", is_flag=True)
@click.pass_obj
def create(obj: dict, url_or_text: str, bm_type: str, title: str, as_json: bool) -> None:
    """Create a bookmark. Defaults to type=link (provide a URL)."""
    try:
        data = client.call_tool(obj["server"], "create_bookmark", {"type": bm_type, "content": url_or_text, "title": title})
    except client.GatewayError as e:
        raise click.ClickException(str(e))
    click.echo(json_mod.dumps(data, indent=2) if as_json else f"Created: {data.get('bookmark', {}).get('id')}")


@group.command("update")
@click.argument("bookmark-id")
@click.option("--title", default="")
@click.option("--note", default="")
@click.option("--archived", default="", type=click.Choice(["true", "false", ""]))
@click.option("--favourited", default="", type=click.Choice(["true", "false", ""]))
@click.option("--json", "as_json", is_flag=True)
@click.pass_obj
def update(obj: dict, bookmark_id: str, title: str, note: str, archived: str, favourited: str, as_json: bool) -> None:
    """Update a bookmark."""
    try:
        data = client.call_tool(obj["server"], "update_bookmark", {"bookmark_id": bookmark_id, "title": title, "note": note, "archived": archived, "favourited": favourited})
    except client.GatewayError as e:
        raise click.ClickException(str(e))
    click.echo(json_mod.dumps(data, indent=2) if as_json else f"Updated: {bookmark_id}")


@group.command("tag")
@click.argument("bookmark-id")
@click.argument("tags")
@click.option("--json", "as_json", is_flag=True)
@click.pass_obj
def tag(obj: dict, bookmark_id: str, tags: str, as_json: bool) -> None:
    """Attach tags to a bookmark. TAGS is comma-separated."""
    try:
        data = client.call_tool(obj["server"], "attach_tags", {"bookmark_id": bookmark_id, "tags": tags})
    except client.GatewayError as e:
        raise click.ClickException(str(e))
    click.echo(json_mod.dumps(data, indent=2) if as_json else f"Tagged: {tags}")


@group.command("untag")
@click.argument("bookmark-id")
@click.argument("tags")
@click.option("--json", "as_json", is_flag=True)
@click.pass_obj
def untag(obj: dict, bookmark_id: str, tags: str, as_json: bool) -> None:
    """Detach tags from a bookmark. TAGS is comma-separated."""
    try:
        data = client.call_tool(obj["server"], "detach_tags", {"bookmark_id": bookmark_id, "tags": tags})
    except client.GatewayError as e:
        raise click.ClickException(str(e))
    click.echo(json_mod.dumps(data, indent=2) if as_json else f"Untagged: {tags}")


@group.command("tags")
@click.option("--json", "as_json", is_flag=True)
@click.pass_obj
def list_tags(obj: dict, as_json: bool) -> None:
    """List all tags."""
    try:
        data = client.call_tool(obj["server"], "list_tags", {})
    except client.GatewayError as e:
        raise click.ClickException(str(e))
    click.echo(json_mod.dumps(data, indent=2) if as_json else fmt.tags(data))


@group.command("lists")
@click.option("--json", "as_json", is_flag=True)
@click.pass_obj
def get_lists(obj: dict, as_json: bool) -> None:
    """List bookmark collections."""
    try:
        data = client.call_tool(obj["server"], "get_lists", {})
    except client.GatewayError as e:
        raise click.ClickException(str(e))
    click.echo(json_mod.dumps(data, indent=2) if as_json else fmt.lists(data))


@group.command("create-list")
@click.argument("name")
@click.argument("icon")
@click.option("--parent", "parent_id", default="")
@click.option("--json", "as_json", is_flag=True)
@click.pass_obj
def create_list(obj: dict, name: str, icon: str, parent_id: str, as_json: bool) -> None:
    """Create a bookmark list. ICON should be an emoji."""
    try:
        data = client.call_tool(obj["server"], "create_list", {"name": name, "icon": icon, "parent_id": parent_id})
    except client.GatewayError as e:
        raise click.ClickException(str(e))
    click.echo(json_mod.dumps(data, indent=2) if as_json else f"Created list: {name} ({data.get('id')})")


@group.command("add-to-list")
@click.argument("list-id")
@click.argument("bookmark-id")
@click.option("--json", "as_json", is_flag=True)
@click.pass_obj
def add_to_list(obj: dict, list_id: str, bookmark_id: str, as_json: bool) -> None:
    """Add a bookmark to a list."""
    try:
        data = client.call_tool(obj["server"], "add_to_list", {"list_id": list_id, "bookmark_id": bookmark_id})
    except client.GatewayError as e:
        raise click.ClickException(str(e))
    click.echo(json_mod.dumps(data, indent=2) if as_json else f"Added {bookmark_id} to list {list_id}")


@group.command("remove-from-list")
@click.argument("list-id")
@click.argument("bookmark-id")
@click.option("--json", "as_json", is_flag=True)
@click.pass_obj
def remove_from_list(obj: dict, list_id: str, bookmark_id: str, as_json: bool) -> None:
    """Remove a bookmark from a list."""
    try:
        data = client.call_tool(obj["server"], "remove_from_list", {"list_id": list_id, "bookmark_id": bookmark_id})
    except client.GatewayError as e:
        raise click.ClickException(str(e))
    click.echo(json_mod.dumps(data, indent=2) if as_json else f"Removed {bookmark_id} from list {list_id}")
