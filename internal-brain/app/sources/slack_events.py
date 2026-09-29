"""Durable Slack event metadata feed. Contains no message bodies or credentials."""
from __future__ import annotations

import hashlib
import hmac
import json
import math
import re
import sqlite3
import time
import uuid
from pathlib import Path

from .base import Change, ChangePage

_ID = re.compile(r"^[A-Z0-9]+$")
_TS = re.compile(r"^\d+(?:\.\d+)?$")


def native_id(team: str, channel: str, ts: str) -> str:
    if not _ID.fullmatch(team) or not _ID.fullmatch(channel) or not _TS.fullmatch(ts):
        raise ValueError("Invalid Slack resource identifier")
    return f"{team}/{channel}/{ts}"


def split_native(value: str) -> tuple[str, str, str]:
    try:
        team, channel, ts = value.split("/")
        native_id(team, channel, ts)
        return team, channel, ts
    except (ValueError, TypeError, AttributeError):
        raise ValueError("Invalid Slack resource identifier") from None


class SlackEventStore:
    """SQLite event cursor, dedup keys, snapshots and message-to-thread routing.

    Incoming webhooks commit dedup and changes in one transaction. The source's
    normal polling loop consumes changes_since(); reconciliation is a separate
    scheduled operation, because Slack has no generic changes cursor.
    """
    def __init__(self, path: str | Path):
        self.path = str(path)
        if self.path == ":memory:":
            raise ValueError("Slack event store requires a persistent file")
        Path(self.path).parent.mkdir(parents=True, exist_ok=True)
        with self._db() as db:
            db.executescript("""
                CREATE TABLE IF NOT EXISTS slack_events (
                    team TEXT NOT NULL, event_id TEXT NOT NULL, received REAL NOT NULL,
                    PRIMARY KEY(team, event_id));
                CREATE TABLE IF NOT EXISTS slack_changes (
                    seq INTEGER PRIMARY KEY AUTOINCREMENT, native_id TEXT NOT NULL,
                    kind TEXT NOT NULL, at REAL NOT NULL);
                CREATE TABLE IF NOT EXISTS slack_threads (
                    native_id TEXT PRIMARY KEY, team TEXT NOT NULL, channel TEXT NOT NULL);
                CREATE TABLE IF NOT EXISTS slack_messages (
                    team TEXT NOT NULL, channel TEXT NOT NULL, ts TEXT NOT NULL, root TEXT NOT NULL,
                    PRIMARY KEY(team, channel, ts));
                CREATE TABLE IF NOT EXISTS slack_crawls (
                    id TEXT PRIMARY KEY, created REAL NOT NULL, ids TEXT NOT NULL);
            """)

    def _db(self):
        return sqlite3.connect(self.path, timeout=5)

    def head(self) -> str:
        with self._db() as db:
            return str(db.execute("SELECT COALESCE(MAX(seq),0) FROM slack_changes").fetchone()[0])

    def changes_since(self, cursor: str, page_size: int = 100) -> ChangePage:
        if not 1 <= page_size <= 1000:
            raise ValueError("Invalid Slack page size")
        with self._db() as db:
            rows = db.execute("SELECT seq,native_id,kind,at FROM slack_changes WHERE seq>? ORDER BY seq LIMIT ?",
                              (int(cursor or 0), page_size + 1)).fetchall()
        page = rows[:page_size]
        return ChangePage([Change(nid, kind, at) for _, nid, kind, at in page],
                          str(page[-1][0]) if page else str(cursor or 0), len(rows) > page_size)

    def remember(self, nid: str, message_ts=()):
        team, channel, root = split_native(nid)
        with self._db() as db:
            db.execute("INSERT OR IGNORE INTO slack_threads VALUES (?,?,?)", (nid, team, channel))
            for ts in message_ts:
                if _TS.fullmatch(str(ts)):
                    db.execute("INSERT OR REPLACE INTO slack_messages VALUES (?,?,?,?)", (team, channel, ts, root))

    def known(self, team: str, channel: str) -> set[str]:
        with self._db() as db:
            return {r[0] for r in db.execute("SELECT native_id FROM slack_threads WHERE team=? AND channel=?", (team, channel))}

    def record_reconciliation(self, team: str, channel: str, current: set[str]):
        """Only call after a COMPLETE successful channel scan; outages never delete."""
        with self._db() as db:
            old = {r[0] for r in db.execute("SELECT native_id FROM slack_threads WHERE team=? AND channel=?", (team, channel))}
            for nid in sorted(current | old):
                db.execute("INSERT INTO slack_changes(native_id,kind,at) VALUES (?,?,?)",
                           (nid, "upsert" if nid in current else "delete", time.time()))
            db.execute("DELETE FROM slack_threads WHERE team=? AND channel=?", (team, channel))
            db.executemany("INSERT INTO slack_threads VALUES (?,?,?)", [(nid, team, channel) for nid in sorted(current)])

    def snapshot_page(self, ids: list[str] | None, token: str | None, page_size: int):
        if not 1 <= page_size <= 1000:
            raise ValueError("Invalid Slack page size")
        with self._db() as db:
            if token is None:
                snapshot, offset = uuid.uuid4().hex, 0
                db.execute("INSERT INTO slack_crawls VALUES (?,?,?)", (snapshot, time.time(), json.dumps(sorted(set(ids or [])))))
            else:
                snapshot, offset_text = token.split(":", 1)
                offset = int(offset_text)
                if offset < 0:
                    raise ValueError("Invalid Slack crawl cursor")
            row = db.execute("SELECT ids FROM slack_crawls WHERE id=?", (snapshot,)).fetchone()
            if not row:
                raise ValueError("Unknown Slack crawl cursor")
            all_ids = json.loads(row[0])
            end = offset + page_size
            return all_ids[offset:end], f"{snapshot}:{end}" if end < len(all_ids) else None

    def accept(self, payload: dict, team: str, allowed_channels: frozenset[str]) -> bool:
        """Persist a previously authenticated Events API envelope once."""
        event_id = payload.get("event_id")
        if not isinstance(event_id, str) or not event_id or len(event_id) > 200:
            raise ValueError("Slack event id missing")
        event = payload.get("event")
        if not isinstance(event, dict):
            raise ValueError("Slack event missing")
        channel = event.get("channel", "")
        if isinstance(channel, dict):
            channel = channel.get("id", "")
        if not isinstance(channel, str) or not isinstance(event.get("type"), str):
            raise ValueError("Invalid Slack event shape")
        stamp = payload.get("event_time", time.time())
        if type(stamp) not in (int, float) or not math.isfinite(stamp) or stamp < 0:
            raise ValueError("Invalid Slack event timestamp")
        with self._db() as db:
            inserted = db.execute("INSERT OR IGNORE INTO slack_events VALUES (?,?,?)", (team, event_id, time.time())).rowcount
            if not inserted:
                return False
            if channel not in allowed_channels:
                return True
            changes = []
            event_type = event.get("type")
            if event_type == "message":
                subtype = event.get("subtype")
                if subtype is not None and not isinstance(subtype, str):
                    raise ValueError("Invalid Slack message event")
                msg = event.get("message", {}) if subtype == "message_changed" else event
                if subtype == "message_deleted":
                    msg = event.get("previous_message", {})
                if not isinstance(msg, dict):
                    raise ValueError("Invalid Slack message event")
                ts = str(msg.get("ts") or event.get("deleted_ts") or "")
                if not _TS.fullmatch(ts):
                    return True
                root = msg.get("thread_ts")
                if not root:
                    row = db.execute("SELECT root FROM slack_messages WHERE team=? AND channel=? AND ts=?",
                                     (team, channel, ts)).fetchone()
                    root = row[0] if row else ts
                nid = native_id(team, channel, str(root))
                kind = "delete" if subtype == "message_deleted" and str(root) == ts else "upsert"
                changes.append((nid, kind))
                # Unknown deleted reply: refresh every known thread as a safe
                # fallback, never leave stale content because routing was absent.
                if subtype == "message_deleted" and not msg.get("thread_ts"):
                    changes.extend((r[0], "upsert") for r in db.execute(
                        "SELECT native_id FROM slack_threads WHERE team=? AND channel=? AND native_id!=?", (team, channel, nid)))
                if kind != "delete":
                    db.execute("INSERT OR IGNORE INTO slack_threads VALUES (?,?,?)", (nid, team, channel))
                    db.execute("INSERT OR REPLACE INTO slack_messages VALUES (?,?,?,?)", (team, channel, ts, str(root)))
            elif event_type in {"member_joined_channel", "member_left_channel", "channel_shared", "channel_unshared",
                                "channel_archive", "channel_unarchive", "group_archive", "group_unarchive", "channel_deleted"}:
                kind = "delete" if event_type == "channel_deleted" else "acl"
                changes = [(r[0], kind) for r in db.execute(
                    "SELECT native_id FROM slack_threads WHERE team=? AND channel=?", (team, channel))]
            at = float(stamp)
            for nid, kind in dict(changes).items():
                db.execute("INSERT INTO slack_changes(native_id,kind,at) VALUES (?,?,?)", (nid, kind, at))
            return True


class SlackEventReceiver:
    """Framework-independent receiver; call with RAW bytes before JSON decoding."""
    def __init__(self, store: SlackEventStore, signing_secret: str, team_id: str,
                 channels, app_id: str | None = None, clock=time.time):
        if not signing_secret:
            raise ValueError("Slack signing secret required")
        self.store, self._secret, self.team_id = store, signing_secret.encode(), team_id
        self.channels, self.app_id, self.clock = frozenset(channels), app_id, clock

    def receive(self, body: bytes, headers) -> dict:
        if len(body) > 1_000_000:
            raise ValueError("Slack event body too large")
        normalized = {k.lower(): v for k, v in headers.items()}
        stamp = normalized.get("x-slack-request-timestamp", "")
        signature = normalized.get("x-slack-signature", "")
        try:
            if abs(self.clock() - int(stamp)) > 300:
                raise ValueError()
            expected = "v0=" + hmac.new(self._secret, b"v0:" + stamp.encode() + b":" + body, hashlib.sha256).hexdigest()
            if not hmac.compare_digest(expected, signature):
                raise ValueError()
        except (ValueError, TypeError, AttributeError):
            raise ValueError("Invalid Slack request signature") from None
        try:
            payload = json.loads(body)
        except (ValueError, UnicodeError, RecursionError):
            raise ValueError("Invalid Slack event body") from None
        if not isinstance(payload, dict):
            raise ValueError("Invalid Slack event body")
        # Slack's signed URL challenge does not carry a workspace identity.
        if payload.get("type") == "url_verification":
            challenge = payload.get("challenge")
            if not isinstance(challenge, str) or len(challenge) > 1000:
                raise ValueError("Invalid Slack challenge")
            return {"challenge": challenge}
        if payload.get("team_id") != self.team_id or (self.app_id and payload.get("api_app_id") != self.app_id):
            raise ValueError("Slack event installation mismatch")
        if payload.get("type") != "event_callback":
            return {"ok": True, "ignored": True}
        accepted = self.store.accept(payload, self.team_id, self.channels)
        return {"ok": True, "duplicate": not accepted}
