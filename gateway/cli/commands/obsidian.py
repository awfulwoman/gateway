from __future__ import annotations
import json as json_mod
import click
from gateway.cli import client, fmt


@click.group()
def group() -> None:
    """Notes (Obsidian vault)."""


@group.command("list")
@click.option("--folder", default="")
@click.option("--json", "as_json", is_flag=True)
@click.pass_obj
def list_notes(obj: dict, folder: str, as_json: bool) -> None:
    """List notes in the vault."""
    try:
        data = client.call_tool(obj["server"], "list_notes", {"folder": folder})
    except client.GatewayError as e:
        raise click.ClickException(str(e))
    click.echo(json_mod.dumps(data, indent=2) if as_json else fmt.notes(data))


@group.command("read")
@click.argument("path")
@click.option("--json", "as_json", is_flag=True)
@click.pass_obj
def read_note(obj: dict, path: str, as_json: bool) -> None:
    """Read a note's content. PATH is relative to the vault root."""
    try:
        data = client.call_tool(obj["server"], "read_note", {"path": path})
    except client.GatewayError as e:
        raise click.ClickException(str(e))
    click.echo(json_mod.dumps(data, indent=2) if as_json else fmt.note_content(data))


@group.command("search")
@click.argument("query")
@click.option("--folder", default="")
@click.option("--json", "as_json", is_flag=True)
@click.pass_obj
def search(obj: dict, query: str, folder: str, as_json: bool) -> None:
    """Search notes by content or title."""
    try:
        data = client.call_tool(obj["server"], "search_notes", {"query": query, "folder": folder})
    except client.GatewayError as e:
        raise click.ClickException(str(e))
    click.echo(json_mod.dumps(data, indent=2) if as_json else fmt.note_search_results(data))


@group.command("create")
@click.argument("path")
@click.argument("content")
@click.option("--json", "as_json", is_flag=True)
@click.pass_obj
def create(obj: dict, path: str, content: str, as_json: bool) -> None:
    """Create a new note. PATH relative to vault root."""
    try:
        data = client.call_tool(obj["server"], "create_note", {"path": path, "content": content})
    except client.GatewayError as e:
        raise click.ClickException(str(e))
    click.echo(json_mod.dumps(data, indent=2) if as_json else f"Created: {path}")


@group.command("update")
@click.argument("path")
@click.argument("content")
@click.option("--json", "as_json", is_flag=True)
@click.pass_obj
def update(obj: dict, path: str, content: str, as_json: bool) -> None:
    """Overwrite a note's content."""
    try:
        data = client.call_tool(obj["server"], "update_note", {"path": path, "content": content})
    except client.GatewayError as e:
        raise click.ClickException(str(e))
    click.echo(json_mod.dumps(data, indent=2) if as_json else f"Updated: {path}")


@group.command("append")
@click.argument("path")
@click.argument("content")
@click.option("--json", "as_json", is_flag=True)
@click.pass_obj
def append(obj: dict, path: str, content: str, as_json: bool) -> None:
    """Append text to a note (creates if absent)."""
    try:
        data = client.call_tool(obj["server"], "append_to_note", {"path": path, "content": content})
    except client.GatewayError as e:
        raise click.ClickException(str(e))
    click.echo(json_mod.dumps(data, indent=2) if as_json else f"Appended to: {path}")


@group.command("move")
@click.argument("path")
@click.argument("dest")
@click.option("--json", "as_json", is_flag=True)
@click.pass_obj
def move(obj: dict, path: str, dest: str, as_json: bool) -> None:
    """Move or rename a note."""
    try:
        data = client.call_tool(obj["server"], "move_note", {"source_path": path, "dest_path": dest})
    except client.GatewayError as e:
        raise click.ClickException(str(e))
    click.echo(json_mod.dumps(data, indent=2) if as_json else f"Moved: {path} → {dest}")


@group.command("delete")
@click.argument("path")
@click.option("--json", "as_json", is_flag=True)
@click.pass_obj
def delete(obj: dict, path: str, as_json: bool) -> None:
    """Delete a note permanently."""
    try:
        data = client.call_tool(obj["server"], "delete_note", {"path": path})
    except client.GatewayError as e:
        raise click.ClickException(str(e))
    click.echo(json_mod.dumps(data, indent=2) if as_json else f"Deleted: {path}")
