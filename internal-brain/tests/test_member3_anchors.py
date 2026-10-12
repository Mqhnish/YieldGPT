"""Member 3: two independent checkpoint anchors (A09).

An attacker who rewrites the local audit DB, and even replaces every anchor in one
store, cannot make verification pass while the other anchor still holds the truth.
"""
import json
import os
import sqlite3
import uuid

import pytest

from app import audit, checkpoints
from app.checkpoints import CheckpointError, LocalCheckpointStore, MultiAnchorStore, S3ObjectLockStore


@pytest.fixture
def two(tmp_path, monkeypatch):
    store = MultiAnchorStore([LocalCheckpointStore(tmp_path / "a.jsonl"), LocalCheckpointStore(tmp_path / "b.jsonl")])
    monkeypatch.setattr(audit, "_store", lambda: store)
    return store


def commit(n):
    for i in range(n):
        audit.log("tester", "event", i=i)
    audit.checkpoint()


def forge_anchors(store, new_hash):
    store.path.write_text("".join(json.dumps({**cp, "hash": new_hash}) + "\n" for cp in store.checkpoints()))


def test_every_checkpoint_lands_in_both_anchors(two):
    commit(5)
    a, b = (s.checkpoints() for s in two.stores)
    assert a and [cp["hash"] for cp in a] == [cp["hash"] for cp in b]
    assert audit.verify_report()["status"] == "verified"


def test_replacing_one_anchor_is_detected_as_equivocation(two):
    commit(5)
    forge_anchors(two.stores[0], "f" * 64)
    r = audit.verify_report()
    assert r["status"] == "failed" and "equivocation" in r["problem"]


def test_rewriting_chain_and_one_anchor_still_fails(two):
    commit(5)
    head = audit.head()
    with sqlite3.connect(audit.AUDIT_DB) as c:  # attacker recomputes the chain locally ...
        c.execute("UPDATE audit_log SET hash=? WHERE id=?", ("e" * 64, head[0]))
    forge_anchors(two.stores[0], "e" * 64)     # ... and replaces every anchor in store 1
    assert audit.verify_report()["status"] == "failed"


def test_one_anchor_refusing_a_write_fails_the_checkpoint(two, monkeypatch):
    def refuse(*_):
        raise CheckpointError("checkpoint store refused write (HTTP 403)")
    monkeypatch.setattr(two.stores[1], "append", refuse)
    audit.log("tester", "event")
    with pytest.raises(CheckpointError, match="anchor 2"):
        audit.checkpoint()


def test_local_anchors_are_never_reported_independent(two):
    assert two.assurance() == "local_only+local_only"


def test_from_env_builds_one_store_per_numbered_endpoint(tmp_path, monkeypatch):
    for var in ("S3_ENDPOINT", "S3_ENDPOINT_2", "S3_ENDPOINT_3"):
        monkeypatch.delenv(f"IB_CHECKPOINT_{var}", raising=False)
    assert isinstance(checkpoints.from_env(tmp_path / "x"), LocalCheckpointStore)
    monkeypatch.setenv("IB_CHECKPOINT_S3_ENDPOINT", "http://a:9000")
    assert isinstance(checkpoints.from_env(tmp_path / "x"), S3ObjectLockStore)
    monkeypatch.setenv("IB_CHECKPOINT_S3_ENDPOINT_2", "http://b:9000")
    monkeypatch.setenv("IB_CHECKPOINT_S3_BUCKET_2", "anchor-b")
    store = checkpoints.from_env(tmp_path / "x")
    assert isinstance(store, MultiAnchorStore)
    assert [(s.endpoint, s.bucket) for s in store.stores] == [("http://a:9000", "audit-checkpoints"),
                                                              ("http://b:9000", "anchor-b")]
    assert store.kind == "multi(s3_object_lock,s3_object_lock)"


# ---------------------------------------------------------------- live: two MinIO / S3 services
live2 = pytest.mark.skipif(not (os.getenv("IB_TEST_S3_ENDPOINT") and os.getenv("IB_TEST_S3_ENDPOINT_2")),
                           reason="set IB_TEST_S3_ENDPOINT and IB_TEST_S3_ENDPOINT_2 (+ _2 credentials)")


def _live_store(suffix, prefix):
    e = lambda n, d="": os.getenv(f"IB_TEST_{n}{suffix}", d)  # noqa: E731
    return S3ObjectLockStore(e("S3_ENDPOINT"), e("S3_BUCKET", "audit-checkpoints"), prefix, "us-east-1",
                             (e("WRITER_KEY"), e("WRITER_SECRET")), (e("READER_KEY"), e("READER_SECRET")))


def _rewrite_chain():
    with sqlite3.connect(audit.AUDIT_DB) as c:
        c.execute("UPDATE audit_log SET event='forged' WHERE id=4")
        prev = audit.GENESIS
        for r in c.execute("SELECT * FROM audit_log ORDER BY id").fetchall():
            h = audit._hash(list(r[1:1 + len(audit.COLS)]), prev)
            c.execute("UPDATE audit_log SET prev_hash=?, hash=? WHERE id=?", (prev, h, r[0]))
            prev = h


@live2
def test_live_two_anchors_survive_full_compromise_of_one(monkeypatch):
    run = uuid.uuid4().hex[:10]
    a, b = _live_store("", f"a2-{run}/"), _live_store("_2", f"a2-{run}/")
    both = MultiAnchorStore([a, b])
    monkeypatch.setattr(audit, "_store", lambda: both)
    for i in range(12):
        audit.log("tester", "event", i=i)
    audit.checkpoint()
    report = audit.verify_report()
    assert report["status"] == "verified" and report["assurance"] == "independent_worm"
    assert {cp["anchor"] for cp in both.checkpoints()} == {1, 2}

    # Attacker rewrites the whole local chain and fully controls anchor 1 (a fresh namespace
    # holding only forged checkpoints that match the rewritten chain). Anchor 2 is untouched.
    _rewrite_chain()
    forged = _live_store("", f"a2-{run}-forged/")
    forged.append(*audit.head())
    assert audit.verify_report(store=forged)["status"] == "verified"           # one anchor alone is fooled
    r = audit.verify_report(store=MultiAnchorStore([forged, b]))
    assert r["status"] == "failed" and "equivocation" in r["problem"]            # the second anchor is not
