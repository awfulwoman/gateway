from __future__ import annotations
import json as json_mod
import click
from gateway.cli import client, fmt


@click.group()
def tasks_group() -> None:
    """Issues (Vikunja)."""


@tasks_group.command("list")
@click.option("--project", "project_id", default=0, type=int)
@click.option("--filter", "filter_by", default="")
@click.option("--sort", "sort_by", default="id", type=click.Choice(["id", "title", "due_date", "priority", "created", "updated"]))
@click.option("--order", "order_by", default="asc", type=click.Choice(["asc", "desc"]))
@click.option("--page", default=1)
@click.option("--json", "as_json", is_flag=True)
@click.pass_obj
def list_issues(obj: dict, project_id: int, filter_by: str, sort_by: str, order_by: str, page: int, as_json: bool) -> None:
    """List issues."""
    try:
        data = client.call_tool(obj["server"], "list_issues", {"project_id": project_id, "filter_by": filter_by, "sort_by": sort_by, "order_by": order_by, "page": page})
    except client.GatewayError as e:
        raise click.ClickException(str(e))
    click.echo(json_mod.dumps(data, indent=2) if as_json else fmt.issues(data))


@tasks_group.command("get")
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


@tasks_group.command("create")
@click.argument("title")
@click.option("--project", "project_id", default=0, type=int, help="Project ID; omit to create in Inbox.")
@click.option("--description", default="")
@click.option("--due", "due_date", default="")
@click.option("--priority", default="")
@click.option("--json", "as_json", is_flag=True)
@click.pass_obj
def create_issue(obj: dict, project_id: int, title: str, description: str, due_date: str, priority: str, as_json: bool) -> None:
    """Create an issue. Defaults to Inbox if --project is not given."""
    try:
        data = client.call_tool(obj["server"], "create_issue", {"project_id": project_id, "title": title, "description": description, "due_date": due_date, "priority": priority})
    except client.GatewayError as e:
        raise click.ClickException(str(e))
    click.echo(json_mod.dumps(data, indent=2) if as_json else f"Created: #{data.get('id')} {data.get('title')}")


@tasks_group.command("update")
@click.argument("issue-id", type=int)
@click.option("--title", default="")
@click.option("--description", default="")
@click.option("--done", "done", default="", type=click.Choice(["true", "false", ""]))
@click.option("--due", "due_date", default="")
@click.option("--priority", default="")
@click.option("--json", "as_json", is_flag=True)
@click.pass_obj
def update_issue(obj: dict, issue_id: int, title: str, description: str, done: str, due_date: str, priority: str, as_json: bool) -> None:
    """Update an issue. Only supplied options are changed."""
    try:
        data = client.call_tool(obj["server"], "update_issue", {"issue_id": issue_id, "title": title, "description": description, "done": done, "due_date": due_date, "priority": priority})
    except client.GatewayError as e:
        raise click.ClickException(str(e))
    click.echo(json_mod.dumps(data, indent=2) if as_json else f"Updated: #{issue_id}")


@tasks_group.command("delete")
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


@tasks_group.command("comments")
@click.argument("issue-id", type=int)
@click.option("--json", "as_json", is_flag=True)
@click.pass_obj
def list_comments(obj: dict, issue_id: int, as_json: bool) -> None:
    """List comments on an issue."""
    try:
        data = client.call_tool(obj["server"], "list_issue_comments", {"issue_id": issue_id})
    except client.GatewayError as e:
        raise click.ClickException(str(e))
    click.echo(json_mod.dumps(data, indent=2) if as_json else fmt.comments(data))


@tasks_group.command("comment")
@click.argument("issue-id", type=int)
@click.argument("comment")
@click.option("--json", "as_json", is_flag=True)
@click.pass_obj
def add_comment(obj: dict, issue_id: int, comment: str, as_json: bool) -> None:
    """Add a comment to an issue."""
    try:
        data = client.call_tool(obj["server"], "add_issue_comment", {"issue_id": issue_id, "comment": comment})
    except client.GatewayError as e:
        raise click.ClickException(str(e))
    click.echo(json_mod.dumps(data, indent=2) if as_json else f"Comment added: #{data.get('id')}")


@tasks_group.command("relations")
@click.argument("issue-id", type=int)
@click.option("--json", "as_json", is_flag=True)
@click.pass_obj
def list_relations(obj: dict, issue_id: int, as_json: bool) -> None:
    """List relations for an issue."""
    try:
        data = client.call_tool(obj["server"], "list_issue_relations", {"issue_id": issue_id})
    except client.GatewayError as e:
        raise click.ClickException(str(e))
    if as_json:
        click.echo(json_mod.dumps(data, indent=2))
    elif not data:
        click.echo("No relations.")
    else:
        lines = [f"  {kind}: #{t.get('id')} {t.get('title', '')}" for kind, issues in data.items() for t in issues]
        click.echo("\n".join(lines))


@tasks_group.command("add-relation")
@click.argument("issue-id", type=int)
@click.argument("other-issue-id", type=int)
@click.argument("kind")
@click.option("--json", "as_json", is_flag=True)
@click.pass_obj
def add_relation(obj: dict, issue_id: int, other_issue_id: int, kind: str, as_json: bool) -> None:
    """Add a relation between two issues. KIND: subtask, parenttask, related, blocking, blocked, precedes, follows."""
    try:
        data = client.call_tool(obj["server"], "add_issue_relation", {"issue_id": issue_id, "other_issue_id": other_issue_id, "relation_kind": kind})
    except client.GatewayError as e:
        raise click.ClickException(str(e))
    click.echo(json_mod.dumps(data, indent=2) if as_json else f"Relation added: #{issue_id} {kind} #{other_issue_id}")


@tasks_group.command("remove-relation")
@click.argument("issue-id", type=int)
@click.argument("kind")
@click.argument("other-issue-id", type=int)
@click.option("--json", "as_json", is_flag=True)
@click.pass_obj
def remove_relation(obj: dict, issue_id: int, kind: str, other_issue_id: int, as_json: bool) -> None:
    """Remove a relation between two issues."""
    try:
        data = client.call_tool(obj["server"], "delete_issue_relation", {"issue_id": issue_id, "relation_kind": kind, "other_issue_id": other_issue_id})
    except client.GatewayError as e:
        raise click.ClickException(str(e))
    click.echo(json_mod.dumps(data, indent=2) if as_json else f"Relation removed: #{issue_id} {kind} #{other_issue_id}")


@tasks_group.command("reminders")
@click.argument("issue-id", type=int)
@click.option("--json", "as_json", is_flag=True)
@click.pass_obj
def list_reminders(obj: dict, issue_id: int, as_json: bool) -> None:
    """List reminders for an issue."""
    try:
        data = client.call_tool(obj["server"], "list_issue_reminders", {"issue_id": issue_id})
    except client.GatewayError as e:
        raise click.ClickException(str(e))
    click.echo(json_mod.dumps(data, indent=2) if as_json else ("\n".join(r.get("reminder", "") for r in data) if data else "No reminders."))


@tasks_group.command("set-reminders")
@click.argument("issue-id", type=int)
@click.argument("reminders-json")
@click.option("--json", "as_json", is_flag=True)
@click.pass_obj
def set_reminders(obj: dict, issue_id: int, reminders_json: str, as_json: bool) -> None:
    """Replace all reminders on an issue. REMINDERS-JSON: '[{"reminder":"2026-06-10T09:00:00Z"}]' or '[]' to clear."""
    try:
        data = client.call_tool(obj["server"], "set_issue_reminders", {"issue_id": issue_id, "reminders_json": reminders_json})
    except client.GatewayError as e:
        raise click.ClickException(str(e))
    click.echo(json_mod.dumps(data, indent=2) if as_json else f"Reminders updated: #{issue_id}")


@tasks_group.command("labels")
@click.option("--json", "as_json", is_flag=True)
@click.pass_obj
def list_labels(obj: dict, as_json: bool) -> None:
    """List all available labels."""
    try:
        data = client.call_tool(obj["server"], "list_labels", {})
    except client.GatewayError as e:
        raise click.ClickException(str(e))
    click.echo(json_mod.dumps(data, indent=2) if as_json else ("\n".join(f"#{lbl['id']}  {lbl['title']}" for lbl in data) if data else "No labels."))


@tasks_group.command("add-label")
@click.argument("issue-id", type=int)
@click.argument("label-id", type=int)
@click.option("--json", "as_json", is_flag=True)
@click.pass_obj
def add_label(obj: dict, issue_id: int, label_id: int, as_json: bool) -> None:
    """Attach a label to an issue."""
    try:
        data = client.call_tool(obj["server"], "add_issue_label", {"issue_id": issue_id, "label_id": label_id})
    except client.GatewayError as e:
        raise click.ClickException(str(e))
    click.echo(json_mod.dumps(data, indent=2) if as_json else f"Label #{label_id} added to issue #{issue_id}")


@tasks_group.command("remove-label")
@click.argument("issue-id", type=int)
@click.argument("label-id", type=int)
@click.option("--json", "as_json", is_flag=True)
@click.pass_obj
def remove_label(obj: dict, issue_id: int, label_id: int, as_json: bool) -> None:
    """Remove a label from an issue."""
    try:
        data = client.call_tool(obj["server"], "remove_issue_label", {"issue_id": issue_id, "label_id": label_id})
    except client.GatewayError as e:
        raise click.ClickException(str(e))
    click.echo(json_mod.dumps(data, indent=2) if as_json else f"Label #{label_id} removed from issue #{issue_id}")


# --- Projects ---

@click.group()
def projects_group() -> None:
    """Vikunja projects."""


@projects_group.command("list")
@click.option("--json", "as_json", is_flag=True)
@click.pass_obj
def list_projects(obj: dict, as_json: bool) -> None:
    """List all projects."""
    try:
        data = client.call_tool(obj["server"], "list_projects", {})
    except client.GatewayError as e:
        raise click.ClickException(str(e))
    click.echo(json_mod.dumps(data, indent=2) if as_json else fmt.projects(data))


@projects_group.command("get")
@click.argument("project-id", type=int)
@click.option("--json", "as_json", is_flag=True)
@click.pass_obj
def get_project(obj: dict, project_id: int, as_json: bool) -> None:
    """Get a project by ID."""
    try:
        data = client.call_tool(obj["server"], "get_project", {"project_id": project_id})
    except client.GatewayError as e:
        raise click.ClickException(str(e))
    click.echo(json_mod.dumps(data, indent=2) if as_json else f"#{data['id']}  {data['title']}")


@projects_group.command("create")
@click.argument("title")
@click.option("--description", default="")
@click.option("--parent", "parent_project_id", default=0, type=int)
@click.option("--json", "as_json", is_flag=True)
@click.pass_obj
def create_project(obj: dict, title: str, description: str, parent_project_id: int, as_json: bool) -> None:
    """Create a new project."""
    try:
        data = client.call_tool(obj["server"], "create_project", {"title": title, "description": description, "parent_project_id": parent_project_id})
    except client.GatewayError as e:
        raise click.ClickException(str(e))
    click.echo(json_mod.dumps(data, indent=2) if as_json else f"Created: #{data.get('id')} {data.get('title')}")
