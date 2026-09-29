"""Shared plumbing for connectors backed by the in-repo simulator (world.py).

Real connectors do NOT use this: they implement start_cursor / list_page /
changes_since against the platform's own APIs (Confluence CQL lastmodified,
Jira JQL updated, Slack Events API + conversations.history, Drive changes.list).
"""
from .base import Change, ChangePage, Connector
from .world import World


class SimulatedConnector(Connector):
    tenant = "companya"

    def __init__(self, world: World):
        self.w = world

    def _ids(self) -> list[str]:
        raise NotImplementedError

    def start_cursor(self) -> str:
        self.w.guard(self.platform)
        return str(self.w.head_seq())

    def list_page(self, page_token=None, page_size=50):
        self.w.guard(self.platform)
        ids = sorted(self._ids())
        start = int(page_token or 0)
        nxt = start + page_size
        return ids[start:nxt], (str(nxt) if nxt < len(ids) else None)

    def changes_since(self, cursor: str, page_size: int = 100) -> ChangePage:
        self.w.guard(self.platform)
        rows = self.w.feed(self.platform, int(cursor or 0))
        page = rows[:page_size]
        next_cursor = str(page[-1][0]) if page else str(cursor or 0)
        return ChangePage([Change(nid, kind, ts) for _, ts, nid, kind in page], next_cursor, len(rows) > page_size)
