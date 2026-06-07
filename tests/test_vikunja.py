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
