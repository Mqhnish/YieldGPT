"""Member 3: S3 Object Lock checkpoint store.

Offline: SigV4 against AWS's published examples, and listing/lock parsing.
Live (skipped unless IB_TEST_S3_ENDPOINT is set, e.g. against deploy/docker-compose.yml):
the app's writer credential cannot delete or replace committed checkpoints, the bucket
enforces COMPLIANCE mode, and tampering is detected end to end.

    IB_TEST_S3_ENDPOINT=http://127.0.0.1:9000 IB_TEST_S3_BUCKET=audit-checkpoints \
    IB_TEST_WRITER_KEY=... IB_TEST_WRITER_SECRET=... IB_TEST_READER_KEY=... IB_TEST_READER_SECRET=... \
    IB_TEST_ROOT_KEY=... IB_TEST_ROOT_SECRET=... python -m pytest tests/test_member3_s3.py
"""
import os
import sqlite3
import uuid
from datetime import datetime, timezone

import httpx
import pytest

from app import audit, checkpoints
from app.checkpoints import EMPTY_SHA256, S3ObjectLockStore, sigv4_headers

AWS = ("AKIAIOSFODNN7EXAMPLE", "wJalrXUtnFEMI/K7MDENG/bPxRfiCYEXAMPLEKEY")


@pytest.mark.parametrize("url, headers, signature", [
    ("https://examplebucket.s3.amazonaws.com/test.txt", {"range": "bytes=0-9"},
     "f0e8bdb87c964420e857bd35b5d6ed310bd44f0170aba48dd91039c6036bdb41"),
    ("https://examplebucket.s3.amazonaws.com/?lifecycle", {},
     "fea454ca298b7da1c68078a5d1bdbfbbe0d65c699e0f91ac7a200a0136783543"),
    ("https://examplebucket.s3.amazonaws.com/?max-keys=2&prefix=J", {},
     "34b48302e7b5fa45bde8084f4b7868a86f0a534bc59db6670ed5711ef69dc6f7"),
])
def test_sigv4_matches_aws_published_examples(url, headers, signature):
    h = sigv4_headers("GET", url, headers, EMPTY_SHA256, *AWS, "us-east-1", datetime(2013, 5, 24, tzinfo=timezone.utc))
    assert h["Authorization"].endswith("Signature=" + signature)


NS = 'xmlns="http://s3.amazonaws.com/doc/2006-03-01/"'
H1, H2 = "a" * 64, "b" * 64
PAGES = [
    f"""<ListVersionsResult {NS}><IsTruncated>true</IsTruncated><NextKeyMarker>c/000000000020-{H1}</NextKeyMarker>
        <NextVersionIdMarker>v1</NextVersionIdMarker>
        <Version><Key>c/000000000020-{H1}</Key><VersionId>v1</VersionId><LastModified>2026-09-29T00:00:00Z</LastModified></Version>
        <DeleteMarker><Key>c/000000000020-{H1}</Key><VersionId>v2</VersionId></DeleteMarker></ListVersionsResult>""",
    f"""<ListVersionsResult {NS}><IsTruncated>false</IsTruncated>
        <Version><Key>c/000000000040-{H2}</Key><VersionId>v3</VersionId><LastModified>2026-09-29T00:01:00Z</LastModified></Version>
        <Version><Key>c/not-a-checkpoint</Key><VersionId>v4</VersionId></Version></ListVersionsResult>""",
]
LOCK = (f"<ObjectLockConfiguration {NS}><ObjectLockEnabled>Enabled</ObjectLockEnabled><Rule><DefaultRetention>"
        "<Mode>COMPLIANCE</Mode><Days>30</Days></DefaultRetention></Rule></ObjectLockConfiguration>")


def test_listing_counts_versions_hidden_by_delete_markers_and_pages(monkeypatch):
    seen = []

    def fake(method, url, **kw):
        seen.append(url)
        if "object-lock" in url:
            return httpx.Response(200, content=LOCK.encode())
        return httpx.Response(200, content=PAGES[len(seen) - 1].encode())

    monkeypatch.setattr(checkpoints._HTTP, "request", fake)
    store = S3ObjectLockStore("http://s3.test", "b", "c/", "us-east-1", ("w", "w"), ("r", "r"))
    assert [(c["row_id"], c["hash"]) for c in store.checkpoints()] == [(20, H1), (40, H2)]
    assert "key-marker=" in seen[1] and "version-id-marker=v1" in seen[1]
    assert store.assurance() == "independent_worm"


def test_lock_config_without_xml_namespace_is_understood(monkeypatch):
    bare = LOCK.replace(f" {NS}", "")                    # MinIO omits the namespace here
    monkeypatch.setattr(checkpoints._HTTP, "request", lambda *a, **k: httpx.Response(200, content=bare.encode()))
    assert S3ObjectLockStore("http://s3.test", "b", "c/", "us-east-1", ("w", "w"), ("r", "r")).assurance() \
        == "independent_worm"


def test_bucket_without_compliance_lock_is_not_independent(monkeypatch):
    governance = LOCK.replace("COMPLIANCE", "GOVERNANCE")
    monkeypatch.setattr(checkpoints._HTTP, "request", lambda *a, **k: httpx.Response(200, content=governance.encode()))
    assert S3ObjectLockStore("http://s3.test", "b", "c/", "us-east-1", ("w", "w"), ("r", "r")).assurance() \
        == "unprotected_bucket"


def test_store_errors_never_carry_credentials(monkeypatch):
    def refuse(*a, **k):
        raise httpx.ConnectError("boom secret-key-123")
    monkeypatch.setattr(checkpoints._HTTP, "request", refuse)
    store = S3ObjectLockStore("http://s3.test", "b", "c/", "us-east-1", ("w", "secret-key-123"), ("r", "r"))
    with pytest.raises(checkpoints.CheckpointError) as err:
        store.append(1, H1)
    assert "secret" not in str(err.value)


# ---------------------------------------------------------------- live MinIO / S3
live = pytest.mark.skipif(not os.getenv("IB_TEST_S3_ENDPOINT"), reason="set IB_TEST_S3_ENDPOINT for live S3 tests")


def _creds(role):
    return os.getenv(f"IB_TEST_{role}_KEY", ""), os.getenv(f"IB_TEST_{role}_SECRET", "")


@pytest.fixture
def s3(monkeypatch):
    prefix = f"test-{uuid.uuid4().hex[:10]}/"
    env = {"IB_CHECKPOINT_S3_ENDPOINT": os.environ["IB_TEST_S3_ENDPOINT"],
           "IB_CHECKPOINT_S3_BUCKET": os.getenv("IB_TEST_S3_BUCKET", "audit-checkpoints"),
           "IB_CHECKPOINT_S3_PREFIX": prefix,
           "IB_CHECKPOINT_WRITER_KEY": _creds("WRITER")[0], "IB_CHECKPOINT_WRITER_SECRET": _creds("WRITER")[1],
           "IB_CHECKPOINT_READER_KEY": _creds("READER")[0], "IB_CHECKPOINT_READER_SECRET": _creds("READER")[1]}
    for k, v in env.items():
        monkeypatch.setenv(k, v)
    return checkpoints.from_env(audit.ANCHOR_PATH)


def _versions(store, key):
    r = store._request("GET", f"?versions&prefix={key}", store.reader)
    return [v.findtext("VersionId", "") for v in checkpoints._xml(r.content).findall("Version")]


@live
def test_live_bucket_enforces_compliance_mode(s3):
    assert s3.assurance() == "independent_worm"


@live
def test_live_writer_cannot_delete_or_replace_checkpoints(s3):
    s3.append(7, H1)
    key = f"{s3.prefix}{7:012d}-{H1}"
    assert s3._request("DELETE", f"/{key}", s3.writer).status_code == 403
    version = _versions(s3, key)[0]
    assert s3._request("DELETE", f"/{key}?versionId={version}", s3.writer).status_code == 403
    assert s3._request("PUT", f"/{key}", s3.reader, b"x").status_code == 403          # reader cannot write
    s3.append(7, H1)                                                                   # re-put adds a version...
    assert version in _versions(s3, key) and len(_versions(s3, key)) == 2              # ...the original survives
    assert {(c["row_id"], c["hash"]) for c in s3.checkpoints()} == {(7, H1)}


@live
def test_live_even_root_cannot_delete_a_locked_version(s3):
    if not _creds("ROOT")[0]:
        pytest.skip("set IB_TEST_ROOT_KEY/SECRET to prove COMPLIANCE mode against the storage admin")
    s3.append(8, H2)
    key = f"{s3.prefix}{8:012d}-{H2}"
    version = _versions(s3, key)[0]
    r = s3._request("DELETE", f"/{key}?versionId={version}", _creds("ROOT"))
    assert r.status_code in (400, 403) and version in _versions(s3, key)


@live
def test_live_tampering_is_detected_end_to_end(s3):
    for i in range(12):
        audit.log("tester", "event", i=i)
    audit.checkpoint()
    report = audit.verify_report()
    assert report["status"] == "verified" and report["assurance"] == "independent_worm" and report["fully_verified"]
    with sqlite3.connect(audit.AUDIT_DB) as c:
        c.execute("UPDATE audit_log SET event='forged' WHERE id=4")
        prev = audit.GENESIS
        for r in c.execute("SELECT * FROM audit_log ORDER BY id").fetchall():
            h = audit._hash(list(r[1:1 + len(audit.COLS)]), prev)
            c.execute("UPDATE audit_log SET prev_hash=?, hash=? WHERE id=?", (prev, h, r[0]))
            prev = h
    assert audit.verify_report()["problem"] == "chain rewritten (anchor mismatch)"
