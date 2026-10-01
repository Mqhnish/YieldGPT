"""Operational reliability. Owner: Member 3.

- AuditedDelivery: request receipt, terminal failure and delivery records for /api/ask,
  and the release rule: an answer is sent only after its audit rows and a protected
  checkpoint covering them are committed.
- config_problems(): deployment checks. Outside demo mode, errors refuse startup.
- health(): observed state (audit, checkpoints, sync, measured freshness). The poll
  interval is reported as configuration, never as a freshness guarantee.
- Maintenance: periodic checkpoint of the chain head, daily retention and change-log pruning.
"""
from __future__ import annotations

import os
import threading
import time
import uuid
from collections import defaultdict
from functools import partial

import anyio

from . import audit, checkpoints, config, identity

CHECKPOINT_INTERVAL_S = int(os.getenv("IB_CHECKPOINT_INTERVAL_S", "30"))
SYNC_LOG_RETENTION_S = int(os.getenv("IB_SYNC_LOG_RETENTION_DAYS", "30")) * 86400
DEV_SECRETS = {"SECRET_KEY": "dev-only-change-me", "WEBHOOK_SECRET": "dev-webhook-secret",
               "AUDIT_PSEUDONYM_KEY": "dev-pseudonym-key-change-me"}
WITHHELD = b'{"detail":"The answer could not be recorded securely, so it was not released. Please try again."}'


async def _log(*args, **kwargs):
    await anyio.to_thread.run_sync(partial(audit.log, *args, **kwargs))


class AuditedDelivery:
    """Pure ASGI middleware for answer delivery. The response is buffered, so no answer
    bytes leave the process until the audit batch is covered by a committed checkpoint."""
    PATHS = {"/api/ask"}

    def __init__(self, app):
        self.app = app

    async def __call__(self, scope, receive, send):
        if scope["type"] != "http" or not (scope["path"] in self.PATHS or scope["path"].startswith("/api/evidence/")
                or (scope["path"].startswith("/api/history/") and scope["path"].endswith("/replay"))):
            return await self.app(scope, receive, send)
        auth = dict(scope["headers"]).get(b"authorization", b"").decode("latin-1")
        user = identity.verify(auth.removeprefix("Bearer ").strip())
        actor = user.username if user else "anonymous"
        ctx = {"request_id": uuid.uuid4().hex[:16], "query_id": "", "actor": actor}
        rid = ctx["request_id"]
        await _log(actor, "request_received", request_id=rid, route=scope["path"], method=scope["method"])
        held = []

        async def hold(message):
            held.append(message)

        token = audit.REQUEST.set(ctx)
        try:
            await self.app(scope, receive, hold)
        except Exception as e:
            await _log(actor, "request_failed", severity="warning", query_id=ctx["query_id"], request_id=rid,
                       status=500, error_type=type(e).__name__)
            raise
        finally:
            audit.REQUEST.reset(token)
        start, body = held[0], b"".join(m.get("body", b"") for m in held[1:])
        status, qid = start["status"], ctx["query_id"]
        if status == 200:
            try:
                await anyio.to_thread.run_sync(audit.checkpoint)
            except Exception as e:  # noqa: BLE001  (no protected checkpoint = no release)
                await _log(actor, "response_withheld", severity="alert", query_id=qid, request_id=rid,
                           reason_code="checkpoint_unavailable", error_type=type(e).__name__)
                start = {"type": "http.response.start", "status": 503,
                         "headers": [(b"content-type", b"application/json")]}
                body, status = WITHHELD, 503
        else:
            await _log(actor, "request_failed", severity="warning", query_id=qid, request_id=rid, status=status)
        headers = [(k, v) for k, v in start["headers"] if k.lower() != b"content-length"]
        headers += [(b"content-length", str(len(body)).encode()), (b"x-request-id", rid.encode())]
        if not any(k.lower() == b"cache-control" for k, _ in headers):
            headers.append((b"cache-control", b"no-store, private"))
        try:
            await send({**start, "headers": headers})
            await send({"type": "http.response.body", "body": body})
        except Exception as e:
            await _log(actor, "response_delivery_failed", severity="warning", query_id=qid, request_id=rid,
                       error_type=type(e).__name__)
            raise
        if start["status"] == 200:
            # Observable precision: bytes handed to the HTTP server transport, not client receipt.
            await _log(actor, "response_delivered", query_id=qid, request_id=rid, bytes=len(body), route=scope["path"],
                       observed="handed_to_server_transport")


# ---------------------------------------------------------------- configuration checks
def config_problems() -> list[dict]:
    out = []

    def add(level, code, message):
        out.append({"level": level, "code": code, "message": message})

    for name, dev in DEV_SECRETS.items():
        if getattr(config, name) == dev:
            add("error", f"dev_{name.lower()}", f"IB_{name} still has its development default")
    if not checkpoints.s3_configured():
        add("error", "local_checkpoints", "audit checkpoints are in a local file the app can rewrite; "
                                          "set IB_CHECKPOINT_S3_* (Object Lock bucket)")
    elif not all(os.getenv(v) for v in ("IB_CHECKPOINT_WRITER_KEY", "IB_CHECKPOINT_WRITER_SECRET",
                                        "IB_CHECKPOINT_READER_KEY", "IB_CHECKPOINT_READER_SECRET")):
        add("error", "checkpoint_credentials", "checkpoint writer/reader credentials are incomplete")
    if not audit.encryption_available():
        add("error", "no_content_encryption", "the 'cryptography' package is missing; audit text is not encrypted")
    if audit.key_source() != "env":
        add("error", "content_key_beside_db", "audit content key is a local demo file; set IB_AUDIT_CONTENT_KEY")
    if int(os.getenv("WEB_CONCURRENCY", "1")) > 1:
        add("warning", "multiple_workers", "the search index is per process; run a single app worker")
    if config.DEMO_MODE:
        add("warning", "demo_mode", "demo identities and simulated-source controls are enabled")
    return out


def fatal_problems() -> list[dict]:
    return [] if config.DEMO_MODE else [p for p in config_problems() if p["level"] == "error"]


# ---------------------------------------------------------------- health
def _pct(values: list[float], q: float) -> float:
    s = sorted(values)
    return round(s[min(len(s) - 1, int(q * (len(s) - 1) + 0.5))], 3)


def observed_freshness(records) -> dict:
    """Measured lag = applied_at - source_at, per platform and delivery path. Webhook lag
    measures apply time after receipt; poll lag includes detection delay."""
    lags, failures = defaultdict(list), defaultdict(int)
    for r in records:
        if r.outcome == "failed":
            failures[r.platform] += 1
        elif r.source_at and r.via in ("poll", "webhook"):
            lags[(r.platform, r.via)].append(max(0.0, r.applied_at - r.source_at))
    out: dict = {}
    for (platform, via), v in sorted(lags.items()):
        out.setdefault(platform, {})[via] = {"n": len(v), "p50_s": _pct(v, .5), "p95_s": _pct(v, .95),
                                             "max_s": round(max(v), 3)}
    return {"lag": out, "recent_failures": dict(failures), "sample": len(records)}


def health(brain=None, detail: bool = False) -> dict:
    report: dict = {"checked_at": time.time()}
    try:
        h = audit.head()
        report["audit"] = {"writable": True, "rows": h[0] if h else 0}
    except Exception as e:  # noqa: BLE001
        report["audit"] = {"writable": False, "error": type(e).__name__}
    store, last = audit._store(), audit.STATE["last_checkpoint"]
    cp = {"store": store.kind, "last_row": last["row_id"] if last else None,
          "age_s": round(time.time() - last["at"], 1) if last else None,
          "last_error": audit.STATE["last_checkpoint_error"]}
    try:
        cp["assurance"], cp["reachable"] = store.assurance(), True
    except Exception as e:  # noqa: BLE001
        cp["assurance"], cp["reachable"], cp["last_error"] = None, False, type(e).__name__
    if report["audit"].get("rows") is not None:
        cp["uncheckpointed_rows"] = report["audit"]["rows"] - (cp["last_row"] or 0)
    report["checkpoints"] = cp
    sync_ok = True
    if brain is not None:
        platforms = brain.syncer.status(config.POLL_INTERVAL_S)
        sync_ok = all(p["health"] == "ok" for p in platforms.values())
        report["sync"] = {"platforms": platforms, "indexed_docs": len(brain.index),
                          "poll_interval_s_configured": config.POLL_INTERVAL_S,
                          "note": "configured interval, not a measured or guaranteed freshness bound",
                          "observed": observed_freshness(brain.syncer.store.recent(limit=2000))}
    report["config"] = config_problems()
    report["status"] = ("failing" if not report["audit"]["writable"] else
                        "ok" if cp["reachable"] and not cp["last_error"] and sync_ok else "degraded")
    return report if detail else {"status": report["status"]}


# ---------------------------------------------------------------- maintenance
class Maintenance:
    def __init__(self, sync_store=None, interval_s: int = CHECKPOINT_INTERVAL_S):
        self.sync_store, self.interval_s = sync_store, interval_s
        self._stop, self._daily_at = threading.Event(), 0.0
        self._thread = threading.Thread(target=self._loop, daemon=True, name="audit-maintenance")

    def start(self):
        self._thread.start()

    def stop(self):
        self._stop.set()
        self._thread.join(timeout=5)

    def tick(self):
        h, last = audit.head(), audit.STATE["last_checkpoint"]
        if h and (not last or last["row_id"] != h[0]):
            audit.try_checkpoint()
        if time.time() - self._daily_at >= 86400:
            audit.apply_retention()
            if hasattr(self.sync_store, "prune"):
                self.sync_store.prune(SYNC_LOG_RETENTION_S)
            self._daily_at = time.time()

    def _loop(self):
        while not self._stop.wait(self.interval_s):
            try:
                self.tick()
            except Exception as e:  # noqa: BLE001  (health reports the failure; never kill the loop)
                audit.STATE["last_checkpoint_error"] = type(e).__name__
