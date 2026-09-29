"""Security log + audit trail: tamper-evident, complete, queryable.

Tamper-evident
  Each row stores the SHA-256 of the previous row (hash chain). Editing or
  deleting any row breaks every hash after it. Every ANCHOR_EVERY rows the
  current head hash is written to an external anchor file (WORM storage in
  production), so an attacker who rewrites the WHOLE chain, or truncates the
  tail, still gets caught because the anchors no longer match.

Complete
  Per query we record: who, the question, the plan, an allow/deny decision for
  every candidate document (with reason), what was sent to the model, and the
  final answer.

Queryable
  Denormalised columns (actor, platform, container, doc_uid, decision) make
  compliance questions plain SQL, and `parse_question()` turns
  "everything user 'jdoe' accessed in 'payment-gateway' last 30 days" into filters.
"""
import hashlib
import json
import re
import sqlite3
import threading
import time
from contextlib import closing

from .config import ANCHOR_EVERY, ANCHOR_PATH, AUDIT_DB, PROBE_ALERT_THRESHOLD

GENESIS = "0" * 64
COLS = ["ts", "actor", "event", "severity", "query_id", "platform", "container", "doc_uid", "decision", "detail"]
_lock = threading.Lock()


def _conn():
    c = sqlite3.connect(AUDIT_DB)
    c.row_factory = sqlite3.Row
    return c


def init():
    with closing(_conn()) as c:
        c.execute(f"""CREATE TABLE IF NOT EXISTS audit_log (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            {', '.join(f'{col} TEXT' for col in COLS)},
            prev_hash TEXT NOT NULL, hash TEXT NOT NULL)""")
        for col in ("actor", "doc_uid", "container", "query_id", "ts"):
            c.execute(f"CREATE INDEX IF NOT EXISTS ix_{col} ON audit_log({col})")
        c.commit()


def _hash(values: list, prev: str) -> str:
    return hashlib.sha256(json.dumps(values + [prev], default=str).encode()).hexdigest()


def log(actor: str, event: str, *, severity: str = "info", query_id: str = "", platform: str = "",
        container: str = "", doc_uid: str = "", decision: str = "", **detail) -> int:
    """severity: info | warning | alert"""
    row = [f"{time.time():.6f}", actor, event, severity, query_id, platform, container, doc_uid, decision,
           json.dumps(detail, sort_keys=True, default=str)]
    with _lock, closing(_conn()) as c:
        last = c.execute("SELECT id, hash FROM audit_log ORDER BY id DESC LIMIT 1").fetchone()
        prev = last["hash"] if last else GENESIS
        h = _hash(row, prev)
        cur = c.execute(f"INSERT INTO audit_log ({', '.join(COLS)}, prev_hash, hash) VALUES ({', '.join('?' * (len(COLS) + 2))})",
                        row + [prev, h])
        c.commit()
        new_id = cur.lastrowid
    if new_id % ANCHOR_EVERY == 0:
        anchor()
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


def anchor() -> dict:
    with closing(_conn()) as c:
        r = c.execute("SELECT id, hash FROM audit_log ORDER BY id DESC LIMIT 1").fetchone()
    if not r:
        return {}
    a = {"id": r["id"], "hash": r["hash"], "anchored_at": time.time()}
    with open(ANCHOR_PATH, "a") as f:
        f.write(json.dumps(a) + "\n")
    return a


def verify() -> dict:
    prev, by_id, last_id = GENESIS, {}, 0
    with closing(_conn()) as c:
        for r in c.execute("SELECT * FROM audit_log ORDER BY id"):
            if r["id"] != last_id + 1:
                return {"ok": False, "problem": "row deleted (gap in ids)", "at_id": last_id + 1}
            if r["prev_hash"] != prev or r["hash"] != _hash([r[col] for col in COLS], prev):
                return {"ok": False, "problem": "row modified", "at_id": r["id"]}
            prev, last_id = r["hash"], r["id"]
            by_id[r["id"]] = r["hash"]
    anchors = []
    if ANCHOR_PATH.exists():
        anchors = [json.loads(line) for line in ANCHOR_PATH.read_text().splitlines() if line.strip()]
    for a in anchors:
        if a["id"] not in by_id:
            return {"ok": False, "problem": "log truncated (anchored row missing)", "at_id": a["id"]}
        if by_id[a["id"]] != a["hash"]:
            return {"ok": False, "problem": "chain rewritten (anchor mismatch)", "at_id": a["id"]}
    return {"ok": True, "rows": last_id, "anchors_checked": len(anchors)}


def search(actor=None, event=None, platform=None, container=None, doc_uid=None, decision=None,
           query_id=None, since=None, until=None, severity=None, limit=500) -> list[dict]:
    where, args = [], []
    for col, val in [("actor", actor), ("event", event), ("platform", platform), ("container", container),
                     ("doc_uid", doc_uid), ("decision", decision), ("query_id", query_id), ("severity", severity)]:
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
    return [{**{k: r[k] for k in r.keys() if k != "detail"}, "ts": float(r["ts"]), "detail": json.loads(r["detail"])}
            for r in rows]


def reconstruct(**filters) -> list[dict]:
    """Group matching document decisions back into full query stories:
    who asked what, what was retrieved/denied, and what was answered."""
    hits = search(**filters)
    qids = []
    for h in hits:
        if h["query_id"] and h["query_id"] not in qids:
            qids.append(h["query_id"])
    stories = []
    for qid in qids:
        events = list(reversed(search(query_id=qid)))
        q = next((e for e in events if e["event"] == "query_received"), None)
        a = next((e for e in events if e["event"] == "answer_returned"), None)
        stories.append({
            "query_id": qid,
            "ts": q["ts"] if q else events[0]["ts"],
            "actor": events[0]["actor"],
            "question": q["detail"].get("question") if q else None,
            "matched": [{"doc_uid": h["doc_uid"], "decision": h["decision"], "stage": h["detail"].get("stage"),
                         "reason": h["detail"].get("reason")}
                        for h in hits if h["query_id"] == qid and h["doc_uid"]],
            "decisions": [{"doc_uid": e["doc_uid"], "platform": e["platform"], "container": e["container"],
                           "decision": e["decision"], "stage": e["detail"].get("stage"),
                           "reason_code": e["detail"].get("reason_code"), "reason": e["detail"].get("reason"),
                           "resource_version": e["detail"].get("resource_version"),
                           "platform_account": e["detail"].get("platform_account"),
                           "checked_at": e["detail"].get("checked_at")}
                          for e in events if e["event"] == "authz_decision"],
            # exactly which document versions the model saw, per generation attempt
            "context_sent": [{"attempt": e["detail"].get("attempt"), "docs": e["detail"].get("context")}
                             for e in events if e["event"] == "context_assembled"],
            "discarded": [{"attempt": e["detail"].get("attempt"), "revoked": e["detail"].get("revoked"),
                           "answer": e["detail"].get("discarded_answer")}
                          for e in events if e["event"] == "answer_discarded"],
            "release": a["detail"].get("release") if a else "no_response_recorded",
            "answer": a["detail"].get("answer") if a else None,
            "cited": a["detail"].get("cited") if a else [],
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
