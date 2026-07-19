from __future__ import annotations
from unittest.mock import patch
from click.testing import CliRunner
from gateway.cli import main

runner = CliRunner()


def test_token_option_configures_client():
    with patch("gateway.cli.client.init") as mock_init, \
         patch("gateway.cli.client.call_tool", return_value=[]):
        r = runner.invoke(main, ["--token", "cli-token", "reminders", "list"])
    assert r.exit_code == 0, r.output
    mock_init.assert_called_once_with("cli-token")


def test_token_env_var_configures_client(monkeypatch):
    monkeypatch.setenv("GATEWAY_TOKEN", "env-token")
    with patch("gateway.cli.client.init") as mock_init, \
         patch("gateway.cli.client.call_tool", return_value=[]):
        r = runner.invoke(main, ["reminders", "list"])
    assert r.exit_code == 0, r.output
    mock_init.assert_called_once_with("env-token")


def test_no_token_configures_empty_string():
    with patch("gateway.cli.client.init") as mock_init, \
         patch("gateway.cli.client.call_tool", return_value=[]):
        r = runner.invoke(main, ["reminders", "list"])
    assert r.exit_code == 0, r.output
    mock_init.assert_called_once_with("")
