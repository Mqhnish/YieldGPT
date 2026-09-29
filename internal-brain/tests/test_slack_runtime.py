"""Optional Slack startup config does not disclose secrets or change demo defaults."""
import json

import httpx
import pytest

from app.slack_runtime import create_live_slack_from_env


def config(tmp_path, monkeypatch, **overrides):
    settings = {"team_id": "TTEAM", "channels": ["CDEMO"], "ingestion_token_env": "TEST_SLACK_INGESTION",
                "user_token_envs": {"TTEAM/UJANE": "TEST_SLACK_JANE"}, "signing_secret_env": "TEST_SLACK_SIGNING",
                "app_id": "ATEST"}
    settings.update(overrides)
    path = tmp_path / "slack.json"
    path.write_text(json.dumps(settings))
    monkeypatch.setenv("IB_SLACK_CONFIG", str(path))
    monkeypatch.setenv("IB_SLACK_EVENTS_DB", str(tmp_path / "feed.db"))
    monkeypatch.setenv("TEST_SLACK_INGESTION", "xoxp-do-not-print-ingestion")
    monkeypatch.setenv("TEST_SLACK_JANE", "xoxp-do-not-print-jane")
    monkeypatch.setenv("TEST_SLACK_SIGNING", "do-not-print-signing")
    return settings, path


def test_optional_config_defaults_to_demo(monkeypatch):
    monkeypatch.delenv("IB_SLACK_CONFIG", raising=False)
    assert create_live_slack_from_env() is None


def test_valid_config_builds_without_network_and_rotates_user_tokens(tmp_path, monkeypatch):
    config(tmp_path, monkeypatch)
    def no_network(*args, **kwargs):
        raise AssertionError("Startup must not make network requests")
    monkeypatch.setattr(httpx.Client, "request", no_network)
    connector, receiver = create_live_slack_from_env()
    assert connector.tenant == "TTEAM" and connector.channels == ("CDEMO",)
    assert receiver.team_id == "TTEAM" and receiver.app_id == "ATEST"
    assert connector._resolve_token("TTEAM/UJANE") == "xoxp-do-not-print-jane"
    assert connector._resolve_token("TTEAM/UOTHER") is None
    monkeypatch.setenv("TEST_SLACK_JANE", "xoxp-rotated-user")
    assert connector._resolve_token("TTEAM/UJANE") == "xoxp-rotated-user"
    connector.client.close()


@pytest.mark.parametrize("change", [
    {"user_token_envs": {"TOTHER/UJANE": "TEST_SLACK_JANE"}},
    {"user_token_envs": {}},
    {"ingestion_token_env": "xoxp-actual-secret-must-not-print"},
    {"signing_secret_env": ""},
    {"channels": ["https://evil.example"]},
    {"channels": "CDEMO"},
    {"page_limit": True},
    {"max_pages": -1},
    {"request_timeout": "xoxp-secret"},
    {"app_id": "bad/app"},
    {"token": "xoxp-actual-secret-must-not-print"},
])
def test_invalid_config_fails_safely(tmp_path, monkeypatch, change):
    config(tmp_path, monkeypatch, **change)
    with pytest.raises(ValueError) as exc:
        create_live_slack_from_env()
    assert "xoxp" not in str(exc.value)
    assert "do-not-print" not in str(exc.value)


def test_missing_user_secret_stops_startup(tmp_path, monkeypatch):
    config(tmp_path, monkeypatch)
    monkeypatch.delenv("TEST_SLACK_JANE")
    with pytest.raises(ValueError, match="credential environment variable is unset"):
        create_live_slack_from_env()


def test_unreadable_malformed_config_uses_safe_error(tmp_path, monkeypatch):
    _, path = config(tmp_path, monkeypatch)
    path.write_text('{"secret": "xoxp-do-not-print"')
    with pytest.raises(ValueError) as exc:
        create_live_slack_from_env()
    assert "xoxp" not in str(exc.value)
    path.unlink()
    with pytest.raises(ValueError, match="unreadable or invalid"):
        create_live_slack_from_env()
