from __future__ import annotations
import json as json_mod
import click
from gateway.cli import client, fmt


@click.group()
def tasks_group() -> None:
    """Tasks (Vikunja)."""


@tasks_group.command("list")
@click.option("--project", "project_id", default=0, type=int)
@click.option("--filter", "filter_by", default="")
@click.option("--sort", "sort_by", default="id", type=click.Choice(["id", "title", "due_date", "priority", "created", "updated"]))
@click.option("--order", "order_by", default="asc", type=click.Choice(["asc", "desc"]))
@click.option("--page", default=1)
@click.option("--json", "as_json", is_flag=True)
@click.pass_obj
def list_tasks(obj: dict, project_id: int, filter_by: str, sort_by: str, order_by: str, page: int, as_json: bool) -> None:
    """List tasks."""
    try:
        data = client.call_tool(obj["server"], "list_tasks", {"project_id": project_id, "filter_by": filter_by, "sort_by": sort_by, "order_by": order_by, "page": page})
    except client.GatewayError as e:
        raise click.ClickException(str(e))
    click.echo(json_mod.dumps(data, indent=2) if as_json else fmt.tasks(data))


@tasks_group.command("get")
@click.argument("task-id", type=int)
@click.option("--json", "as_json", is_flag=True)
@click.pass_obj
def get_task(obj: dict, task_id: int, as_json: bool) -> None:
    """Get a task by ID."""
    try:
        data = client.call_tool(obj["server"], "get_task", {"task_id": task_id})
    except client.GatewayError as e:
        raise click.ClickException(str(e))
    click.echo(json_mod.dumps(data, indent=2) if as_json else fmt.task_detail(data))


@tasks_group.command("create")
@click.argument("project-id", type=int)
@click.argument("title")
@click.option("--description", default="")
@click.option("--due", "due_date", default="")
@click.option("--priority", default="")
@click.option("--json", "as_json", is_flag=True)
@click.pass_obj
def create_task(obj: dict, project_id: int, title: str, description: str, due_date: str, priority: str, as_json: bool) -> None:
    """Create a task in a project."""
    try:
        data = client.call_tool(obj["server"], "create_task", {"project_id": project_id, "title": title, "description": description, "due_date": due_date, "priority": priority})
    except client.GatewayError as e:
        raise click.ClickException(str(e))
    click.echo(json_mod.dumps(data, indent=2) if as_json else f"Created: #{data.get('id')} {data.get('title')}")


@tasks_group.command("update")
@click.argument("task-id", type=int)
@click.option("--title", default="")
@click.option("--description", default="")
@click.option("--done", "done", default="", type=click.Choice(["true", "false", ""]))
@click.option("--due", "due_date", default="")
@click.option("--priority", default="")
@click.option("--json", "as_json", is_flag=True)
@click.pass_obj
def update_task(obj: dict, task_id: int, title: str, description: str, done: str, due_date: str, priority: str, as_json: bool) -> None:
    """Update a task. Only supplied options are changed."""
    try:
        data = client.call_tool(obj["server"], "update_task", {"task_id": task_id, "title": title, "description": description, "done": done, "due_date": due_date, "priority": priority})
    except client.GatewayError as e:
        raise click.ClickException(str(e))
    click.echo(json_mod.dumps(data, indent=2) if as_json else f"Updated: #{task_id}")


@tasks_group.command("delete")
@click.argument("task-id", type=int)
@click.option("--json", "as_json", is_flag=True)
@click.pass_obj
def delete_task(obj: dict, task_id: int, as_json: bool) -> None:
    """Delete a task by ID."""
    try:
        data = client.call_tool(obj["server"], "delete_task", {"task_id": task_id})
    except client.GatewayError as e:
        raise click.ClickException(str(e))
    click.echo(json_mod.dumps(data, indent=2) if as_json else f"Deleted: #{task_id}")


@tasks_group.command("comments")
@click.argument("task-id", type=int)
@click.option("--json", "as_json", is_flag=True)
@click.pass_obj
def list_comments(obj: dict, task_id: int, as_json: bool) -> None:
    """List comments on a task."""
    try:
        data = client.call_tool(obj["server"], "list_task_comments", {"task_id": task_id})
    except client.GatewayError as e:
        raise click.ClickException(str(e))
    click.echo(json_mod.dumps(data, indent=2) if as_json else fmt.comments(data))


@tasks_group.command("comment")
@click.argument("task-id", type=int)
@click.argument("comment")
@click.option("--json", "as_json", is_flag=True)
@click.pass_obj
def add_comment(obj: dict, task_id: int, comment: str, as_json: bool) -> None:
    """Add a comment to a task."""
    try:
        data = client.call_tool(obj["server"], "add_task_comment", {"task_id": task_id, "comment": comment})
    except client.GatewayError as e:
        raise click.ClickException(str(e))
    click.echo(json_mod.dumps(data, indent=2) if as_json else f"Comment added: #{data.get('id')}")


@tasks_group.command("relations")
@click.argument("task-id", type=int)
@click.option("--json", "as_json", is_flag=True)
@click.pass_obj
def list_relations(obj: dict, task_id: int, as_json: bool) -> None:
    """List relations for a task."""
    try:
        data = client.call_tool(obj["server"], "list_task_relations", {"task_id": task_id})
    except client.GatewayError as e:
        raise click.ClickException(str(e))
    if as_json:
        click.echo(json_mod.dumps(data, indent=2))
    elif not data:
        click.echo("No relations.")
    else:
        lines = [f"  {kind}: #{t.get('id')} {t.get('title', '')}" for kind, tasks in data.items() for t in tasks]
        click.echo("\n".join(lines))


@tasks_group.command("add-relation")
@click.argument("task-id", type=int)
@click.argument("other-task-id", type=int)
@click.argument("kind")
@click.option("--json", "as_json", is_flag=True)
@click.pass_obj
def add_relation(obj: dict, task_id: int, other_task_id: int, kind: str, as_json: bool) -> None:
    """Add a relation between two tasks. KIND: subtask, parenttask, related, blocking, blocked, precedes, follows."""
    try:
        data = client.call_tool(obj["server"], "add_task_relation", {"task_id": task_id, "other_task_id": other_task_id, "relation_kind": kind})
    except client.GatewayError as e:
        raise click.ClickException(str(e))
    click.echo(json_mod.dumps(data, indent=2) if as_json else f"Relation added: #{task_id} {kind} #{other_task_id}")


@tasks_group.command("remove-relation")
@click.argument("task-id", type=int)
@click.argument("kind")
@click.argument("other-task-id", type=int)
@click.option("--json", "as_json", is_flag=True)
@click.pass_obj
def remove_relation(obj: dict, task_id: int, kind: str, other_task_id: int, as_json: bool) -> None:
    """Remove a relation between two tasks."""
    try:
        data = client.call_tool(obj["server"], "delete_task_relation", {"task_id": task_id, "relation_kind": kind, "other_task_id": other_task_id})
    except client.GatewayError as e:
        raise click.ClickException(str(e))
    click.echo(json_mod.dumps(data, indent=2) if as_json else f"Relation removed: #{task_id} {kind} #{other_task_id}")


@tasks_group.command("reminders")
@click.argument("task-id", type=int)
@click.option("--json", "as_json", is_flag=True)
@click.pass_obj
def list_reminders(obj: dict, task_id: int, as_json: bool) -> None:
    """List reminders for a task."""
    try:
        data = client.call_tool(obj["server"], "list_task_reminders", {"task_id": task_id})
    except client.GatewayError as e:
        raise click.ClickException(str(e))
    click.echo(json_mod.dumps(data, indent=2) if as_json else ("\n".join(r.get("reminder", "") for r in data) if data else "No reminders."))


@tasks_group.command("set-reminders")
@click.argument("task-id", type=int)
@click.argument("reminders-json")
@click.option("--json", "as_json", is_flag=True)
@click.pass_obj
def set_reminders(obj: dict, task_id: int, reminders_json: str, as_json: bool) -> None:
    """Replace all reminders on a task. REMINDERS-JSON: '[{"reminder":"2026-06-10T09:00:00Z"}]' or '[]' to clear."""
    try:
        data = client.call_tool(obj["server"], "set_task_reminders", {"task_id": task_id, "reminders_json": reminders_json})
    except client.GatewayError as e:
        raise click.ClickException(str(e))
    click.echo(json_mod.dumps(data, indent=2) if as_json else f"Reminders updated: #{task_id}")


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
@click.argument("task-id", type=int)
@click.argument("label-id", type=int)
@click.option("--json", "as_json", is_flag=True)
@click.pass_obj
def add_label(obj: dict, task_id: int, label_id: int, as_json: bool) -> None:
    """Attach a label to a task."""
    try:
        data = client.call_tool(obj["server"], "add_task_label", {"task_id": task_id, "label_id": label_id})
    except client.GatewayError as e:
        raise click.ClickException(str(e))
    click.echo(json_mod.dumps(data, indent=2) if as_json else f"Label #{label_id} added to task #{task_id}")


@tasks_group.command("remove-label")
@click.argument("task-id", type=int)
@click.argument("label-id", type=int)
@click.option("--json", "as_json", is_flag=True)
@click.pass_obj
def remove_label(obj: dict, task_id: int, label_id: int, as_json: bool) -> None:
    """Remove a label from a task."""
    try:
        data = client.call_tool(obj["server"], "remove_task_label", {"task_id": task_id, "label_id": label_id})
    except client.GatewayError as e:
        raise click.ClickException(str(e))
    click.echo(json_mod.dumps(data, indent=2) if as_json else f"Label #{label_id} removed from task #{task_id}")


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
