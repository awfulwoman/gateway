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
