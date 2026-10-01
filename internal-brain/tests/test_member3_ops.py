"""Member 3: request lifecycle and release rule, audit access boundaries, compliance
queries, health/config checks, sync storage and maintenance (through app.server)."""
import threading
import time

import pytest
from fastapi.testclient import TestClient

from app import audit, config, main, reliability, server
from app.sync_state import ChangeRecord, SqliteSyncStateStore

from .test_member3_audit import QUESTION, DownStore


@pytest.fixture
def client():
    with TestClient(server.app) as c:
        yield c


def auth(c, user):
    token = c.post("/api/login", json={"username": user, "password": "demo"}).json()["token"]
    return {"Authorization": "Bearer " + token}


def events_for(request_id):
    return [e for e in reversed(audit.search(request_id=request_id, limit=1000))]


# ---------------------------------------------------------------- request lifecycle
def test_answer_is_released_only_after_a_covering_checkpoint(client):
    r = client.post("/api/ask", json={"question": QUESTION}, headers=auth(client, "jdoe"))
    assert r.status_code == 200 and r.json()["citations"]
    rid = r.headers["x-request-id"]
    names = [e["event"] for e in events_for(rid)]
    order = [names.index(n) for n in ("request_received", "query_received", "context_assembled",
                                      "answer_returned", "response_delivered")]
    assert order == sorted(order)
    answer_row = next(e["id"] for e in events_for(rid) if e["event"] == "answer_returned")
    assert audit.STATE["last_checkpoint"]["row_id"] >= answer_row
    story = audit.reconstruct(query_id=r.json()["query_id"])[0]
    assert story["request_id"] == rid and story["delivery"] == "delivered" and story["terminal"] == "answer_returned"
    assert all(d["version"] for attempt in story["context_sent"] for d in attempt["docs"])


def test_answer_is_withheld_when_no_checkpoint_can_be_committed(client, monkeypatch):
    monkeypatch.setattr(audit, "_store", lambda: DownStore())
    r = client.post("/api/ask", json={"question": QUESTION}, headers=auth(client, "jdoe"))
    assert r.status_code == 503
    assert "replication" not in r.text.lower() and "citations" not in r.text
    withheld = audit.search(event="response_withheld")[0]
    assert withheld["query_id"] and withheld["request_id"] == r.headers["x-request-id"]
    assert audit.reconstruct(query_id=withheld["query_id"])[0]["delivery"] == "withheld"


def test_pipeline_failure_records_a_terminal_failure_with_the_query_id(client, monkeypatch):
    def boom(*a, **k):
        raise RuntimeError("model adapter exploded")
    monkeypatch.setattr(main.brain(), "_generate", boom)
    r = client.post("/api/ask", json={"question": QUESTION}, headers=auth(client, "jdoe"))
    assert r.status_code == 503
    failed = audit.search(event="request_failed")[0]
    assert failed["query_id"] and failed["detail"]["status"] == 503
    story = audit.reconstruct(query_id=failed["query_id"])[0]
    assert story["terminal"] == "request_failed" and story["delivery"] == "failed"


def test_permitted_candidates_are_distinguished_from_context_sent(client):
    r = client.post("/api/ask", json={"question": "vendor payouts API integration notes"}, headers=auth(client, "kim"))
    story = audit.reconstruct(query_id=r.json()["query_id"])[0]
    sent = {d["uid"] for a in story["context_sent"] for d in a["docs"]}
    # DRV-5 is live-allowed for kim but quarantined as poisoned: permitted, never sent to the model
    assert "gdrive:DRV-5" in story["permitted_not_sent"] and "gdrive:DRV-5" not in sent


def test_server_startup_closes_requests_interrupted_by_a_restart():
    audit.log("jdoe", "request_received", request_id="before-crash")
    with TestClient(server.app):
        pass
    closed = audit.search(event="request_abandoned", request_id="before-crash")
    assert closed and audit.search(event="reliability_started")[0]["detail"]["abandoned_requests"] == 1


def test_unauthenticated_ask_is_recorded(client):
    r = client.post("/api/ask", json={"question": "anything"})
    assert r.status_code == 401
    rid = r.headers["x-request-id"]
    assert [(e["actor"], e["event"]) for e in events_for(rid)] == [("anonymous", "request_received"),
                                                                    ("anonymous", "request_failed")]


# ---------------------------------------------------------------- audit access boundaries
GET_ROUTES = ["/api/session", "/api/freshness", "/api/audit/events", "/api/audit/verify", "/api/sync/state",
              "/api/sync/changes", "/api/slack/maintenance", "/api/health", "/api/health/detail",
              "/api/audit/events?limit=500"]


def test_admin_and_employee_cannot_read_protected_audit_content(client):
    r = client.post("/api/ask", json={"question": QUESTION}, headers=auth(client, "jdoe"))
    qid, answer_line = r.json()["query_id"], r.json()["answer"].splitlines()[0][:40]
    for user in ("dana", "jdoe", "kim"):
        h = auth(client, user)
        for path in GET_ROUTES:
            body = client.get(path, headers=h).text
            assert QUESTION not in body and answer_line not in body, (user, path)
        for path, payload in [("/api/audit/query", {"question": "user 'jdoe'"}),
                              ("/api/compliance/requests", {"actor": "jdoe"}),
                              ("/api/audit/pseudonym", {"pseudonym": "user-0000000000"})]:
            assert client.post(path, json=payload, headers=h).status_code == 403, (user, path)
    assert client.get(f"/api/evidence/{qid}/S1", headers=auth(client, "dana")).status_code == 404
    full = client.post("/api/compliance/requests", json={"actor": "jdoe"}, headers=auth(client, "priya")).json()
    assert full["results"][0]["question"] == QUESTION
    denied = {e["actor"] for e in audit.search(event="audit_access_denied", limit=100)}
    assert {"dana", "jdoe", "kim"} <= denied


def test_compliance_filters_reconstruct_the_right_requests(client):
    t0 = time.time()
    jane = client.post("/api/ask", json={"question": QUESTION}, headers=auth(client, "jdoe")).json()
    client.post("/api/ask", json={"question": "What are the steps in the payment-gateway failover runbook?"},
                headers=auth(client, "ravi"))
    h = auth(client, "priya")

    def find(**f):
        return client.post("/api/compliance/requests", json=f, headers=h).json()["results"]

    stories = find(actor="jdoe", platform="slack", decision="allowed", since=t0, until=time.time() + 5)
    assert [s["query_id"] for s in stories] == [jane["query_id"]]
    assert find(actor="jdoe", until=t0 - 60) == []
    assert find(doc_uid="slack:T0COMPANYA/mig-leads/2101", decision="denied")[0]["actor"] == "jdoe"
    story = find(query_id=jane["query_id"])[0]
    assert {c["uid"] for c in jane["citations"]} <= {d["uid"] for a in story["context_sent"] for d in a["docs"]}


def test_pseudonym_resolution_is_compliance_only_and_audited(client):
    client.post("/api/ask", json={"question": QUESTION}, headers=auth(client, "jdoe"))
    events = client.get("/api/audit/events?limit=200", headers=auth(client, "dana")).json()["events"]
    token = next(e["actor"] for e in events if e["event"] == "query_received")
    assert token.startswith("user-")
    r = client.post("/api/audit/pseudonym", json={"pseudonym": token}, headers=auth(client, "priya"))
    assert r.json()["actor"] == "jdoe"
    assert client.post("/api/audit/pseudonym", json={"pseudonym": token}, headers=auth(client, "dana")).status_code == 403
    assert any(e["detail"].get("action") == "resolve_pseudonym" for e in audit.search(event="audit_accessed"))


def test_verifier_endpoint_reports_status_to_both_audit_scopes(client):
    for user in ("priya", "dana"):
        r = client.get("/api/audit/verify", headers=auth(client, user)).json()
        assert r["status"] in ("verified", "unverifiable") and "assurance" in r and "uncheckpointed_rows" in r


def test_compliance_page_is_served(client):
    assert "Compliance audit" in client.get("/compliance").text


# ---------------------------------------------------------------- health + configuration
def test_public_health_is_minimal_and_detail_is_admin_only(client):
    assert set(client.get("/api/health").json()) == {"status"}
    assert client.get("/api/health/detail", headers=auth(client, "jdoe")).status_code == 403
    d = client.get("/api/health/detail", headers=auth(client, "dana")).json()
    assert d["audit"]["writable"] and d["checkpoints"]["store"] == "local_file"
    assert "not a measured or guaranteed" in d["sync"]["note"] and "observed" in d["sync"]
    assert {"local_checkpoints", "demo_mode"} <= {p["code"] for p in d["config"]}


def test_observed_freshness_is_measured_per_path():
    now = time.time()
    records = [ChangeRecord("jira", "MIG-1", "upsert", "poll", now - 100, applied_at=now),
               ChangeRecord("jira", "MIG-7", "upsert", "poll", now - 40, applied_at=now),
               ChangeRecord("slack", "x", "upsert", "webhook", now - 1, applied_at=now),
               ChangeRecord("jira", "MIG-9", "upsert", "crawl", 0.0, applied_at=now),
               ChangeRecord("gdrive", "DRV-1", "upsert", "webhook", now, applied_at=now, outcome="failed")]
    f = reliability.observed_freshness(records)
    assert f["lag"]["jira"]["poll"]["n"] == 2 and f["lag"]["jira"]["poll"]["max_s"] == pytest.approx(100, abs=0.01)
    assert "crawl" not in f["lag"]["jira"] and f["recent_failures"] == {"gdrive": 1}


def test_unsafe_configuration_refuses_startup_outside_demo_mode(monkeypatch):
    monkeypatch.setattr(config, "DEMO_MODE", False)
    for name, dev in reliability.DEV_SECRETS.items():
        monkeypatch.setattr(config, name, dev)
    for var in ("IB_CHECKPOINT_S3_ENDPOINT", "IB_AUDIT_CONTENT_KEY"):
        monkeypatch.delenv(var, raising=False)
    codes = {p["code"] for p in reliability.fatal_problems()}
    assert {"dev_secret_key", "dev_webhook_secret", "dev_audit_pseudonym_key", "local_checkpoints",
            "content_key_beside_db"} <= codes
    with pytest.raises(RuntimeError, match="refusing to start"):
        with TestClient(server.app):
            pass


# ---------------------------------------------------------------- sync storage + maintenance
def test_sync_store_concurrent_writes_and_retention(tmp_path):
    store = SqliteSyncStateStore(tmp_path / "sync.db")
    old = time.time() - 10 * 86400

    def writer(n):
        for i in range(50):
            store.record(ChangeRecord("jira", f"K-{n}-{i}", "upsert", "poll", old, applied_at=old))
    threads = [threading.Thread(target=writer, args=(n,)) for n in range(4)]
    for t in threads:
        t.start()
    for t in threads:
        t.join()
    store.record(ChangeRecord("jira", "GONE-1", "delete", "poll", old, applied_at=old, outcome="removed"))
    store.record(ChangeRecord("jira", "NEW-1", "upsert", "poll", time.time()))
    assert len(store.recent(limit=1000)) == 202
    assert store.prune(max_age_s=86400) == 200
    assert {c.native_id for c in store.recent(limit=1000)} == {"GONE-1", "NEW-1"}   # tombstone kept
    assert store.tombstone("jira", "GONE-1") is not None


def test_maintenance_checkpoints_new_rows(monkeypatch):
    for i in range(3):
        audit.log("tester", "event", i=i)
    reliability.Maintenance().tick()
    assert audit.STATE["last_checkpoint"]["row_id"] == audit.head()[0]
    assert audit.verify_report()["status"] == "verified"


# ---------------------------------------------------------------- per-platform webhook signatures
def test_webhooks_use_each_platforms_signature_scheme(client, monkeypatch):
    import hashlib
    import hmac
    monkeypatch.setitem(config.WEBHOOK_SECRETS, "jira", "jira-secret")
    monkeypatch.setitem(config.WEBHOOK_SECRETS, "gdrive", "drive-token")
    raw = b'{"native_id": "MIG-1", "kind": "upsert"}'
    sig = "sha256=" + hmac.new(b"jira-secret", raw, hashlib.sha256).hexdigest()
    post = lambda p, body, h: client.post(f"/api/webhooks/{p}", content=body, headers=h).status_code  # noqa: E731

    assert post("jira", raw, {"x-hub-signature": sig}) == 200
    assert post("jira", raw.replace(b"MIG-1", b"MIG-2"), {"x-hub-signature": sig}) == 401   # body tampered
    assert post("jira", raw, {"x-webhook-secret": config.WEBHOOK_SECRET}) == 401           # old shared header
    assert post("gdrive", raw, {"x-goog-channel-token": "drive-token"}) == 200
    assert post("gdrive", raw, {"x-goog-channel-token": "jira-secret"}) == 401             # no cross-platform reuse
    assert post("nope", raw, {}) == 404
    assert audit.search(event="webhook_rejected", limit=10)


def test_shared_webhook_secret_is_flagged_and_unused_default_is_not(monkeypatch):
    monkeypatch.setattr(config, "WEBHOOK_SECRET", reliability.DEV_SECRETS["WEBHOOK_SECRET"])
    for p in config.WEBHOOK_SECRETS:
        monkeypatch.setitem(config.WEBHOOK_SECRETS, p, config.WEBHOOK_SECRET)
    codes = {p["code"] for p in reliability.config_problems()}
    assert {"shared_webhook_secret", "dev_webhook_secret"} <= codes
    for p in config.WEBHOOK_SECRETS:
        monkeypatch.setitem(config.WEBHOOK_SECRETS, p, f"own-{p}")
    codes = {p["code"] for p in reliability.config_problems()}
    assert not {"shared_webhook_secret", "dev_webhook_secret"} & codes
