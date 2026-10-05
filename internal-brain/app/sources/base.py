"""THE CONNECTOR CONTRACT. Every platform adapter (Confluence, Jira, Slack, Drive)
implements `Connector` and must pass tests/contract/. Nothing outside a connector
may touch a platform directly: sync, retrieval and authorization only call these
methods.

Owner: Member 1. Changes to this file need sign-off from all three members.

Rules every connector MUST follow
---------------------------------
R1  check() never raises. Any error, timeout, missing credential or unknown
    permission state returns UNAVAILABLE. Only an explicit positive answer from
    the platform's own permission model returns ALLOWED.            (fail closed)
R2  check() evaluates the ASKER's rights using the platform's native rules, live,
    at call time. The ingestion bot being able to read a doc proves nothing.
R3  A user with no linked account on the platform is DENIED ("no_linked_account").
R4  A resource that doesn't exist is DENIED ("not_found"), never UNAVAILABLE, and
    the user-facing layer must treat it identically to any other denial.
R5  acl_hint() must include every principal that check() would currently allow
    (it may include more). It is only an index prefilter, never a decision.
R6  fetch() returns None for deleted/expired content, and raises SourceUnavailable
    (not None) when the platform can't be reached, so sync never mistakes an
    outage for a deletion.
R7  list_page() paginates the full estate with no duplicates. changes_since()
    returns every upsert / acl / delete after the cursor, in order, and is safe to
    replay (applying the same change twice gives the same index state).
R8  start_cursor() is taken BEFORE the initial crawl, so changes made during the
    crawl are replayed afterwards instead of lost.
R9  Every SourceDoc has uid "<platform>:<native_id>", a non-empty version string
    that changes whenever content changes, and an https url.
R10 reason_code is a stable machine-readable string. reason is human detail and
    is written to the audit log ONLY, never shown to the asker.
R11 A permission check that takes longer than CHECK_TIMEOUT_S is UNAVAILABLE
    ("timeout"). The base class enforces this; don't add your own retries inside
    _check, because a slow answer is treated as no answer.
R12 Error text that reaches the audit log is truncated and must not contain
    credentials. Never put tokens or API keys in exception messages.
R13 ping() raises SourceUnavailable when the platform is down. It is used to tell
    "this platform is down" (safe to tell the user) apart from "this one document
    errored" (not safe: could hint that the document exists).
"""
from __future__ import annotations

import time
from abc import ABC, abstractmethod
from concurrent.futures import ThreadPoolExecutor
from concurrent.futures import TimeoutError as FutureTimeout
from dataclasses import dataclass, field
from enum import Enum

from .. import config
from ..identity import User, account_for, principals

_CHECK_POOL = ThreadPoolExecutor(max_workers=16, thread_name_prefix="authz")
# Separate pool for check_many's per-id dispatch to connectors that override check(): those
# calls themselves wait on _CHECK_POOL, so sharing one pool could starve it under load.
_DISPATCH_POOL = ThreadPoolExecutor(max_workers=16, thread_name_prefix="authz-dispatch")


def safe_error(e: Exception) -> str:
    """R12: bounded, type-prefixed error text for the audit log."""
    return f"{type(e).__name__}: {str(e)[:200]}"


class SourceUnavailable(Exception):
    """Raised by platform calls when the platform can't be reached or errors."""


class Decision(str, Enum):
    ALLOWED = "allowed"
    DENIED = "denied"
    UNAVAILABLE = "unavailable"  # could not determine: treated exactly like DENIED for release


@dataclass(frozen=True)
class PermissionResult:
    decision: Decision
    reason_code: str            # stable code, e.g. "space_view_missing", "not_found", "source_error"
    reason: str                 # human detail, audit-only
    checked_at: float
    platform_account: str       # which platform identity was evaluated ("" if none linked)
    resource_version: str = ""  # version of the resource at check time, if known

    @property
    def allowed(self) -> bool:
        return self.decision is Decision.ALLOWED


@dataclass
class SourceDoc:
    uid: str                # "<platform>:<native_id>"
    platform: str
    tenant: str             # site / workspace / domain the object lives in
    native_id: str
    container: str          # space key / project key / channel / folder
    title: str
    text: str
    url: str
    version: str            # changes whenever content changes
    updated_at: float
    parent: str = ""        # parent page / folder / thread root, if any
    author: str = ""
    links: list[str] = field(default_factory=list)


@dataclass(frozen=True)
class Change:
    native_id: str
    kind: str               # "upsert" | "acl" | "delete"
    at: float               # when the platform says it happened


@dataclass
class ChangePage:
    changes: list[Change]
    next_cursor: str
    has_more: bool


class Connector(ABC):
    platform: str = ""
    tenant: str = ""

    def uid(self, native_id: str) -> str:
        return f"{self.platform}:{native_id}"

    # ---- ingestion -------------------------------------------------------
    @abstractmethod
    def start_cursor(self) -> str: ...

    @abstractmethod
    def list_page(self, page_token: str | None, page_size: int = 50) -> tuple[list[str], str | None]:
        """One page of native ids for the initial crawl. Returns (ids, next_token or None)."""

    @abstractmethod
    def changes_since(self, cursor: str, page_size: int = 100) -> ChangePage: ...

    @abstractmethod
    def fetch(self, native_id: str) -> SourceDoc | None: ...

    @abstractmethod
    def acl_hint(self, native_id: str) -> set[str]: ...

    # ---- authorization ---------------------------------------------------
    @abstractmethod
    def _check(self, user: User, account: str, native_id: str) -> tuple[Decision, str, str, str]:
        """Platform-specific rule evaluation. Return (decision, reason_code, reason, version).
        May raise; check() converts any exception into UNAVAILABLE."""

    # Optional: platforms with a native bulk permission API override this and set
    # supports_batch = True. Return {native_id: (decision, reason_code, reason, version)}.
    supports_batch = False

    def _check_batch(self, user: User, account: str, native_ids: list[str]) -> dict:
        raise NotImplementedError

    def check(self, user: User, native_id: str) -> PermissionResult:
        """Public entry point for one document. Same rules as check_many."""
        return self._check_native(user, [native_id])[native_id]

    def check_many(self, user: User, native_ids: list[str]) -> dict[str, PermissionResult]:
        """Check several documents for one user. Enforces R1, R3 and R11 for every id:
        runs checks in parallel (or one bulk call if the platform supports it), all under a
        single CHECK_TIMEOUT_S deadline. Anything not answered in time is UNAVAILABLE."""
        now = time.time()
        ids = list(dict.fromkeys(native_ids))
        if type(self).check is not Connector.check:
            # The connector customises check() (e.g. Slack workspace/user scoping). Batching must
            # never route around that logic: run ITS check() per id, in parallel, same deadline.
            futs = {nid: _DISPATCH_POOL.submit(self.check, user, nid) for nid in ids}
            deadline = now + config.CHECK_TIMEOUT_S
            out = {}
            for nid, f in futs.items():
                try:
                    out[nid] = f.result(timeout=max(0.0, deadline - time.time()))
                except FutureTimeout:
                    out[nid] = PermissionResult(Decision.UNAVAILABLE, "timeout",
                                                f"permission check exceeded {config.CHECK_TIMEOUT_S}s", now,
                                                account_for(user, self.platform) or "")
                except Exception as e:  # noqa: BLE001  (fail closed)
                    out[nid] = PermissionResult(Decision.UNAVAILABLE, "source_error", safe_error(e), now,
                                                account_for(user, self.platform) or "")
            return out
        return self._check_native(user, ids)

    def _check_native(self, user: User, ids: list[str]) -> dict[str, PermissionResult]:
        """The rule engine behind check() and check_many(): R1, R3, R11, bulk or parallel."""
        now = time.time()
        ids = list(dict.fromkeys(ids))
        account = account_for(user, self.platform)
        if not account:
            return {nid: PermissionResult(Decision.DENIED, "no_linked_account",
                                          f"{user.username} has no {self.platform} account", now, "") for nid in ids}

        def failed(e: Exception) -> PermissionResult:
            if isinstance(e, FutureTimeout):
                return PermissionResult(Decision.UNAVAILABLE, "timeout",
                                        f"permission check exceeded {config.CHECK_TIMEOUT_S}s", now, account)
            return PermissionResult(Decision.UNAVAILABLE, "source_error", safe_error(e), now, account)

        def res(fn) -> PermissionResult:
            try:
                decision, code, reason, version = fn()
                return PermissionResult(decision, code, reason, now, account, version)
            except Exception as e:  # noqa: BLE001  (R1: anything unexpected fails closed)
                return failed(e)

        deadline = now + config.CHECK_TIMEOUT_S
        if self.supports_batch and len(ids) > 1:
            fut = _CHECK_POOL.submit(self._check_batch, user, account, ids)
            try:
                batch = fut.result(timeout=max(0.0, deadline - time.time()))
            except Exception as e:  # noqa: BLE001  (timeout or error: every id fails closed)
                return {nid: failed(e) for nid in ids}
            return {nid: res(lambda nid=nid: batch[nid]) if nid in batch else
                    PermissionResult(Decision.UNAVAILABLE, "no_decision", "bulk check returned no decision", now, account)
                    for nid in ids}
        futs = {nid: _CHECK_POOL.submit(self._check, user, account, nid) for nid in ids}
        return {nid: res(lambda f=f: f.result(timeout=max(0.0, deadline - time.time()))) for nid, f in futs.items()}

    def ping(self) -> None:
        """R13: raise SourceUnavailable if the platform is unreachable. Default: cheap cursor call."""
        self.start_cursor()

    # ---- helpers -----------------------------------------------------------
    @staticmethod
    def _matches(user: User, allowed: set[str]) -> bool:
        return bool(principals(user) & allowed)
