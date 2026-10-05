"""Shared change-detection engine for SaaS APIs that only offer "updated since" search.

Confluence (CQL `lastmodified`) and Jira (JQL `updated`) both:
  - accept date literals with MINUTE precision, interpreted in the API user's timezone
  - never return deleted items in search results

So the cursor is not a single timestamp. It is JSON:
  since  platform timestamp of the newest change we've emitted
  seen   (id, version) pairs inside the overlap window, so re-queried items aren't re-emitted
  dseq   last deletion sequence number emitted

Every query starts OVERLAP_S before `since` (floored to the minute), which absorbs minute
rounding and small clock/timezone skew. Duplicates are filtered by (id, version), so
replaying the same cursor returns the same changes (contract R7).

Deletions are found by RECONCILIATION: list all current ids, diff against the ids we
know about, emit "delete" for the missing ones. That runs every RECONCILE_EVERY_S.
Deletions between reconciliations are still never SERVED, because every retrieval goes
through a live permission check and a fresh fetch, and both treat 404 as gone.

Safety valve: if one reconciliation would delete more than MASS_DELETE_FRACTION of
everything we know (and more than MASS_DELETE_MIN items), those deletions are HELD, not
emitted. That pattern almost always means a truncated listing or a lost integration
permission, not a real mass deletion. Edits keep flowing (freshness isn't blocked), the
anomaly is exposed as `anomaly` and sync health shows "degraded" until a human either
fixes the cause or sets IB_ALLOW_MASS_DELETE=1 for one poll.
"""
from __future__ import annotations

import json
import threading
import time
from abc import abstractmethod

from .. import config
from .base import Change, ChangePage, Connector

OVERLAP_S = 180
MASS_DELETE_FRACTION = 0.2
MASS_DELETE_MIN = 5


class CloudPollingConnector(Connector):
    def __init__(self):
        self._known: set[str] = set()
        self._tombs: list[tuple[int, str, float]] = []  # (seq, native_id, detected_at)
        self._tomb_seq = 0
        self._last_reconcile = 0.0
        self._poll_lock = threading.Lock()   # background poller and manual "poll now" can overlap
        self.anomaly = ""                     # set when a reconciliation is held back

    # ---- implemented by each platform ------------------------------------
    @abstractmethod
    def _all_ids(self) -> set[str]:
        """Every current id (cheap id-only listing)."""

    @abstractmethod
    def _updated_since(self, ts: float) -> list[tuple[str, str, float]]:
        """(native_id, version, updated_ts) for items updated at/after ts (minute precision is fine)."""

    # ---- contract methods --------------------------------------------------
    def start_cursor(self) -> str:
        now = time.time()
        self._known = self._all_ids()          # baseline for deletion detection (also proves reachability)
        self._last_reconcile = now
        return json.dumps({"since": now, "seen": [], "dseq": self._tomb_seq})

    def changes_since(self, cursor: str, page_size: int = 100) -> ChangePage:
        with self._poll_lock:
            return self._changes_since(cursor)

    def _changes_since(self, cursor: str) -> ChangePage:
        c = self._parse(cursor)
        # After a restart the in-memory sequence is back at 0 but the persisted cursor isn't:
        # continue numbering from the cursor so new deletions are never hidden behind it.
        self._tomb_seq = max(self._tomb_seq, c["dseq"])
        since, seen = c["since"], {tuple(x) for x in c["seen"]}

        results = self._updated_since(since - OVERLAP_S)
        fresh = [(i, v, t) for i, v, t in results if (i, v) not in seen]
        new_since = max([since] + [t for _, _, t in results])
        keep = [[i, v] for i, v, t in results if t >= new_since - OVERLAP_S - 60]
        self._known |= {i for i, _, _ in results}

        self._maybe_reconcile()
        deletes = [(s, i, at) for s, i, at in self._tombs if s > c["dseq"]]

        changes = [Change(i, "upsert", t) for i, v, t in sorted(fresh, key=lambda x: x[2])]
        changes += [Change(i, "delete", at) for _, i, at in deletes]
        nxt = {"since": new_since, "seen": keep, "dseq": max([c["dseq"]] + [s for s, _, _ in deletes])}
        return ChangePage(changes, json.dumps(nxt), False)

    # ---- helpers -------------------------------------------------------------
    @staticmethod
    def _parse(cursor: str) -> dict:
        if not cursor or cursor == "0":
            return {"since": 0.0, "seen": [], "dseq": 0}
        c = json.loads(cursor)
        return {"since": float(c.get("since", 0)), "seen": c.get("seen", []), "dseq": int(c.get("dseq", 0))}

    def _maybe_reconcile(self):
        now = time.time()
        if config.RECONCILE_EVERY_S and now - self._last_reconcile < config.RECONCILE_EVERY_S:
            return
        current = self._all_ids()
        gone = sorted(self._known - current) if self._known else []  # empty after restart: baseline only
        if len(gone) > max(MASS_DELETE_MIN, MASS_DELETE_FRACTION * len(self._known)) and not config.ALLOW_MASS_DELETE:
            # keep the old baseline so the deletions are re-evaluated next time, don't emit anything
            self.anomaly = (f"reconciliation would delete {len(gone)} of {len(self._known)} items; held back "
                            f"(listing truncated or integration access lost?)")
            self._last_reconcile = now
            return
        self.anomaly = ""
        for native_id in gone:
            self._tomb_seq += 1
            self._tombs.append((self._tomb_seq, native_id, now))
        self._known = current
        self._last_reconcile = now
        self._tombs = self._tombs[-10_000:]
