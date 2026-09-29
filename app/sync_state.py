"""Sync bookkeeping: where each platform's sync left off, and what changed.

Interface owned by Member 1. Durable storage owned by Member 3: `SqliteSyncStateStore`
is a working reference; Member 3 may harden or replace it, as long as it
implements `SyncStateStore`.

What is recorded
- PlatformSyncState, one row per platform: cursor, whether the initial crawl
  finished, last attempt / last success / last error, consecutive failures,
  running counts. The cursor only advances after a batch is fully applied.
- ChangeRecord, one row per applied change: platform, native id, kind
  (upsert / acl / delete), how it arrived (crawl / poll / webhook / read_through),
  when the source says it happened, when we applied it, the resulting version,
  and the outcome (indexed / removed / failed). Deletions are kept as
  tombstones so "was this deleted, and when?" is answerable.
"""
from __future__ import annotations

import json
import sqlite3
import threading
import time
from contextlib import closing
from dataclasses import asdict, dataclass, field
from pathlib import Path
from typing import Protocol


@dataclass
class PlatformSyncState:
    platform: str
    cursor: str = "0"
    initial_load_complete: bool = False
    last_attempt: float = 0.0
    last_success: float = 0.0
    last_error: str = ""
    consecutive_failures: int = 0
    upserts: int = 0
    deletes: int = 0

    def status(self, poll_interval_s: int, now: float | None = None) -> dict:
        now = now or time.time()
        age = now - self.last_success if self.last_success else None
        overdue = age is None or age > 2 * poll_interval_s
        return {**asdict(self),
                "seconds_since_success": round(age) if age is not None else None,
                "overdue": overdue,
                "health": "failing" if self.consecutive_failures else ("stale" if overdue else "ok")}


@dataclass
class ChangeRecord:
    platform: str
    native_id: str
    kind: str                   # upsert | acl | delete
    via: str                    # crawl | poll | webhook | read_through
    source_at: float            # when the platform says it changed (0 if unknown)
    applied_at: float = field(default_factory=time.time)
    version: str = ""
    outcome: str = "indexed"    # indexed | removed | failed
    error: str = ""


class SyncStateStore(Protocol):
    def get(self, platform: str) -> PlatformSyncState | None: ...
    def put(self, state: PlatformSyncState) -> None: ...
    def record(self, change: ChangeRecord) -> None: ...
    def recent(self, platform: str | None = None, outcome: str | None = None, limit: int = 100) -> list[ChangeRecord]: ...
    def tombstone(self, platform: str, native_id: str) -> ChangeRecord | None: ...


class InMemorySyncStateStore:
    def __init__(self):
        self._states: dict[str, PlatformSyncState] = {}
        self._log: list[ChangeRecord] = []
        self._lock = threading.Lock()

    def get(self, platform):
        s = self._states.get(platform)
        return PlatformSyncState(**asdict(s)) if s else None

    def put(self, state):
        with self._lock:
            self._states[state.platform] = PlatformSyncState(**asdict(state))

    def record(self, change):
        with self._lock:
            self._log.append(change)

    def recent(self, platform=None, outcome=None, limit=100):
        rows = [c for c in self._log if (not platform or c.platform == platform) and (not outcome or c.outcome == outcome)]
        return list(reversed(rows))[:limit]

    def tombstone(self, platform, native_id):
        for c in reversed(self._log):
            if c.platform == platform and c.native_id == native_id and c.outcome == "removed":
                return c
        return None


class SqliteSyncStateStore:
    """Durable reference implementation (survives restarts)."""

    def __init__(self, path: Path):
        self.path = path
        self._lock = threading.Lock()
        with closing(self._conn()) as c:
            c.execute("CREATE TABLE IF NOT EXISTS sync_state (platform TEXT PRIMARY KEY, data TEXT NOT NULL)")
            c.execute("""CREATE TABLE IF NOT EXISTS sync_changes (id INTEGER PRIMARY KEY AUTOINCREMENT,
                         platform TEXT, native_id TEXT, outcome TEXT, data TEXT NOT NULL)""")
            c.execute("CREATE INDEX IF NOT EXISTS ix_sc ON sync_changes(platform, native_id)")
            c.commit()

    def _conn(self):
        return sqlite3.connect(self.path)

    def get(self, platform):
        with closing(self._conn()) as c:
            r = c.execute("SELECT data FROM sync_state WHERE platform=?", (platform,)).fetchone()
        return PlatformSyncState(**json.loads(r[0])) if r else None

    def put(self, state):
        with self._lock, closing(self._conn()) as c:
            c.execute("INSERT OR REPLACE INTO sync_state VALUES (?, ?)", (state.platform, json.dumps(asdict(state))))
            c.commit()

    def record(self, change):
        with self._lock, closing(self._conn()) as c:
            c.execute("INSERT INTO sync_changes (platform, native_id, outcome, data) VALUES (?,?,?,?)",
                      (change.platform, change.native_id, change.outcome, json.dumps(asdict(change))))
            c.commit()

    def recent(self, platform=None, outcome=None, limit=100):
        sql, args = "SELECT data FROM sync_changes WHERE 1=1", []
        if platform:
            sql += " AND platform=?"
            args.append(platform)
        if outcome:
            sql += " AND outcome=?"
            args.append(outcome)
        sql += " ORDER BY id DESC LIMIT ?"
        with closing(self._conn()) as c:
            return [ChangeRecord(**json.loads(r[0])) for r in c.execute(sql, args + [limit])]

    def tombstone(self, platform, native_id):
        with closing(self._conn()) as c:
            r = c.execute("SELECT data FROM sync_changes WHERE platform=? AND native_id=? AND outcome='removed' "
                          "ORDER BY id DESC LIMIT 1", (platform, native_id)).fetchone()
        return ChangeRecord(**json.loads(r[0])) if r else None
