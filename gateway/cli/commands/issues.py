from __future__ import annotations
import json as json_mod
import click
from gateway.cli import client, fmt


@click.group()
def group() -> None:
    """Issues (Obsidian vault)."""


@group.command("list")
@click.option("--project", default="")
@click.option("--status", default="")
@click.option("--priority", default=-1, type=int)
@click.option("--label", default="")
@click.option("--json", "as_json", is_flag=True)
@click.pass_obj
def list_issues(obj: dict, project: str, status: str, priority: int, label: str, as_json: bool) -> None:
    """List issues."""
    try:
        data = client.call_tool(obj["server"], "list_issues", {
            "project": project, "status": status, "priority": priority, "label": label,
        })
    except client.GatewayError as e:
        raise click.ClickException(str(e))
    click.echo(json_mod.dumps(data, indent=2) if as_json else fmt.issues(data))


@group.command("get")
@click.argument("issue-id", type=int)
@click.option("--json", "as_json", is_flag=True)
@click.pass_obj
def get_issue(obj: dict, issue_id: int, as_json: bool) -> None:
    """Get an issue by ID."""
    try:
        data = client.call_tool(obj["server"], "get_issue", {"issue_id": issue_id})
    except client.GatewayError as e:
        raise click.ClickException(str(e))
    click.echo(json_mod.dumps(data, indent=2) if as_json else fmt.issue_detail(data))


@group.command("create")
@click.argument("title")
@click.option("--project", default="")
@click.option("--description", default="")
@click.option("--due", default="")
@click.option("--priority", default=0, type=int)
@click.option("--label", "labels", multiple=True)
@click.option("--json", "as_json", is_flag=True)
@click.pass_obj
def create_issue(obj: dict, title: str, project: str, description: str, due: str, priority: int, labels: tuple, as_json: bool) -> None:
    """Create a new issue."""
    try:
        data = client.call_tool(obj["server"], "create_issue", {
            "title": title, "project": project, "description": description,
            "due": due, "priority": priority, "labels": list(labels),
        })
    except client.GatewayError as e:
        raise click.ClickException(str(e))
    click.echo(json_mod.dumps(data, indent=2) if as_json else f"Created: #{data.get('id')} {data.get('title')}")


@group.command("update")
@click.argument("issue-id", type=int)
@click.option("--title", default="")
@click.option("--status", default="", type=click.Choice(["", "open", "in-progress", "done"]))
@click.option("--project", default="")
@click.option("--description", default="")
@click.option("--due", default="")
@click.option("--priority", default=-1, type=int)
@click.option("--json", "as_json", is_flag=True)
@click.pass_obj
def update_issue(obj: dict, issue_id: int, title: str, status: str, project: str, description: str, due: str, priority: int, as_json: bool) -> None:
    """Update an issue. Only supplied options are changed."""
    try:
        data = client.call_tool(obj["server"], "update_issue", {
            "issue_id": issue_id, "title": title, "status": status,
            "project": project, "description": description, "due": due, "priority": priority,
        })
    except client.GatewayError as e:
        raise click.ClickException(str(e))
    click.echo(json_mod.dumps(data, indent=2) if as_json else f"Updated: #{issue_id}")


@group.command("delete")
@click.argument("issue-id", type=int)
@click.option("--json", "as_json", is_flag=True)
@click.pass_obj
def delete_issue(obj: dict, issue_id: int, as_json: bool) -> None:
    """Delete an issue by ID."""
    try:
        data = client.call_tool(obj["server"], "delete_issue", {"issue_id": issue_id})
    except client.GatewayError as e:
        raise click.ClickException(str(e))
    click.echo(json_mod.dumps(data, indent=2) if as_json else f"Deleted: #{issue_id}")
