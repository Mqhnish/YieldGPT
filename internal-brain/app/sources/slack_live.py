"""Optional read-only Slack Web API connector for a configured workspace estate.

The ingestion credential only discovers/indexes content. Every user-visible read
uses a separately resolved, auth.test-verified delegated USER credential. No
platform token is accepted from a request body, logged, or placed in a URL.
"""
from __future__ import annotations

import hashlib
import json
import re
import time
from collections.abc import Callable

import httpx

from ..identity import User, account_for
from .base import Connector, Decision, SourceDoc, SourceUnavailable
from .slack_events import SlackEventStore, native_id, split_native
from .slack_content import SlackSourceDoc, thread_text

_DENIED = {"channel_not_found", "thread_not_found", "message_not_found", "not_in_channel", "access_denied", "no_permission"}
# Only these fixed strings can reach an exception/audit record. Never copy
# arbitrary platform response text or httpx exception text into diagnostics.
_KNOWN_ERRORS = _DENIED | {"invalid_auth", "token_revoked", "token_expired", "account_inactive", "missing_scope",
                         "ratelimited", "not_authed", "team_access_not_granted", "not_allowed_token_type", "service_unavailable"}


class SlackAPIError(SourceUnavailable):
    def __init__(self, code: str):
        self.code = code if isinstance(code, str) and code in _KNOWN_ERRORS else "source_error"
        super().__init__(f"Slack API unavailable ({self.code})")


class SlackLiveConnector(Connector):
    platform = "slack"

    def __init__(self, team_id: str, channels: list[str], ingestion_token: str,
                 user_token_resolver: Callable[[str], str | None], event_store: SlackEventStore,
                 *, client: httpx.Client | None = None, page_limit: int = 100,
                 max_pages: int = 100, request_timeout: float = 2.0,
                 sleep: Callable[[float], None] = time.sleep):
        if not re.fullmatch(r"T[A-Z0-9]+", team_id):
            raise ValueError("Slack workspace id must be a T-prefixed native id")
        if not channels or any(not re.fullmatch(r"[CGD][A-Z0-9]+", c) for c in channels):
            raise ValueError("Configure explicit Slack conversation ids")
        if not ingestion_token or not callable(user_token_resolver):
            raise ValueError("Slack ingestion credential and user credential resolver required")
        if not 1 <= page_limit <= 200 or not 1 <= max_pages <= 1000:
            raise ValueError("Invalid Slack pagination limits")
        if not 0 < request_timeout <= 10:
            raise ValueError("Invalid Slack timeout")
        self.tenant = team_id
        self.channels = tuple(sorted(set(channels)))
        self._ingestion_token = ingestion_token
        self._resolve_token = user_token_resolver
        self.store = event_store
        self.client = client or httpx.Client(follow_redirects=False)
        self.page_limit, self.max_pages = page_limit, max_pages
        self.request_timeout, self._sleep = request_timeout, sleep

    def _api(self, token: str, method: str, params=None, *, retries: bool = False):
        attempts = 3 if retries else 1
        for attempt in range(attempts):
            try:
                request = self.client.post if method == "auth.test" else self.client.get
                response = request(f"https://slack.com/api/{method}", params=params or {},
                                   headers={"Authorization": f"Bearer {token}"},
                                   timeout=self.request_timeout, follow_redirects=False)
            except Exception:
                raise SourceUnavailable("Slack transport unavailable") from None
            if response.status_code == 429:
                # Never retry sooner than Slack asks, never sleep minutes in a
                # query. The synchronization owner schedules long Retry-After.
                try:
                    delay = float(response.headers.get("Retry-After", "1"))
                except ValueError:
                    delay = 60.0
                if retries and attempt + 1 < attempts and 0 <= delay <= 2:
                    self._sleep(delay)
                    continue
                raise SlackAPIError("ratelimited")
            if response.status_code >= 500 and retries and attempt + 1 < attempts:
                self._sleep(0.2 * (2 ** attempt))
                continue
            if response.status_code != 200:
                raise SourceUnavailable("Slack HTTP request failed")
            try:
                payload = response.json()
            except Exception:
                raise SourceUnavailable("Slack returned an invalid response") from None
            if not isinstance(payload, dict):
                raise SourceUnavailable("Slack returned an invalid response")
            if payload.get("ok") is not True:
                raise SlackAPIError(payload.get("error", "source_error"))
            return payload
        raise SourceUnavailable("Slack retry budget exhausted")

    def _identity(self, token: str, expected_user: str | None = None, *, retries=False):
        identity = self._api(token, "auth.test", retries=retries)
        if identity.get("team_id") != self.tenant:
            raise SourceUnavailable("Slack credential workspace mismatch")
        if expected_user is not None:
            if identity.get("user_id") != expected_user or identity.get("bot_id") or not token.startswith(("xoxp-", "xoxe.xoxp-")):
                raise SourceUnavailable("Slack delegated user identity mismatch")
        return identity

    def _resource(self, nid: str):
        try:
            team, channel, ts = split_native(nid)
        except ValueError:
            return None
        if team != self.tenant or channel not in self.channels:
            return None
        return channel, ts

    def _user_token(self, user: User) -> str | None:
        account = account_for(user, "slack")
        if not account:
            return None
        parts = account.split("/")
        if len(parts) != 2 or parts[0] != self.tenant or not re.fullmatch(r"[UW][A-Z0-9]+", parts[1]):
            return None
        try:
            token = self._resolve_token(account)
        except Exception:
            raise SourceUnavailable("Slack delegated credential unavailable") from None
        if not token:
            raise SourceUnavailable("Slack delegated credential unavailable")
        self._identity(token, parts[1])
        return token

    def _pages(self, token: str, method: str, params: dict, key: str, *, retries=False):
        cursor, seen = "", set()
        for _ in range(self.max_pages):
            data = self._api(token, method, {**params, "limit": self.page_limit, **({"cursor": cursor} if cursor else {})}, retries=retries)
            rows = data.get(key)
            if not isinstance(rows, list) or not all(isinstance(row, dict) for row in rows):
                raise SourceUnavailable("Slack response shape is invalid")
            yield rows
            cursor = (data.get("response_metadata") or {}).get("next_cursor", "").strip()
            if not cursor:
                if data.get("has_more"):
                    # Returning a partial thread as if complete is unsafe.
                    raise SourceUnavailable("Slack pagination was incomplete")
                return
            if cursor in seen:
                raise SourceUnavailable("Slack pagination cursor repeated")
            seen.add(cursor)
        raise SourceUnavailable("Slack pagination budget exceeded")

    def _thread(self, token: str, nid: str, *, retries=False):
        resource = self._resource(nid)
        if not resource:
            return None
        channel, root = resource
        try:
            pages = self._pages(token, "conversations.replies", {"channel": channel, "ts": root}, "messages", retries=retries)
            messages = {}
            for page in pages:
                for message in page:
                    ts = str(message.get("ts", ""))
                    if not re.fullmatch(r"\d+(?:\.\d+)?", ts):
                        continue
                    if message.get("hidden") or message.get("subtype") in {"message_deleted", "tombstone"}:
                        continue
                    if str(message.get("thread_ts", root)) != root:
                        continue
                    # Slack applies retention and source visibility. Do not
                    # restore absent messages from the indexing credential.
                    messages[ts] = {"ts": ts, "user": str(message.get("user") or message.get("bot_id") or "unknown"),
                                    "text": str(message.get("text", "")), "edited": str((message.get("edited") or {}).get("ts", ""))}
        except SlackAPIError as exc:
            if exc.code in _DENIED:
                return None
            raise
        for message in messages.values():
            if not re.fullmatch(r"\d+(?:\.\d+)?", message["edited"]):
                message["edited"] = ""
        ordered = sorted(messages.values(), key=lambda msg: float(msg["ts"]))
        if not ordered or not any(msg["text"].strip() for msg in ordered):
            return None
        version = hashlib.sha256(json.dumps(ordered, sort_keys=True, separators=(",", ":")).encode()).hexdigest()
        updated = max(float(msg["edited"] or msg["ts"]) for msg in ordered)
        # Built from validated native identifiers; never trust a supplied URL.
        url = f"https://app.slack.com/client/{self.tenant}/{channel}/thread/{channel}-{root}"
        self.store.remember(nid, [msg["ts"] for msg in ordered])
        text, spans = thread_text([(f"@{msg['user']} [{msg['ts']}]: {msg['text']}", float(msg["ts"])) for msg in ordered])
        return SlackSourceDoc(self.uid(nid), self.platform, self.tenant, nid, channel,
                         f"Slack conversation {channel} · thread {root}",
                         text,
                         url, version, updated, parent=f"{self.tenant}/{channel}", author=ordered[0]["user"], message_spans=spans)

    def fetch(self, native_id: str) -> SourceDoc | None:
        if not self._resource(native_id):
            return None
        self._identity(self._ingestion_token, retries=True)
        return self._thread(self._ingestion_token, native_id, retries=True)

    def read_authorized(self, user: User, native_id: str) -> SourceDoc | None:
        """Re-fetch as asker immediately before model input and evidence release.

        UNAVAILABLE raises; absent/denied returns None. This intentionally does
        not reuse a cached positive check or an ingestion-token document.
        """
        if not self._resource(native_id):
            return None
        token = self._user_token(user)
        return self._thread(token, native_id) if token else None

    def _check(self, user, account, native_id):
        if not self._resource(native_id):
            return Decision.DENIED, "not_found", "resource unavailable in configured estate", ""
        if account.split("/", 1)[0] != self.tenant:
            return Decision.DENIED, "workspace_mismatch", "linked account belongs to another workspace", ""
        doc = self.read_authorized(user, native_id)
        if doc is None:
            return Decision.DENIED, "not_found", "resource unavailable to mapped account", ""
        return Decision.ALLOWED, "delegated_read", "Slack returned thread for the verified mapped user", doc.version

    def acl_hint(self, native_id: str) -> set[str]:
        # Native user IDs do not share the app's corporate principal namespace.
        # A conservative superset preserves recall; check/read enforce access.
        return {"anyone"}

    def ping(self):
        self._identity(self._ingestion_token)

    def start_cursor(self) -> str:
        return self.store.head()

    def changes_since(self, cursor: str, page_size: int = 100):
        return self.store.changes_since(cursor, page_size)

    def _history_ids(self, channel: str):
        ids = set()
        for page in self._pages(self._ingestion_token, "conversations.history", {"channel": channel}, "messages", retries=True):
            for message in page:
                if message.get("hidden") or message.get("subtype") in {"message_deleted", "tombstone", "channel_join", "channel_leave"}:
                    continue
                ts = str(message.get("thread_ts") or message.get("ts", ""))
                try:
                    ids.add(native_id(self.tenant, channel, ts))
                except ValueError:
                    continue
        return ids

    def list_page(self, page_token=None, page_size=50):
        if page_token:
            return self.store.snapshot_page(None, page_token, page_size)
        self._identity(self._ingestion_token, retries=True)
        ids = set()
        for channel in self.channels:
            ids.update(self._history_ids(channel))
        for nid in ids:
            self.store.remember(nid)
        return self.store.snapshot_page(sorted(ids), None, page_size)

    def reconcile(self) -> int:
        """Missed-event/retention backstop. Schedule outside query requests.

        Successful complete scans enqueue refreshes (including old edited
        threads); incomplete/rate-limited scans raise and never enqueue deletes.
        This is intentionally conservative and must be budgeted for the actual
        installation's API rate limits before claiming a freshness SLA.
        """
        self._identity(self._ingestion_token, retries=True)
        count = 0
        for channel in self.channels:
            ids = self._history_ids(channel)
            self.store.record_reconciliation(self.tenant, channel, ids)
            count += len(ids)
        return count
