"""Keeps the index fresh using ONLY connector-contract methods (no direct platform access).

Three layers, cheapest first:
  1. webhooks   platform pushes a change; applied immediately
  2. polling    every POLL_INTERVAL_S, page through changes_since(cursor); catches missed webhooks
  3. read-through at query time (brain.py): a retrieved doc whose live version differs is
     re-fetched and re-indexed before use

Bookkeeping rules
  - The cursor for the initial crawl is taken BEFORE crawling (contract R8), so edits during
    the crawl are replayed by the first poll.
  - A page of changes is fully applied before the cursor advances. If anything in the page
    fails, the cursor stays put and the whole page is retried next poll (changes are idempotent).
  - A platform outage (SourceUnavailable) is recorded as a failure. It NEVER deletes docs:
    only an explicit delete change or fetch() returning None removes something.
"""
from __future__ import annotations

import threading
import time

from .index import Index
from .sources.base import Connector
from .sync_state import ChangeRecord, InMemorySyncStateStore, PlatformSyncState, SyncStateStore


class Syncer:
    def __init__(self, connectors: dict[str, Connector], index: Index, store: SyncStateStore | None = None):
        self.c = connectors
        self.index = index
        self.store = store or InMemorySyncStateStore()
        self._stop = threading.Event()

    # ------------------------------------------------------------------ state
    def state(self, platform: str) -> PlatformSyncState:
        return self.store.get(platform) or PlatformSyncState(platform)

    def _fail(self, st: PlatformSyncState, err: Exception):
        st.last_error = f"{type(err).__name__}: {err}"
        st.consecutive_failures += 1
        self.store.put(st)

    def _ok(self, st: PlatformSyncState):
        st.last_success = time.time()
        # a connector can succeed but report something a human should look at (e.g. held-back deletions)
        st.last_error = getattr(self.c[st.platform], "anomaly", "") or ""
        st.consecutive_failures = 0
        self.store.put(st)

    # ------------------------------------------------------------------ apply
    def _apply(self, platform: str, native_id: str, kind: str, via: str, source_at: float = 0.0) -> ChangeRecord:
        """Idempotent, fetch-on-notify. The change `kind` is a HINT, never trusted on its own:
        we always fetch current state, and only remove a doc when the platform confirms it's
        gone (fetch() -> None). So a forged, replayed or out-of-order "delete" can't remove a
        live document, and events arriving out of order still converge on the latest state.
        Raises if the platform can't be reached (caller decides what that means)."""
        conn = self.c[platform]
        doc = conn.fetch(native_id)
        if doc is None:
            self.index.remove(conn.uid(native_id))
            rec = ChangeRecord(platform, native_id, "delete", via, source_at, outcome="removed")
        else:
            self.index.upsert(doc, conn.acl_hint(native_id))
            rec = ChangeRecord(platform, native_id, kind, via, source_at, version=doc.version)
        self.store.record(rec)
        return rec

    # ------------------------------------------------------------------ crawl
    def full_load(self, platforms: list[str] | None = None, page_size: int = 50, _then_poll: bool = True) -> int:
        for p in platforms or list(self.c):
            st = self.state(p)
            st.last_attempt = time.time()
            conn = self.c[p]
            try:
                st.cursor = conn.start_cursor()           # R8: before crawling
                token = None
                while True:
                    ids, token = conn.list_page(token, page_size)
                    for nid in ids:
                        self._apply(p, nid, "upsert", "crawl")
                        st.upserts += 1
                    if not token:
                        break
                st.initial_load_complete = True
                self._ok(st)
            except Exception as e:  # noqa: BLE001
                self._fail(st, e)
        if _then_poll:
            self.poll(platforms)  # replay anything that changed during the crawl
        return len(self.index)

    # ------------------------------------------------------------------ poll
    def poll(self, platforms: list[str] | None = None) -> dict[str, int]:
        applied = {}
        for p in platforms or list(self.c):
            st = self.state(p)
            if not st.initial_load_complete:
                # Never incrementally sync on top of a half-finished crawl: finish the crawl first.
                self.full_load([p], _then_poll=False)
                st = self.state(p)
                if not st.initial_load_complete:
                    applied[p] = 0
                    continue
            st.last_attempt = time.time()
            n = 0
            try:
                while True:
                    page = self.c[p].changes_since(st.cursor)
                    for ch in page.changes:
                        rec = self._apply(p, ch.native_id, ch.kind, "poll", ch.at)
                        if rec.outcome == "removed":
                            st.deletes += 1
                        else:
                            st.upserts += 1
                        n += 1
                    st.cursor = page.next_cursor           # only after the whole page applied
                    self.store.put(st)
                    if not page.has_more:
                        break
                self._ok(st)
            except Exception as e:  # noqa: BLE001
                self._fail(st, e)
            applied[p] = n
        return applied

    # ------------------------------------------------------------------ push
    def on_webhook(self, platform: str, native_id: str, kind: str = "upsert"):
        if platform not in self.c:
            return
        try:
            self._apply(platform, native_id, kind, "webhook", time.time())
        except Exception as e:  # noqa: BLE001  (poll will pick it up; never delete on error)
            self.store.record(ChangeRecord(platform, native_id, kind, "webhook", time.time(),
                                           outcome="failed", error=f"{type(e).__name__}: {e}"))

    def record_read_through(self, platform: str, native_id: str, version: str):
        self.store.record(ChangeRecord(platform, native_id, "upsert", "read_through", time.time(), version=version))

    # ------------------------------------------------------------------ loop
    def start_polling(self, interval_s: int):
        def loop():
            while not self._stop.wait(interval_s):
                self.poll()
        threading.Thread(target=loop, daemon=True).start()

    def stop(self):
        self._stop.set()

    def status(self, interval_s: int) -> dict:
        return {p: self.state(p).status(interval_s) for p in self.c}
