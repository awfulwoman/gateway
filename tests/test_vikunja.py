import json
from unittest.mock import MagicMock, patch
from gateway.config import Config, VikunjaConfig
import gateway.tools.vikunja as vikunja


def test_vikunja_config_defaults():
    c = Config()
    assert c.vikunja.base_url == ""
    assert c.vikunja.api_token == ""


def test_vikunja_config_from_env(monkeypatch):
    monkeypatch.setenv("GATEWAY_VIKUNJA__BASE_URL", "https://vikunja.example.com")
    monkeypatch.setenv("GATEWAY_VIKUNJA__API_TOKEN", "tok-abc123")
    c = Config()
    assert c.vikunja.base_url == "https://vikunja.example.com"
    assert c.vikunja.api_token == "tok-abc123"


def _make_mock_client():
    """Returns a mock httpx client usable as context manager."""
    mock_client = MagicMock()
    mock_client.__enter__ = MagicMock(return_value=mock_client)
    mock_client.__exit__ = MagicMock(return_value=False)
    return mock_client


def test_client_raises_when_not_configured():
    vikunja.init(VikunjaConfig(base_url="", api_token=""))
    import pytest
    with pytest.raises(AssertionError):
        vikunja._client()


def test_list_projects():
    vikunja.init(VikunjaConfig(base_url="http://test", api_token="tok"))
    mock_client = _make_mock_client()
    mock_client.get.return_value.json.return_value = [
        {"id": 1, "title": "Inbox", "description": "", "is_archived": False, "parent_project_id": 0},
        {"id": 2, "title": "Work", "description": "Work tasks", "is_archived": False, "parent_project_id": 0},
    ]
    with patch("gateway.tools.vikunja.httpx.Client", return_value=mock_client):
        result = json.loads(vikunja.list_projects())
    assert len(result) == 2
    assert result[0]["id"] == 1
    assert result[0]["title"] == "Inbox"


def test_get_project():
    vikunja.init(VikunjaConfig(base_url="http://test", api_token="tok"))
    mock_client = _make_mock_client()
    mock_client.get.return_value.json.return_value = {
        "id": 1, "title": "Inbox", "description": "", "is_archived": False, "parent_project_id": 0
    }
    with patch("gateway.tools.vikunja.httpx.Client", return_value=mock_client):
        result = json.loads(vikunja.get_project(1))
    assert result["id"] == 1
    mock_client.get.assert_called_once_with("/projects/1")


def test_create_project():
    vikunja.init(VikunjaConfig(base_url="http://test", api_token="tok"))
    mock_client = _make_mock_client()
    mock_client.put.return_value.json.return_value = {
        "id": 3, "title": "New Project", "description": "", "is_archived": False, "parent_project_id": 0
    }
    with patch("gateway.tools.vikunja.httpx.Client", return_value=mock_client):
        result = json.loads(vikunja.create_project("New Project"))
    assert result["id"] == 3
    assert result["title"] == "New Project"
    mock_client.put.assert_called_once_with("/projects", json={"title": "New Project"})


def test_create_project_with_parent():
    vikunja.init(VikunjaConfig(base_url="http://test", api_token="tok"))
    mock_client = _make_mock_client()
    mock_client.put.return_value.json.return_value = {
        "id": 4, "title": "Sub", "description": "desc", "is_archived": False, "parent_project_id": 1
    }
    with patch("gateway.tools.vikunja.httpx.Client", return_value=mock_client):
        result = json.loads(vikunja.create_project("Sub", description="desc", parent_project_id=1))
    assert result["parent_project_id"] == 1
    mock_client.put.assert_called_once_with(
        "/projects", json={"title": "Sub", "description": "desc", "parent_project_id": 1}
    )


def test_list_tasks_no_filter():
    vikunja.init(VikunjaConfig(base_url="http://test", api_token="tok"))
    mock_client = _make_mock_client()
    mock_client.get.return_value.json.return_value = [
        {"id": 10, "title": "Buy milk", "description": "", "done": False,
         "due_date": None, "priority": 0, "project_id": 1, "labels": []}
    ]
    with patch("gateway.tools.vikunja.httpx.Client", return_value=mock_client):
        result = json.loads(vikunja.list_tasks())
    assert result[0]["id"] == 10
    mock_client.get.assert_called_once_with("/tasks", params={"sort_by": "id", "order_by": "asc", "page": 1})


def test_list_tasks_with_project_id():
    vikunja.init(VikunjaConfig(base_url="http://test", api_token="tok"))
    mock_client = _make_mock_client()
    mock_client.get.return_value.json.return_value = []
    with patch("gateway.tools.vikunja.httpx.Client", return_value=mock_client):
        vikunja.list_tasks(project_id=5)
    call_params = mock_client.get.call_args[1]["params"]
    assert call_params["filter"] == "project_id=5"


def test_list_tasks_project_id_combined_with_filter():
    vikunja.init(VikunjaConfig(base_url="http://test", api_token="tok"))
    mock_client = _make_mock_client()
    mock_client.get.return_value.json.return_value = []
    with patch("gateway.tools.vikunja.httpx.Client", return_value=mock_client):
        vikunja.list_tasks(project_id=5, filter_by="done=false")
    call_params = mock_client.get.call_args[1]["params"]
    assert call_params["filter"] == "project_id=5 && done=false"


def test_get_task():
    vikunja.init(VikunjaConfig(base_url="http://test", api_token="tok"))
    mock_client = _make_mock_client()
    mock_client.get.return_value.json.return_value = {
        "id": 10, "title": "Buy milk", "description": "", "done": False,
        "due_date": None, "priority": 0, "project_id": 1, "labels": [],
        "reminders": [], "related_tasks": {}
    }
    with patch("gateway.tools.vikunja.httpx.Client", return_value=mock_client):
        result = json.loads(vikunja.get_task(10))
    assert result["id"] == 10
    mock_client.get.assert_called_once_with("/tasks/10")


def test_create_task():
    vikunja.init(VikunjaConfig(base_url="http://test", api_token="tok"))
    mock_client = _make_mock_client()
    mock_client.put.return_value.json.return_value = {
        "id": 11, "title": "New task", "description": "", "done": False,
        "due_date": None, "priority": 0, "project_id": 1, "labels": []
    }
    with patch("gateway.tools.vikunja.httpx.Client", return_value=mock_client):
        result = json.loads(vikunja.create_task(project_id=1, title="New task"))
    assert result["id"] == 11
    mock_client.put.assert_called_once_with("/projects/1/tasks", json={"title": "New task"})


def test_update_task_partial():
    vikunja.init(VikunjaConfig(base_url="http://test", api_token="tok"))
    mock_client = _make_mock_client()
    mock_client.post.return_value.json.return_value = {
        "id": 10, "title": "Buy oat milk", "done": False, "description": "",
        "due_date": None, "priority": 0, "project_id": 1, "labels": []
    }
    with patch("gateway.tools.vikunja.httpx.Client", return_value=mock_client):
        result = json.loads(vikunja.update_task(10, title="Buy oat milk"))
    assert result["title"] == "Buy oat milk"
    mock_client.post.assert_called_once_with("/tasks/10", json={"title": "Buy oat milk"})


def test_update_task_done():
    vikunja.init(VikunjaConfig(base_url="http://test", api_token="tok"))
    mock_client = _make_mock_client()
    mock_client.post.return_value.json.return_value = {
        "id": 10, "title": "Buy milk", "done": True, "description": "",
        "due_date": None, "priority": 0, "project_id": 1, "labels": []
    }
    with patch("gateway.tools.vikunja.httpx.Client", return_value=mock_client):
        vikunja.update_task(10, done="true")
    mock_client.post.assert_called_once_with("/tasks/10", json={"done": True})


def test_delete_task():
    vikunja.init(VikunjaConfig(base_url="http://test", api_token="tok"))
    mock_client = _make_mock_client()
    mock_client.delete.return_value.json.return_value = {"message": "The task was successfully deleted."}
    with patch("gateway.tools.vikunja.httpx.Client", return_value=mock_client):
        result = json.loads(vikunja.delete_task(10))
    assert result["status"] == "deleted"
    mock_client.delete.assert_called_once_with("/tasks/10")


def test_list_labels():
    vikunja.init(VikunjaConfig(base_url="http://test", api_token="tok"))
    mock_client = _make_mock_client()
    mock_client.get.return_value.json.return_value = [
        {"id": 1, "title": "urgent", "hex_color": "ff0000", "description": ""},
        {"id": 2, "title": "home", "hex_color": "", "description": ""},
    ]
    with patch("gateway.tools.vikunja.httpx.Client", return_value=mock_client):
        result = json.loads(vikunja.list_labels())
    assert len(result) == 2
    assert result[0]["id"] == 1
    assert result[0]["title"] == "urgent"
    mock_client.get.assert_called_once_with("/labels")


def test_add_task_label():
    vikunja.init(VikunjaConfig(base_url="http://test", api_token="tok"))
    mock_client = _make_mock_client()
    mock_client.put.return_value.json.return_value = {"label_id": 1, "created": "2024-01-01T00:00:00Z"}
    with patch("gateway.tools.vikunja.httpx.Client", return_value=mock_client):
        result = json.loads(vikunja.add_task_label(task_id=10, label_id=1))
    assert result["status"] == "added"
    mock_client.put.assert_called_once_with("/tasks/10/labels", json={"label_id": 1})


def test_remove_task_label():
    vikunja.init(VikunjaConfig(base_url="http://test", api_token="tok"))
    mock_client = _make_mock_client()
    mock_client.delete.return_value.json.return_value = {"message": "success"}
    with patch("gateway.tools.vikunja.httpx.Client", return_value=mock_client):
        result = json.loads(vikunja.remove_task_label(task_id=10, label_id=1))
    assert result["status"] == "removed"
    mock_client.delete.assert_called_once_with("/tasks/10/labels/1")


def test_list_task_comments():
    vikunja.init(VikunjaConfig(base_url="http://test", api_token="tok"))
    mock_client = _make_mock_client()
    mock_client.get.return_value.json.return_value = [
        {"id": 1, "comment": "First note", "created": "2024-01-01T00:00:00Z",
         "author": {"username": "charlie"}}
    ]
    with patch("gateway.tools.vikunja.httpx.Client", return_value=mock_client):
        result = json.loads(vikunja.list_task_comments(10))
    assert result[0]["id"] == 1
    assert result[0]["comment"] == "First note"
    mock_client.get.assert_called_once_with("/tasks/10/comments")


def test_add_task_comment():
    vikunja.init(VikunjaConfig(base_url="http://test", api_token="tok"))
    mock_client = _make_mock_client()
    mock_client.put.return_value.json.return_value = {
        "id": 2, "comment": "Follow up needed", "created": "2024-01-02T00:00:00Z",
        "author": {"username": "charlie"}
    }
    with patch("gateway.tools.vikunja.httpx.Client", return_value=mock_client):
        result = json.loads(vikunja.add_task_comment(10, "Follow up needed"))
    assert result["id"] == 2
    mock_client.put.assert_called_once_with("/tasks/10/comments", json={"comment": "Follow up needed"})


def test_list_task_relations():
    vikunja.init(VikunjaConfig(base_url="http://test", api_token="tok"))
    mock_client = _make_mock_client()
    mock_client.get.return_value.json.return_value = {
        "id": 10, "title": "Task A", "description": "", "done": False,
        "due_date": None, "priority": 0, "project_id": 1, "labels": [],
        "reminders": [],
        "related_tasks": {"subtask": [{"id": 11, "title": "Sub A"}]}
    }
    with patch("gateway.tools.vikunja.httpx.Client", return_value=mock_client):
        result = json.loads(vikunja.list_task_relations(10))
    assert "subtask" in result
    assert result["subtask"][0]["id"] == 11


def test_add_task_relation():
    vikunja.init(VikunjaConfig(base_url="http://test", api_token="tok"))
    mock_client = _make_mock_client()
    mock_client.put.return_value.json.return_value = {
        "task_id": 10, "other_task_id": 11, "relation_kind": "subtask", "created": "2024-01-01T00:00:00Z"
    }
    with patch("gateway.tools.vikunja.httpx.Client", return_value=mock_client):
        result = json.loads(vikunja.add_task_relation(10, 11, "subtask"))
    assert result["status"] == "created"
    mock_client.put.assert_called_once_with(
        "/tasks/10/relations", json={"other_task_id": 11, "relation_kind": "subtask"}
    )


def test_delete_task_relation():
    vikunja.init(VikunjaConfig(base_url="http://test", api_token="tok"))
    mock_client = _make_mock_client()
    mock_client.delete.return_value.json.return_value = {"message": "success"}
    with patch("gateway.tools.vikunja.httpx.Client", return_value=mock_client):
        result = json.loads(vikunja.delete_task_relation(10, "subtask", 11))
    assert result["status"] == "deleted"
    mock_client.delete.assert_called_once_with("/tasks/10/relations/subtask/11")
