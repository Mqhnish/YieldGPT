"""Connector registry. The only place that knows which class serves which platform."""
from .base import Connector
from .confluence import ConfluenceConnector
from .gdrive import DriveConnector
from .jira import JiraConnector
from .slack import SlackConnector
from .world import World


def build_connectors(world: World) -> dict[str, Connector]:
    cs = [ConfluenceConnector(world), JiraConnector(world), SlackConnector(world), DriveConnector(world)]
    return {c.platform: c for c in cs}
