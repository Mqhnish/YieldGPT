"""Optional Slack startup wiring. Configuration refers to environment names only.

No credentials are accepted from HTTP requests or stored in the JSON file. The
corporate identity mapping remains owned by Member 1; it must use the same
TEAM/USER account identifiers configured here.
"""
from __future__ import annotations

import json
import os
import re
from pathlib import Path

from .config import DATA_DIR
from . import slack_oauth
from .sources.slack_events import SlackEventReceiver, SlackEventStore
from .sources.slack_live import SlackLiveConnector

_ENV_NAME = re.compile(r"^[A-Z][A-Z0-9_]{0,127}$")
_ACCOUNT = re.compile(r"^T[A-Z0-9]+/[UW][A-Z0-9]+$")
_ALLOWED = {"team_id", "channels", "ingestion_token_env", "user_token_envs", "signing_secret_env", "app_id",
            "page_limit", "max_pages", "request_timeout"}


def _env_name(value):
    if not isinstance(value, str) or not _ENV_NAME.fullmatch(value):
        raise ValueError("Slack configuration must reference an environment variable name")
    return value


def _required_secret(name):
    value = os.environ.get(_env_name(name), "")
    if not value or not value.strip() or value.upper().startswith(('YOUR_', 'PLACEHOLDER', 'REPLACE', 'CHANGE_ME')):
        raise ValueError("A required Slack credential environment variable is unset")
    return value


def create_live_slack_from_env():
    """Return (connector, receiver) or None when IB_SLACK_CONFIG is unset.

    Malformed configuration, missing secrets, or storage setup errors stop
    startup with fixed messages. No network calls or credential validation occur
    until the connector's normal auth.test boundary; no token values are logged.
    """
    config_path = os.getenv("IB_SLACK_CONFIG", "").strip()
    if not config_path:
        slack_oauth.RUNTIME = None
        return None
    try:
        path = Path(config_path)
        if path.stat().st_size > 65536:
            raise ValueError()
        settings = json.loads(path.read_text(encoding="utf-8"))
    except Exception:
        raise ValueError("Slack configuration file is unreadable or invalid") from None
    if isinstance(settings,dict) and set(settings)=={'workspaces'}:
        rows=settings['workspaces']
        if not isinstance(rows,list) or not 1 <= len(rows) <= 100:
            raise ValueError('Slack configuration requires 1–100 workspaces')
        slack_oauth.configure([row.get('team_id') for row in rows if isinstance(row,dict)])
        built=[]
        try:
            for row in rows:
                built.append(_build_workspace(row))
            from .sources.slack_multi import SlackWorkspaces, SlackWorkspaceEvents
            return SlackWorkspaces([c for c,r in built]), SlackWorkspaceEvents([r for c,r in built])
        except Exception:
            for c,r in built:
                c.client.close()
            raise
    slack_oauth.configure([settings.get('team_id')] if isinstance(settings,dict) else [])
    return _build_workspace(settings)


def _build_workspace(settings):
    if not isinstance(settings, dict) or set(settings) - _ALLOWED:
        raise ValueError("Slack configuration contains unsupported fields")
    try:
        team_id = settings["team_id"]
        channels = settings["channels"]
        env_map = settings["user_token_envs"]
        ingestion_env = _env_name(settings["ingestion_token_env"])
        signing_env = _env_name(settings["signing_secret_env"])
    except (KeyError, TypeError):
        raise ValueError("Slack configuration is missing required fields") from None
    if not isinstance(team_id, str) or not re.fullmatch(r"T[A-Z0-9]+", team_id):
        raise ValueError("Slack configuration has an invalid workspace id")
    if (not isinstance(channels, list) or not channels or len(channels) > 1000
            or not all(isinstance(c, str) and re.fullmatch(r"[CGD][A-Z0-9]+", c) for c in channels)):
        raise ValueError("Slack configuration requires a conversation allowlist")
    if not isinstance(env_map, dict) or (not env_map and slack_oauth.RUNTIME is None):
        raise ValueError("Slack configuration requires delegated user credential mappings")
    for account, env_name in env_map.items():
        if not isinstance(account, str) or not _ACCOUNT.fullmatch(account) or account.split("/", 1)[0] != team_id:
            raise ValueError("Slack delegated account mapping has an invalid workspace or user")
        _required_secret(env_name)
    app_id = settings.get("app_id")
    if app_id is not None and (not isinstance(app_id, str) or not re.fullmatch(r"A[A-Z0-9]+", app_id)):
        raise ValueError("Slack configuration has an invalid application id")
    page_limit, max_pages = settings.get("page_limit", 100), settings.get("max_pages", 100)
    timeout = settings.get("request_timeout", 2.0)
    if (type(page_limit) is not int or type(max_pages) is not int
            or isinstance(timeout, bool) or not isinstance(timeout, (int, float))):
        raise ValueError("Slack configuration has invalid request limits")
    ingestion = _required_secret(ingestion_env)
    signing = _required_secret(signing_env)
    # Keep only validated environment names; read user token values afresh on
    # each request so rotations don't require cached credential invalidation.
    lookup = dict(env_map)
    def resolve(mapped_account):
        if slack_oauth.RUNTIME is not None:
            token = slack_oauth.RUNTIME.credential(mapped_account)
            if token is not None:
                return token
        env_name = lookup.get(mapped_account)
        return os.environ.get(env_name) if env_name else None
    try:
        db_path = os.getenv("IB_SLACK_EVENTS_DB", str(DATA_DIR / "slack-events.db"))
        store = SlackEventStore(db_path)
        connector = SlackLiveConnector(team_id, channels, ingestion, resolve, store,
                                       page_limit=page_limit, max_pages=max_pages, request_timeout=timeout)
        receiver = SlackEventReceiver(store, signing, team_id, channels, app_id=app_id)
    except Exception:
        raise ValueError("Slack connector startup configuration or storage is invalid") from None
    return connector, receiver
