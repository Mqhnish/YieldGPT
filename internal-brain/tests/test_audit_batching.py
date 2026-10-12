"""Permission phases append their audit rows in one transaction. Coverage, order,
sealing and the hash chain must be exactly what per-row logging produced."""
import pytest

from app import audit
from app.brain import Brain
from app.identity import USERS

Q = "What was the root cause of the payment outage last quarter, and what follow-up tickets were created?"
FIELDS = ("actor", "event", "query_id", "platform", "container", "doc_uid", "decision")


def _strip(rows):
    return [tuple(r[k] for k in FIELDS) for r in rows]


def test_batched_rows_match_per_row_logging_and_chain_verifies():
    per_row = []

    def sink(actor, event, **f):
        per_row.append((actor, event, f.get("query_id", ""), f.get("platform", ""), f.get("container", ""),
                        f.get("doc_uid", ""), f.get("decision", "")))
        return audit.log(actor, event, **f)   # not `is audit.log`, so Brain logs row by row

    for user in ("ravi", "kim", "priya"):
        Brain().ask(USERS[user], Q)                       # default sink: batched
    batched = _strip(sorted(audit.search(limit=100000), key=lambda r: r["id"]))
    audit.init()
    with audit._conn() as c:
        c.execute("DELETE FROM audit_log")
        c.execute("DELETE FROM audit_content")
    b = Brain(event_sink=sink)
    for user in ("ravi", "kim", "priya"):
        b.ask(USERS[user], Q)
    # query ids differ per run; compare everything else, in order
    norm = lambda rows: [(a, e, p, c, d, dec) for a, e, _q, p, c, d, dec in rows]  # noqa: E731
    assert [r for r in norm(batched) if r[1] == "authz_decision"]
    assert norm(batched) == norm(per_row)


def test_batched_question_keeps_sealed_text_and_verifies():
    r = Brain().ask(USERS["ravi"], Q)
    rows = audit.search(query_id=r["query_id"], event="authz_decision", limit=100000)
    assert rows and all(row["decision"] in ("allowed", "denied", "unavailable") for row in rows)
    audit.checkpoint()
    assert audit.verify()["ok"], audit.verify()
    assert all(row["detail"].get("title") for row in rows)          # sealed field round-trips


def test_failed_batch_write_fails_closed_and_commits_nothing(monkeypatch):
    b = Brain()
    real = audit._append
    calls = {"n": 0}

    def flaky(c, actor, event, *a):
        if event == "authz_decision":
            calls["n"] += 1
            if calls["n"] == 3:
                raise RuntimeError("disk full")
        return real(c, actor, event, *a)

    monkeypatch.setattr(audit, "_append", flaky)
    with pytest.raises(RuntimeError):
        b.ask(USERS["ravi"], Q)
    # the failing batch rolled back as a whole; no answer was recorded or returned
    assert audit.search(event="authz_decision", limit=100000) == []
    assert audit.search(event="answer_returned") == []
    monkeypatch.setattr(audit, "_append", real)
    audit.checkpoint()
    assert audit.verify()["ok"], audit.verify()


def test_batch_crossing_anchor_boundary_checkpoints(monkeypatch):
    monkeypatch.setattr(audit, "ANCHOR_EVERY", 7)
    hits = []
    monkeypatch.setattr(audit, "try_checkpoint", lambda: hits.append(1) or {})
    audit.log_many([("t", "e", {}) for _ in range(6)])     # ids 1..6: no multiple of 7
    assert hits == []
    audit.log_many([("t", "e", {}) for _ in range(3)])     # ids 7..9: crosses 7
    assert hits == [1]


def test_batched_denials_still_raise_probing_alert(monkeypatch):
    monkeypatch.setattr(audit, "PROBE_ALERT_THRESHOLD", 3)
    # One broad batch over many docs is routine; the same doc denied in separate attempts is probing.
    audit.log_many([("mallory", "authz_decision", {"decision": "denied", "doc_uid": f"d{i}"}) for i in range(5)])
    assert not audit.search(actor="mallory", event="probing_suspected")
    audit.log_many([("mallory", "authz_decision", {"decision": "denied", "doc_uid": "d0", "query_id": f"q{i}"})
                    for i in range(3)])
    assert len(audit.search(actor="mallory", event="probing_suspected")) == 1
