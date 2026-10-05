"""Security log + audit trail: tamper-evident, complete, queryable. Owner: Member 3.

Tamper-evident
  Each row stores the SHA-256 of the previous row (hash chain). Every append is one
  SQLite `BEGIN IMMEDIATE` transaction (read head, insert), so ordering is safe across
  threads AND worker processes. The chain head is committed to a checkpoint store
  outside the app's write authority (app/checkpoints.py: S3 Object Lock in COMPLIANCE
  mode). The verifier trusts those checkpoints, not this database, so modified rows,
  deleted rows, a rewritten chain and a truncated checkpointed tail are all detected.
  Rows after the last checkpoint are reported as an uncheckpointed tail, never as verified.

Protected content
  Free text (questions, answers, discarded drafts, titles, reasons) is sealed with
  AES-GCM into `audit_content`. The chained row keeps only a salted digest, so text
  can be redacted after the retention period without breaking verification, and a
  database file or backup does not expose it.

Complete
  Per request: receipt, question, plan, a decision for every considered document,
  the exact versions sent to the model, the answer or terminal failure, and the
  delivery outcome. `request_id` links HTTP-level events to the brain's `query_id`.

Queryable
  Denormalised columns (actor, platform, container, doc_uid, decision) make compliance
  questions plain SQL; `parse_question()` turns plain English into filters.
"""
import base64
import contextvars
import hashlib
import json
import os
import re
import secrets
import sqlite3
import time
from contextlib import closing
from pathlib import Path

from . import checkpoints
from .config import ANCHOR_EVERY, ANCHOR_PATH, AUDIT_DB, DEMO_MODE, PROBE_ALERT_THRESHOLD

GENESIS = "0" * 64
COLS = ["ts", "actor", "event", "severity", "query_id", "platform", "container", "doc_uid", "decision", "detail",
        "request_id"]
SEALED_KEYS = ("question", "answer", "discarded_answer", "dropped", "title", "reason", "value", "filters")
TERMINAL = ("answer_returned", "request_failed", "response_withheld", "request_abandoned")
REDACTED = "[redacted: retention]"
UNREADABLE = "[sealed: unreadable]"

# Set per HTTP request by app/reliability.py: {"request_id", "query_id", "actor"}.
REQUEST: contextvars.ContextVar = contextvars.ContextVar("audit_request", default=None)
STATE: dict = {"last_checkpoint": None, "last_checkpoint_error": ""}   # per-process, for health


def retention_days() -> int:
    return int(os.getenv("IB_AUDIT_TEXT_RETENTION_DAYS", "90"))


def _conn():
    c = sqlite3.connect(AUDIT_DB, timeout=15, isolation_level=None)
    c.row_factory = sqlite3.Row
    return c


def init():
    with closing(_conn()) as c:
        cols = {r["name"] for r in c.execute("PRAGMA table_info(audit_log)")}
        if cols and "request_id" not in cols:
            raise RuntimeError(f"{AUDIT_DB} uses the pre-Member-3 audit schema. "
                               "Run scripts/reset_demo.py or set IB_AUDIT_DB to a new file.")
        c.execute("PRAGMA journal_mode=WAL")
        c.execute(f"""CREATE TABLE IF NOT EXISTS audit_log (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            {', '.join(f'{col} TEXT' for col in COLS)},
            prev_hash TEXT NOT NULL, hash TEXT NOT NULL)""")
        c.execute("""CREATE TABLE IF NOT EXISTS audit_content (row_id INTEGER PRIMARY KEY, alg TEXT NOT NULL,
                     nonce BLOB NOT NULL, ciphertext BLOB NOT NULL, ts REAL NOT NULL)""")
        for col in ("actor", "doc_uid", "container", "query_id", "ts", "request_id", "event"):
            c.execute(f"CREATE INDEX IF NOT EXISTS ix_{col} ON audit_log({col})")


def _hash(values: list, prev: str) -> str:
    return hashlib.sha256(json.dumps(values + [prev], default=str).encode()).hexdigest()


# ---------------------------------------------------------------- content sealing
def encryption_available() -> bool:
    try:
        import cryptography.hazmat.primitives.ciphers.aead  # noqa: F401
        return True
    except ImportError:
        return False


def key_source() -> str:
    return "env" if os.getenv("IB_AUDIT_CONTENT_KEY") else "demo_key_file"


def _key_file() -> Path:
    return Path(AUDIT_DB).with_name(Path(AUDIT_DB).name + ".content.key")


_DEMO_KEYS: dict = {}


def _key(create: bool = False) -> bytes | None:
    """The content key: IB_AUDIT_CONTENT_KEY, or in demo mode a key file beside the DB,
    created only by a writer (never by a read-only verifier)."""
    env = os.getenv("IB_AUDIT_CONTENT_KEY", "")
    if env:
        key = base64.b64decode(env)
        if len(key) != 32:
            raise RuntimeError("IB_AUDIT_CONTENT_KEY must be 32 random bytes, base64-encoded")
        return key
    path = _key_file()
    if path not in _DEMO_KEYS:
        if create and DEMO_MODE:
            try:
                fd = os.open(path, os.O_CREAT | os.O_EXCL | os.O_WRONLY, 0o600)
                os.write(fd, base64.b64encode(secrets.token_bytes(32)))
                os.close(fd)
            except FileExistsError:
                pass                    # another process created it first: use theirs
        if not path.exists():
            return None                 # outside demo mode the key must come from the secret store
        _DEMO_KEYS[path] = base64.b64decode(path.read_bytes())
    return _DEMO_KEYS[path]


def _seal(nonce: bytes, plaintext: bytes, digest: str) -> tuple[str, bytes]:
    if not encryption_available():
        raise RuntimeError("Audit encryption dependency is missing; refusing plaintext persistence")
    key = _key(create=True)
    if key is None:
        raise RuntimeError("audit content key unavailable: set IB_AUDIT_CONTENT_KEY")
    from cryptography.hazmat.primitives.ciphers.aead import AESGCM
    return "aesgcm", AESGCM(key).encrypt(nonce, plaintext, digest.encode())


def _unseal(alg: str, nonce: bytes, blob: bytes, digest: str) -> bytes | None:
    """Plaintext, or None if the key is missing or the ciphertext/digest don't match."""
    try:
        if alg == "none":
            plain = blob
        else:
            from cryptography.hazmat.primitives.ciphers.aead import AESGCM
            key = _key()
            if key is None:
                return None
            plain = AESGCM(key).decrypt(nonce, blob, digest.encode())
    except Exception:  # noqa: BLE001  (wrong key or altered ciphertext)
        return None
    return plain if hashlib.sha256(nonce + plain).hexdigest() == digest else None


# ---------------------------------------------------------------- append
def _append(c, actor, event, severity, query_id, platform, container, doc_uid, decision, request_id, detail) -> int:
    """Append one row inside an open BEGIN IMMEDIATE transaction."""
    sealed = {k: detail.pop(k) for k in SEALED_KEYS if k in detail}
    if sealed:
        nonce = secrets.token_bytes(12)
        plaintext = json.dumps(sealed, sort_keys=True, default=str).encode()
        digest = hashlib.sha256(nonce + plaintext).hexdigest()
        alg, blob = _seal(nonce, plaintext, digest)
        detail["_sealed"], detail["_digest"] = sorted(sealed), digest
    ts = time.time()
    row = [f"{ts:.6f}", actor, event, severity, query_id, platform, container, doc_uid, decision,
           json.dumps(detail, sort_keys=True, default=str), request_id]
    last = c.execute("SELECT hash FROM audit_log ORDER BY id DESC LIMIT 1").fetchone()
    prev = last["hash"] if last else GENESIS
    new_id = c.execute(f"INSERT INTO audit_log ({', '.join(COLS)}, prev_hash, hash) "
                       f"VALUES ({', '.join('?' * (len(COLS) + 2))})", row + [prev, _hash(row, prev)]).lastrowid
    if sealed:
        c.execute("INSERT INTO audit_content VALUES (?,?,?,?,?)", (new_id, alg, nonce, blob, ts))
    return new_id


def log(actor: str, event: str, *, severity: str = "info", query_id: str = "", platform: str = "",
        container: str = "", doc_uid: str = "", decision: str = "", request_id: str | None = None, **detail) -> int:
    """severity: info | warning | alert. Raises if the row can't be committed (callers fail closed)."""
    ctx = REQUEST.get()
    if ctx is not None and query_id:
        ctx["query_id"] = query_id
    if request_id is None:
        request_id = ctx["request_id"] if ctx else ""
    with closing(_conn()) as c:
        c.execute("BEGIN IMMEDIATE")
        try:
            new_id = _append(c, actor, event, severity, query_id, platform, container, doc_uid, decision,
                             request_id, detail)
            c.execute("COMMIT")
        except BaseException:
            c.execute("ROLLBACK")
            raise
    if new_id % ANCHOR_EVERY == 0:
        try_checkpoint()
    if decision == "denied":
        _probe_check(actor)
    return new_id


def _probe_check(actor: str):
    """Security signal: many denials in a short window looks like someone probing."""
    since = f"{time.time() - 600:.6f}"
    with closing(_conn()) as c:
        n = c.execute("SELECT COUNT(*) FROM audit_log WHERE actor=? AND decision='denied' AND ts>=?",
                      (actor, since)).fetchone()[0]
        already = c.execute("SELECT COUNT(*) FROM audit_log WHERE actor=? AND event='probing_suspected' AND ts>=?",
                            (actor, since)).fetchone()[0]
    if n >= PROBE_ALERT_THRESHOLD and not already:
        log(actor, "probing_suspected", severity="alert", denials_last_10min=n)


# ---------------------------------------------------------------- checkpoints
def _store():
    return checkpoints.from_env(ANCHOR_PATH)


def head() -> tuple[int, str] | None:
    with closing(_conn()) as c:
        r = c.execute("SELECT id, hash FROM audit_log ORDER BY id DESC LIMIT 1").fetchone()
    return (r["id"], r["hash"]) if r else None


def checkpoint() -> dict:
    """Commit the current head to the protected store. Raises CheckpointError on failure."""
    h = head()
    if not h:
        return {}
    try:
        _store().append(*h)
    except Exception as e:
        STATE["last_checkpoint_error"] = type(e).__name__
        raise checkpoints.CheckpointError(str(e) if isinstance(e, checkpoints.CheckpointError)
                                          else type(e).__name__) from None
    STATE["last_checkpoint"] = {"row_id": h[0], "hash": h[1], "at": time.time()}
    STATE["last_checkpoint_error"] = ""
    return STATE["last_checkpoint"]


def try_checkpoint() -> dict:
    try:
        return checkpoint()
    except checkpoints.CheckpointError:
        return {}


anchor = try_checkpoint   # legacy name


# ---------------------------------------------------------------- retention + restart recovery
def apply_retention(days: int | None = None, now: float | None = None) -> int:
    """Delete sealed text older than the policy period. The deletion and its chained
    `retention_applied` record commit in one transaction."""
    days = retention_days() if days is None else days
    cutoff = (now or time.time()) - days * 86400
    with closing(_conn()) as c:
        c.execute("BEGIN IMMEDIATE")
        try:
            n = c.execute("DELETE FROM audit_content WHERE ts < ?", (cutoff,)).rowcount
            if n:
                _append(c, "system", "retention_applied", "info", "", "", "", "", "", "",
                        {"cutoff": cutoff, "days": days, "redacted_rows": n})
            c.execute("COMMIT")
        except BaseException:
            c.execute("ROLLBACK")
            raise
    return n


def recover_interrupted() -> int:
    """Run at startup: give every request/query without a terminal event an explicit
    `request_abandoned` terminal record. ponytail: assumes no other worker is mid-request."""
    marks = ",".join("?" * len(TERMINAL))
    with closing(_conn()) as c:
        reqs = c.execute(f"""SELECT request_id, actor FROM audit_log WHERE event='request_received'
            AND request_id NOT IN (SELECT request_id FROM audit_log WHERE event IN ({marks}) AND request_id!='')""",
                         TERMINAL).fetchall()
        qids = {r["request_id"]: (r["query_id"] or "") for r in c.execute(
            "SELECT request_id, MAX(query_id) AS query_id FROM audit_log WHERE request_id!='' GROUP BY request_id")}
        orphans = c.execute(f"""SELECT query_id, actor FROM audit_log WHERE event='query_received'
            AND request_id='' AND query_id NOT IN (SELECT query_id FROM audit_log WHERE event IN ({marks}) AND query_id!='')""",
                            TERMINAL).fetchall()
    for r in reqs:
        log(r["actor"], "request_abandoned", severity="warning", query_id=qids.get(r["request_id"], ""),
            request_id=r["request_id"], reason="no terminal event before process restart")
    for r in orphans:
        log(r["actor"], "request_abandoned", severity="warning", query_id=r["query_id"], request_id="",
            reason="no terminal event before process restart")
    return len(reqs) + len(orphans)


# ---------------------------------------------------------------- verifier
def verify_report(store=None) -> dict:
    """status: verified | failed | unverifiable. `verified_through` is the last checkpointed
    row; later rows are an uncheckpointed tail and are never reported as verified."""
    rows, sealed, retention, prev, last_id = {}, {}, [], GENESIS, 0
    report = {"status": "verified", "ok": True, "problem": None, "at_id": None, "rows": 0, "anchors_checked": 0,
              "verified_through": 0, "uncheckpointed_rows": 0, "assurance": None, "fully_verified": False,
              "checkpoint_store": None, "content": {"sealed": 0, "ok": 0, "redacted": 0, "unchecked": 0},
              "checked_at": time.time()}

    def done(status, problem=None, at_id=None):
        report.update(status=status, ok=status == "verified", problem=problem, at_id=at_id)
        report["fully_verified"] = (status == "verified" and report["uncheckpointed_rows"] == 0
                                    and report["assurance"] == "independent_worm")
        return report

    with closing(_conn()) as c:
        for r in c.execute("SELECT * FROM audit_log ORDER BY id"):
            if r["id"] != last_id + 1:
                return done("failed", "row deleted (gap in ids)", last_id + 1)
            if r["prev_hash"] != prev or r["hash"] != _hash([r[col] for col in COLS], prev):
                return done("failed", "row modified", r["id"])
            prev, last_id = r["hash"], r["id"]
            rows[r["id"]] = r["hash"]
            detail = json.loads(r["detail"] or "{}")
            if "_digest" in detail:
                sealed[r["id"]] = (detail["_digest"], float(r["ts"]))
            if r["event"] == "retention_applied" and r["actor"] == "system":
                retention.append((float(r["ts"]), detail.get("cutoff", 0), detail.get("days", 0)))
        content = {x["row_id"]: (x["alg"], x["nonce"], x["ciphertext"])
                   for x in c.execute("SELECT row_id, alg, nonce, ciphertext FROM audit_content")}
    report["rows"] = last_id

    # A redaction is legitimate only if a chained retention record covers it and that
    # record did not cut younger than the policy period at the time it was written.
    policy = retention_days()
    valid_cutoff = max([cut for ts, cut, days in retention if days >= policy and cut <= ts - days * 86400 + 1],
                       default=float("-inf"))
    have_key = encryption_available() and _key_available()
    for row_id, (digest, ts) in sealed.items():
        report["content"]["sealed"] += 1
        if row_id not in content:
            if ts < valid_cutoff:
                report["content"]["redacted"] += 1
                continue
            return done("failed", "sealed content deleted without retention record", row_id)
        alg, nonce, blob = content[row_id]
        if alg != "none" and not have_key:
            report["content"]["unchecked"] += 1
        elif _unseal(alg, nonce, blob, digest) is None:
            return done("failed", "sealed content altered", row_id)
        else:
            report["content"]["ok"] += 1

    store = store or _store()
    report["checkpoint_store"] = store.kind
    try:
        cps = store.checkpoints()
        report["assurance"] = store.assurance()
    except Exception as e:  # noqa: BLE001
        return done("unverifiable", f"checkpoint store unreachable ({type(e).__name__})")
    by_row: dict[int, set] = {}
    for cp in cps:
        by_row.setdefault(int(cp["row_id"]), set()).add(cp["hash"])
    report["anchors_checked"] = len(by_row)
    conflicts = sorted(r for r, hs in by_row.items() if len(hs) > 1)
    if conflicts:
        return done("failed", "conflicting checkpoints for one row (equivocation)", conflicts[0])
    for row_id in sorted(by_row):
        if row_id not in rows:
            return done("failed", "log truncated (anchored row missing)", row_id)
        if rows[row_id] != next(iter(by_row[row_id])):
            return done("failed", "chain rewritten (anchor mismatch)", row_id)
    report["verified_through"] = max(by_row, default=0)
    report["uncheckpointed_rows"] = last_id - report["verified_through"]
    if last_id and not by_row:
        return done("unverifiable", "no committed checkpoints in the protected store")
    return done("verified")


def _key_available() -> bool:
    try:
        return _key() is not None
    except Exception:  # noqa: BLE001
        return False


def verify() -> dict:
    """Legacy shape used by the original console and tests. Prefer verify_report()."""
    r = verify_report()
    if r["ok"]:
        return {"ok": True, "rows": r["rows"], "anchors_checked": r["anchors_checked"]}
    return {"ok": False, "problem": r["problem"], "at_id": r["at_id"]}


# ---------------------------------------------------------------- read paths
def _open_content(rows) -> dict[int, dict]:
    ids = [r["id"] for r in rows if '"_digest"' in (r["detail"] or "")]
    if not ids:
        return {}
    with closing(_conn()) as c:
        found = {x["row_id"]: x for x in c.execute(
            f"SELECT row_id, alg, nonce, ciphertext FROM audit_content WHERE row_id IN ({','.join('?' * len(ids))})", ids)}
    out, ids = {}, set(ids)
    for r in rows:
        if r["id"] not in ids:
            continue
        detail = json.loads(r["detail"])
        x = found.get(r["id"])
        plain = _unseal(x["alg"], x["nonce"], x["ciphertext"], detail["_digest"]) if x else None
        out[r["id"]] = json.loads(plain) if plain else {k: REDACTED if not x else UNREADABLE for k in detail["_sealed"]}
    return out


def search(actor=None, event=None, platform=None, container=None, doc_uid=None, decision=None,
           query_id=None, since=None, until=None, severity=None, request_id=None, limit=500) -> list[dict]:
    where, args = [], []
    if container:
        # Space keys on a real Confluence site can't contain '-' or '_' and are upper case
        # ("payment-gateway" is PAYMENTGATEWAY), so containers match ignoring case and separators.
        where.append("LOWER(REPLACE(REPLACE(container, '-', ''), '_', '')) = ?")
        args.append(container.lower().replace("-", "").replace("_", ""))
    for col, val in [("actor", actor), ("event", event), ("platform", platform),
                     ("doc_uid", doc_uid), ("decision", decision), ("query_id", query_id), ("severity", severity),
                     ("request_id", request_id)]:
        if val:
            where.append(f"{col} = ?")
            args.append(val)
    if since:
        where.append("CAST(ts AS REAL) >= ?")
        args.append(since)
    if until:
        where.append("CAST(ts AS REAL) <= ?")
        args.append(until)
    sql = "SELECT * FROM audit_log" + (" WHERE " + " AND ".join(where) if where else "") + " ORDER BY id DESC LIMIT ?"
    with closing(_conn()) as c:
        rows = c.execute(sql, args + [limit]).fetchall()
    opened = _open_content(rows)
    out = []
    for r in rows:
        detail = json.loads(r["detail"])
        detail.pop("_sealed", None)
        detail.pop("_digest", None)
        detail.update(opened.get(r["id"], {}))
        out.append({**{k: r[k] for k in r.keys() if k != "detail"}, "ts": float(r["ts"]), "detail": detail})
    return out


def actors() -> set[str]:
    with closing(_conn()) as c:
        return {r[0] for r in c.execute("SELECT DISTINCT actor FROM audit_log")}


DELIVERY = {"response_delivered": "delivered", "response_withheld": "withheld",
            "response_delivery_failed": "delivery_failed", "request_failed": "failed",
            "request_abandoned": "abandoned"}


def reconstruct(**filters) -> list[dict]:
    """Group matching document decisions back into full request stories:
    who asked what, what was considered/denied, what the model saw, and what was delivered."""
    hits = search(**filters)
    qids = []
    for h in hits:
        if h["query_id"] and h["query_id"] not in qids:
            qids.append(h["query_id"])
    stories = []
    for qid in qids:
        events = {e["id"]: e for e in search(query_id=qid)}
        rid = next((e["request_id"] for e in events.values() if e.get("request_id")), "")
        if rid:
            events.update({e["id"]: e for e in search(request_id=rid)})
        events = [events[i] for i in sorted(events)]
        q = next((e for e in events if e["event"] == "query_received"), None)
        a = next((e for e in events if e["event"] == "answer_returned"), None)
        context = [{"attempt": e["detail"].get("attempt"), "docs": e["detail"].get("context")}
                   for e in events if e["event"] == "context_assembled"]
        sent = {d["uid"] for attempt in context for d in (attempt["docs"] or [])}
        decisions = [{"doc_uid": e["doc_uid"], "platform": e["platform"], "container": e["container"],
                      "decision": e["decision"], "stage": e["detail"].get("stage"), "phase": e["detail"].get("phase"),
                      "attempt": e["detail"].get("attempt"),
                      "reason_code": e["detail"].get("reason_code"), "reason": e["detail"].get("reason"),
                      "resource_version": e["detail"].get("resource_version"),
                      "platform_account": e["detail"].get("platform_account"),
                      "checked_at": e["detail"].get("checked_at")}
                     for e in events if e["event"] == "authz_decision"]
        permitted = {d["doc_uid"] for d in decisions if d["stage"] == "live" and d["decision"] == "allowed"}
        outcome = [e["event"] for e in events if e["event"] in DELIVERY]
        stories.append({
            "query_id": qid,
            "request_id": rid,
            "ts": q["ts"] if q else events[0]["ts"],
            "actor": events[0]["actor"],
            "question": q["detail"].get("question") if q else None,
            "matched": [{"doc_uid": h["doc_uid"], "decision": h["decision"], "stage": h["detail"].get("stage"),
                         "reason": h["detail"].get("reason")}
                        for h in hits if h["query_id"] == qid and h["doc_uid"]],
            "decisions": decisions,
            # exactly which document versions the model saw, per generation attempt
            "context_sent": context,
            "permitted_not_sent": sorted(permitted - sent),
            "discarded": [{"attempt": e["detail"].get("attempt"), "revoked": e["detail"].get("revoked"),
                           "answer": e["detail"].get("discarded_answer")}
                          for e in events if e["event"] == "answer_discarded"],
            "release": a["detail"].get("release") if a else "no_response_recorded",
            "answer": a["detail"].get("answer") if a else None,
            "cited": a["detail"].get("cited") if a else [],
            "generation": a["detail"].get("generation") if a else None,
            "terminal": next((e["event"] for e in reversed(events) if e["event"] in TERMINAL), None),
            # "unconfirmed" = no HTTP delivery record (e.g. direct Brain.ask, or a crash after release)
            "delivery": DELIVERY[outcome[-1]] if outcome else "unconfirmed",
        })
    return stories


PLATFORM_WORDS = {"confluence": "confluence", "jira": "jira", "slack": "slack", "drive": "gdrive", "gdrive": "gdrive"}


def parse_question(text: str) -> dict:
    """Tiny NL -> filter parser for compliance questions. Swap for an LLM tool call later."""
    t = text.lower()
    f: dict = {}
    m = re.search(r"user\s+['\"]?([a-z0-9_.-]+)['\"]?", t)
    if m:
        f["actor"] = m.group(1)
    for w, p in PLATFORM_WORDS.items():
        if re.search(rf"\b{w}\b", t):
            f["platform"] = p
    quoted = re.findall(r"['\"]([^'\"]+)['\"]", text)
    for q in quoted:
        if q.lower() != f.get("actor"):
            if ":" in q:
                f["doc_uid"] = q
            else:
                f["container"] = q.lower()
    m = re.search(r"last (\d+) (day|week|hour)s?", t)
    if m:
        f["since"] = time.time() - int(m.group(1)) * {"day": 86400, "week": 604800, "hour": 3600}[m.group(2)]
    elif "last week" in t:
        f["since"] = time.time() - 604800
    if "denied" in t or "blocked" in t:
        f["decision"] = "denied"
    elif "accessed" in t or "retrieved" in t or "saw" in t:
        f["decision"] = "allowed"
    if "who" in t and "doc_uid" in f:
        f.pop("actor", None)
    return f
