"""Connector registry. The only place that knows which class serves which platform.

Confluence + Jira have three modes (config.ATLASSIAN_MODE):
  sim      simulator classes (confluence.py / jira.py), no HTTP
  fixture  real HTTP connectors (confluence_cloud.py / jira_cloud.py) + fake Atlassian site
  live     real HTTP connectors + a real Atlassian Cloud site (needs IB_ATLASSIAN_* env vars)
Slack and Drive are still simulator-only (owners: Member 2 and Member 3).
"""
from .. import config
from .atlassian_client import AtlassianClient
from .base import Connector
from .confluence import ConfluenceConnector
from .confluence_cloud import ConfluenceCloudConnector
from .fake_atlassian import FakeAtlassian
from .gdrive import DriveConnector
from .jira import JiraConnector
from .jira_cloud import JiraCloudConnector
from .slack import SlackConnector
from .world import World


def atlassian_client(world: World, mode: str) -> AtlassianClient:
    if mode == "fixture":
        return AtlassianClient("https://companya.atlassian.net", transport=FakeAtlassian(world).transport())
    if mode == "live":
        missing = [n for n, v in [("IB_ATLASSIAN_SITE", config.ATLASSIAN_SITE), ("IB_ATLASSIAN_EMAIL", config.ATLASSIAN_EMAIL),
                                  ("IB_ATLASSIAN_API_TOKEN", config.ATLASSIAN_API_TOKEN)] if not v]
        if missing:
            raise RuntimeError(f"live Atlassian mode needs: {', '.join(missing)}")
        return AtlassianClient(config.ATLASSIAN_SITE, config.ATLASSIAN_EMAIL, config.ATLASSIAN_API_TOKEN)
    raise ValueError(f"unknown IB_ATLASSIAN_MODE {mode!r}")


def build_connectors(world: World, atlassian_mode: str | None = None) -> dict[str, Connector]:
    mode = atlassian_mode or config.ATLASSIAN_MODE
    if mode == "sim":
        atl = [ConfluenceConnector(world), JiraConnector(world)]
    else:
        client = atlassian_client(world, mode)
        atl = [ConfluenceCloudConnector(client), JiraCloudConnector(client)]
    cs = atl + [SlackConnector(world), DriveConnector(world)]
    return {c.platform: c for c in cs}
