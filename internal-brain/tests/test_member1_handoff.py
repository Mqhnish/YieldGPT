"""Tests for the Member 1 -> Member 3 handoff items:
decision records, release recheck, fail-closed, audit access policy, sync bookkeeping."""
import pytest

from app import audit, audit_policy, llm
from app.identity import USERS
from app.index import Index
from app.sources.registry import build_connectors
from app.sources.world import World
from app.sync import Syncer
from app.sync_state import InMemorySyncStateStore, SqliteSyncStateStore

from .conftest import cited

MIGRATION_Q = "What's the status of the database migration project and were there any blockers raised in Slack last week?"


# ---------------------------------------------------------------- 1. decision records
def test_every_decision_record_is_complete(ask):
    r = ask("jdoe", MIGRATION_Q)
    decisions = audit.search(query_id=r["query_id"], event="authz_decision")
    assert decisions
    for d in decisions:
        assert d["doc_uid"] and d["platform"] and d["decision"] in ("allowed", "denied", "unavailable")
        det = d["detail"]
        assert det["stage"] in ("prefilter", "live", "fetch", "release")
        assert det["reason_code"] and "checked_at" in det and "resource_version" in det
        if det["stage"] in ("live", "release"):
            assert det["platform_account"]            # which platform identity was evaluated
    stages = {d["detail"]["stage"] for d in decisions}
    # A connector may legally use an unrestricted coarse hint (contract R5),
    # so a query needn't contain a prefilter denial. Live/release are mandatory.
    assert {"live", "release"} <= stages


def test_denied_content_never_reaches_the_model(brain, monkeypatch):
    seen = []
    real = llm.complete
    monkeypatch.setattr(llm, "complete", lambda q, s, a: (seen.append(s), real(q, s, a))[1])
    brain.ask(USERS["jdoe"], MIGRATION_Q)
    sent = {s["uid"] for batch in seen for s in batch}
    text = " ".join(s["text"] for batch in seen for s in batch)
    assert "slack:mig-leads/2101" not in sent and "licence" not in text.lower()
    # and the audit log records exactly what was sent, with versions
    ctx = audit.search(event="context_assembled")[0]["detail"]["context"]
    assert {c["uid"] for c in ctx} == sent and all(c["version"] for c in ctx)


# ---------------------------------------------------------------- 2. release recheck
def test_revocation_during_generation_discards_and_rebuilds(brain, monkeypatch):
    real, calls = llm.complete, []

    def generate_then_revoke(q, sources, asker):
        calls.append([s["uid"] for s in sources])
        if len(calls) == 1:  # access removed while the model is "thinking"
            brain.world.slack_remove_member("db-migration", "jdoe", push=False)
        return real(q, sources, asker)

    monkeypatch.setattr(llm, "complete", generate_then_revoke)
    r = brain.ask(USERS["jdoe"], MIGRATION_Q)
    assert "slack:db-migration/2001" in calls[0] and "slack:db-migration/2001" not in calls[1]
    assert "slack:db-migration/2001" not in cited(r)
    assert "40s" not in r["answer"]                                  # slack-only fact gone
    story = audit.reconstruct(query_id=r["query_id"])[0]
    assert story["release"] == "released_after_rebuild"
    assert story["discarded"][0]["revoked"] == ["slack:db-migration/2001"]
    assert "40s" in story["discarded"][0]["answer"]                  # auditor can see what was thrown away


def test_repeated_revocation_withholds_answer(brain, monkeypatch):
    real, n = llm.complete, [0]

    def generate_then_revoke(q, sources, asker):
        n[0] += 1
        if n[0] == 1:
            brain.world.slack_remove_member("db-migration", "jdoe", push=False)
        else:
            brain.world.projects["MIG"]["roles"] = {"developers": set(), "viewers": set()}
        return real(q, sources, asker)

    monkeypatch.setattr(llm, "complete", generate_then_revoke)
    r = brain.ask(USERS["jdoe"], MIGRATION_Q)
    assert r["citations"] == [] and "couldn't find" in r["answer"]
    assert audit.reconstruct(query_id=r["query_id"])[0]["release"] == "withheld"


# ---------------------------------------------------------------- fail closed
def test_platform_outage_fails_closed_but_other_sources_still_answer(brain):
    brain.world.outages.add("slack")
    r = brain.ask(USERS["jdoe"], MIGRATION_Q)
    assert not any(u.startswith("slack:") for u in cited(r))
    assert any(u.startswith("jira:") for u in cited(r))
    unavailable = audit.search(query_id=r["query_id"], decision="unavailable")
    assert unavailable and all(u["platform"] == "slack" for u in unavailable)


# ---------------------------------------------------------------- 3. audit access policy
def test_compliance_gets_full_view(ask):
    ask("jdoe", MIGRATION_Q)
    ev = audit_policy.view_events(USERS["priya"], audit.search(event="query_received"))
    assert ev[0]["detail"]["question"] == MIGRATION_Q and ev[0]["actor"] == "jdoe"
    assert audit_policy.reconstruct(USERS["priya"], {"actor": "jdoe"})


def test_admin_sees_metadata_only(ask):
    ask("jdoe", MIGRATION_Q)
    ev = audit_policy.view_events(USERS["dana"], audit.search(limit=200))
    for e in ev:
        assert set(e) <= {"id", "ts", "event", "severity", "platform", "decision", "actor"}
        assert e["actor"] in ("system", "webhook") or e["actor"].startswith("user-")
    assert MIGRATION_Q not in str(ev) and "mig-leads" not in str(ev)
    with pytest.raises(PermissionError):
        audit_policy.reconstruct(USERS["dana"], {"actor": "jdoe"})


def test_employee_has_no_audit_access_and_attempt_is_logged():
    with pytest.raises(PermissionError):
        audit_policy.view_events(USERS["jdoe"], [])
    with pytest.raises(PermissionError):
        audit_policy.verify(USERS["jdoe"])
    assert audit.search(actor="jdoe", event="audit_access_denied")


def test_audit_reads_are_themselves_audited(ask):
    audit_policy.view_events(USERS["priya"], audit.search(limit=5), {"x": 1})
    audit_policy.verify(USERS["dana"])
    acc = audit.search(event="audit_accessed")
    assert {a["actor"] for a in acc} == {"priya", "dana"}
    assert {a["detail"]["scope"] for a in acc} == {"full", "meta"}


def test_pseudonyms_are_stable():
    assert audit_policy.pseudonym("jdoe") == audit_policy.pseudonym("jdoe") != audit_policy.pseudonym("ravi")


# ---------------------------------------------------------------- 5. sync bookkeeping
def _syncer(store=None):
    w = World()
    cs = build_connectors(w)
    s = Syncer(cs, Index(), store or InMemorySyncStateStore())
    return w, s


def test_full_load_records_state_and_crawl():
    w, s = _syncer()
    s.full_load()
    for p in ("confluence", "jira", "slack", "gdrive"):
        st = s.state(p)
        assert st.initial_load_complete and st.last_success and st.consecutive_failures == 0
    assert all(c.via in ("crawl", "poll") for c in s.store.recent(limit=500))


def test_change_during_crawl_is_not_lost():
    w, s = _syncer()
    conf = s.c["confluence"]
    real = conf.list_page

    def crawl_and_edit(token, page_size=50):
        out = real(token, page_size)
        if token is None:  # someone edits CONF-101 after we've already read it
            w.confluence_update("CONF-101", "Step 7: added mid-crawl.", push=False)
        return out

    conf.list_page = crawl_and_edit
    s.full_load(["confluence"], page_size=100)
    assert "mid-crawl" in s.index.get("confluence:CONF-101").doc.text


def test_outage_does_not_advance_cursor_or_delete_anything():
    w, s = _syncer()
    s.full_load()
    before = s.state("confluence").cursor
    w.outages.add("confluence")
    w.confluence_update("CONF-101", "Step 6: during outage.", push=False)
    s.poll(["confluence"])
    st = s.state("confluence")
    assert st.cursor == before and st.consecutive_failures == 1 and "SourceUnavailable" in st.last_error
    assert s.index.get("confluence:CONF-101") is not None                     # outage != deletion
    assert st.status(300)["health"] == "failing"
    w.outages.clear()
    s.poll(["confluence"])
    assert "during outage" in s.index.get("confluence:CONF-101").doc.text
    assert s.state("confluence").consecutive_failures == 0


def test_webhook_during_outage_is_recorded_failed_and_poll_recovers():
    w, s = _syncer()
    s.full_load()
    w.listeners.append(s.on_webhook)
    w.outages.add("jira")
    w.jira_update("MIG-1", status="Done")
    failed = s.store.recent("jira", "failed")
    assert failed and failed[0].via == "webhook"
    assert "[In Progress]" in s.index.get("jira:MIG-1").doc.text               # not deleted, not changed
    w.outages.clear()
    s.poll(["jira"])
    assert "[Done]" in s.index.get("jira:MIG-1").doc.text


def test_deletion_leaves_a_tombstone():
    w, s = _syncer()
    s.full_load()
    w.delete("confluence", "CONF-106", push=False)
    s.poll(["confluence"])
    assert s.index.get("confluence:CONF-106") is None
    t = s.store.tombstone("confluence", "CONF-106")
    assert t and t.kind == "delete" and t.via == "poll" and s.state("confluence").deletes == 1


def test_sqlite_store_survives_restart(tmp_path):
    path = tmp_path / "sync.db"
    w, s = _syncer(SqliteSyncStateStore(path))
    s.full_load()
    w.delete("jira", "MIG-9", push=False)
    s.poll(["jira"])
    reopened = SqliteSyncStateStore(path)
    assert reopened.get("jira").cursor == s.state("jira").cursor
    assert reopened.tombstone("jira", "MIG-9") is not None


# ---------------------------------------------------------------- review fixes
def test_forged_delete_webhook_cannot_remove_a_live_doc():
    w, s = _syncer()
    s.full_load()
    s.on_webhook("confluence", "CONF-101", "delete")         # platform says nothing was deleted
    assert s.index.get("confluence:CONF-101") is not None
    assert s.store.tombstone("confluence", "CONF-101") is None


def test_real_delete_webhook_is_confirmed_then_applied():
    w, s = _syncer()
    s.full_load()
    w.listeners.append(s.on_webhook)
    w.delete("jira", "MIG-9")
    assert s.index.get("jira:MIG-9") is None and s.store.tombstone("jira", "MIG-9").via == "webhook"


def test_failed_initial_crawl_is_retried_before_incremental_sync():
    w, s = _syncer()
    w.outages.add("slack")
    s.full_load()
    assert not s.state("slack").initial_load_complete
    assert not any(uid.startswith("slack:") for uid in s.index._docs)
    w.outages.clear()
    s.poll(["slack"])
    assert s.state("slack").initial_load_complete
    assert s.index.get("slack:db-migration/2001") is not None


def test_decision_records_are_schema_versioned(ask):
    r = ask("jdoe", MIGRATION_Q)
    for ev in ("authz_decision", "context_assembled", "answer_returned"):
        assert all(e["detail"]["schema"] == f"{ev}/1" for e in audit.search(query_id=r["query_id"], event=ev))


def test_demo_controls_are_off_outside_demo_mode(monkeypatch):
    from fastapi.testclient import TestClient

    from app import main
    monkeypatch.setattr(main, "DEMO_MODE", False)
    with TestClient(main.app) as c:
        t = c.post("/api/login", json={"username": "dana", "password": "demo"}).json()["token"]
        r = c.post("/api/sim", json={"action": "slack_remove_member", "target": "db-migration", "value": "jdoe"},
                   headers={"Authorization": "Bearer " + t})
        assert r.status_code == 404
