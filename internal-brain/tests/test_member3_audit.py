"""Member 3: audit persistence, protected checkpoints and the verifier.

Tamper matrix (modified row, middle deletion, whole-chain rewrite, anchored and
unanchored tail deletion, equivocation, missing/unreachable checkpoint storage),
concurrent appends across threads and processes, restart recovery, and sealed text.
"""
import multiprocessing
import sqlite3
import threading
from pathlib import Path

import pytest

from app import audit, checkpoints, reliability

from .conftest import cited

QUESTION = "What's the status of the database migration project and were there any blockers raised in Slack last week?"


def fill(n):
    for i in range(n):
        audit.log("tester", "event", i=i)


def db():
    return sqlite3.connect(audit.AUDIT_DB)


def rewrite_all_hashes():
    """Attacker with DB write access recomputes the whole chain after an edit."""
    with db() as c:
        prev = audit.GENESIS
        for r in c.execute("SELECT * FROM audit_log ORDER BY id").fetchall():
            h = audit._hash(list(r[1:1 + len(audit.COLS)]), prev)
            c.execute("UPDATE audit_log SET prev_hash=?, hash=? WHERE id=?", (prev, h, r[0]))
            prev = h


class DownStore:
    kind = "s3_object_lock"

    def checkpoints(self):
        raise checkpoints.CheckpointError("checkpoint store unreachable (ConnectError)")

    def assurance(self):
        raise checkpoints.CheckpointError("unreachable")

    def append(self, *a):
        raise checkpoints.CheckpointError("unreachable")


# ---------------------------------------------------------------- verified / failed / unverifiable
def test_clean_log_is_verified_through_its_last_checkpoint():
    fill(25)
    audit.checkpoint()
    r = audit.verify_report()
    assert r["status"] == "verified" and r["verified_through"] == 25 and r["uncheckpointed_rows"] == 0
    assert r["assurance"] == "local_only" and not r["fully_verified"]   # a local file is never independent


def test_modified_row_fails():
    fill(5)
    audit.checkpoint()
    with db() as c:
        c.execute("UPDATE audit_log SET actor='someone-else' WHERE id=3")
    r = audit.verify_report()
    assert (r["status"], r["problem"], r["at_id"]) == ("failed", "row modified", 3)


def test_middle_deletion_fails():
    fill(5)
    audit.checkpoint()
    with db() as c:
        c.execute("DELETE FROM audit_log WHERE id=3")
    assert audit.verify_report()["problem"] == "row deleted (gap in ids)"


def test_whole_chain_rewrite_fails_against_checkpoint():
    fill(10)
    audit.checkpoint()
    with db() as c:
        c.execute("UPDATE audit_log SET event='forged' WHERE id=2")
    rewrite_all_hashes()
    r = audit.verify_report()
    assert (r["status"], r["problem"], r["at_id"]) == ("failed", "chain rewritten (anchor mismatch)", 10)


def test_anchored_tail_deletion_fails():
    fill(10)
    audit.checkpoint()
    fill(5)
    with db() as c:
        c.execute("DELETE FROM audit_log WHERE id>=8")
    r = audit.verify_report()
    assert (r["status"], r["problem"], r["at_id"]) == ("failed", "log truncated (anchored row missing)", 10)


def test_unanchored_tail_is_never_reported_as_verified():
    fill(10)
    audit.checkpoint()
    fill(5)                                   # rows 11-15: after the last checkpoint
    r = audit.verify_report()
    assert r["status"] == "verified" and r["verified_through"] == 10 and r["uncheckpointed_rows"] == 5
    assert not r["fully_verified"]
    with db() as c:                           # deleting the unanchored tail cannot be proven...
        c.execute("DELETE FROM audit_log WHERE id>10")
    r = audit.verify_report()
    assert r["verified_through"] == 10        # ...and nothing after row 10 was ever claimed
    fill(1)                                   # but the next append exposes the gap (AUTOINCREMENT)
    assert audit.verify_report()["problem"] == "row deleted (gap in ids)"


def test_conflicting_checkpoints_fail():
    fill(5)
    audit.checkpoint()
    audit._store().append(5, "f" * 64)        # a second, different head for the same row
    r = audit.verify_report()
    assert (r["status"], r["at_id"]) == ("failed", 5) and "equivocation" in r["problem"]


def test_unreachable_checkpoint_store_is_unverifiable():
    fill(5)
    audit.checkpoint()
    r = audit.verify_report(store=DownStore())
    assert r["status"] == "unverifiable" and not r["ok"] and "unreachable" in r["problem"]
    with db() as c:                           # a definite tamper is still reported as failed
        c.execute("UPDATE audit_log SET actor='x' WHERE id=2")
    assert audit.verify_report(store=DownStore())["status"] == "failed"


def test_log_without_any_checkpoint_is_unverifiable():
    fill(3)
    r = audit.verify_report()
    assert r["status"] == "unverifiable" and r["problem"] == "no committed checkpoints in the protected store"
    assert audit.verify() == {"ok": False, "problem": r["problem"], "at_id": None}


# ---------------------------------------------------------------- concurrency
def test_concurrent_thread_appends_keep_one_ordered_chain():
    threads = [threading.Thread(target=fill, args=(40,)) for _ in range(8)]
    for t in threads:
        t.start()
    for t in threads:
        t.join()
    audit.checkpoint()
    r = audit.verify_report()
    assert r["status"] == "verified" and r["rows"] == 320


def _process_worker(db_path, anchors, n):
    from app import audit as child_audit
    child_audit.AUDIT_DB, child_audit.ANCHOR_PATH = Path(db_path), Path(anchors)
    for i in range(n):
        child_audit.log("worker", "event", i=i)


def test_concurrent_process_appends_keep_one_ordered_chain():
    ctx = multiprocessing.get_context("spawn")
    procs = [ctx.Process(target=_process_worker, args=(str(audit.AUDIT_DB), str(audit.ANCHOR_PATH), 40))
             for _ in range(4)]
    for p in procs:
        p.start()
    for p in procs:
        p.join(60)
        assert p.exitcode == 0
    audit.checkpoint()
    r = audit.verify_report()
    assert r["status"] == "verified" and r["rows"] == 160


# ---------------------------------------------------------------- restart recovery
def test_restart_recovery_gives_interrupted_requests_a_terminal_record():
    audit.log("jdoe", "request_received", request_id="r1")
    audit.log("jdoe", "query_received", query_id="q1", request_id="r1", question="What changed?")
    # process dies here: no answer_returned, no delivery
    assert audit.recover_interrupted() == 1
    assert audit.recover_interrupted() == 0   # idempotent
    story = audit.reconstruct(query_id="q1")[0]
    assert story["request_id"] == "r1" and story["terminal"] == "request_abandoned"
    assert story["delivery"] == "abandoned" and story["release"] == "no_response_recorded"


# ---------------------------------------------------------------- sealed text + retention
def raw_db_bytes():
    return b"".join(p.read_bytes() for p in Path(audit.AUDIT_DB).parent.glob(Path(audit.AUDIT_DB).name + "*")
                    if not p.name.endswith(".key"))


def test_questions_and_answers_are_sealed_at_rest(ask):
    r = ask("jdoe", QUESTION)
    assert cited(r)
    raw = raw_db_bytes()
    assert QUESTION.encode() not in raw and b"replication lag" not in raw
    story = audit.reconstruct(query_id=r["query_id"])[0]            # the audit read path still opens it
    assert story["question"] == QUESTION and "replication lag" in story["answer"].lower()


def test_retention_redacts_text_and_the_chain_still_verifies(ask, monkeypatch):
    monkeypatch.setenv("IB_AUDIT_TEXT_RETENTION_DAYS", "0")
    r = ask("jdoe", QUESTION)
    assert audit.apply_retention() > 0
    audit.checkpoint()
    report = audit.verify_report()
    assert report["status"] == "verified" and report["content"]["redacted"] > 0
    assert audit.reconstruct(query_id=r["query_id"])[0]["question"] == audit.REDACTED


def test_redaction_shorter_than_policy_is_detected(ask):
    ask("jdoe", QUESTION)                     # policy is 90 days
    audit.apply_retention(days=0)             # an operator deletes text early
    audit.checkpoint()
    assert audit.verify_report()["problem"] == "sealed content deleted without retention record"


def test_deleted_or_swapped_sealed_text_fails():
    a = audit.log("jdoe", "query_received", question="first question")
    b = audit.log("jdoe", "query_received", question="second question")
    audit.checkpoint()
    with db() as c:
        ra = c.execute("SELECT nonce, ciphertext FROM audit_content WHERE row_id=?", (a,)).fetchone()
        rb = c.execute("SELECT nonce, ciphertext FROM audit_content WHERE row_id=?", (b,)).fetchone()
        c.execute("UPDATE audit_content SET nonce=?, ciphertext=? WHERE row_id=?", (*rb, a))
        c.execute("UPDATE audit_content SET nonce=?, ciphertext=? WHERE row_id=?", (*ra, b))
    assert audit.verify_report()["problem"] == "sealed content altered"
    with db() as c:
        c.execute("DELETE FROM audit_content WHERE row_id=?", (a,))
    assert audit.verify_report()["problem"] == "sealed content deleted without retention record"


def test_without_cryptography_refuses_plaintext_persistence(monkeypatch):
    monkeypatch.setattr(audit, "encryption_available", lambda: False)
    with pytest.raises(RuntimeError, match="refusing plaintext"):
        audit.log("jdoe", "query_received", question="plain")
    with db() as c:
        assert not c.execute("SELECT * FROM audit_content").fetchall()
    assert not audit.search(event="query_received")


def test_pre_member3_schema_is_refused(tmp_path, monkeypatch):
    legacy = tmp_path / "legacy.db"
    with sqlite3.connect(legacy) as c:
        c.execute("CREATE TABLE audit_log (id INTEGER PRIMARY KEY, ts TEXT, prev_hash TEXT, hash TEXT)")
    monkeypatch.setattr(audit, "AUDIT_DB", legacy)
    with pytest.raises(RuntimeError, match="pre-Member-3"):
        audit.init()
