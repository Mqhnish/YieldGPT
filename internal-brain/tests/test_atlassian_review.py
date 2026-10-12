"""Regression tests for the connector review (29 Sep). Each test reproduces a bug that
existed before the fix."""
import json
import os
import time

import httpx
import pytest

from app import config
from app.identity import USERS
from app.index import Index
from app.sources.atlassian_client import AtlassianClient
from app.sources.base import Decision
from app.sources.confluence_cloud import ConfluenceCloudConnector
from app.sources.fake_atlassian import FakeAtlassian
from app.sources.jira_cloud import JiraCloudConnector
from app.sources.registry import build_connectors
from app.sources.world import World
from app.sync import Syncer

SITE = "https://companya.atlassian.net"


def _client(handler, **kw):
    return AtlassianClient(SITE, "bot@companya.example", "TOKEN", transport=httpx.MockTransport(handler), **kw)


# ---------------------------------------------------------------- security
@pytest.mark.parametrize("next_link", ["https://evil.example/steal", "//evil.example/steal", "http://companya.atlassian.net/x"])
def test_credentials_never_sent_off_site(next_link):
    hosts = []

    def h(req):
        hosts.append(req.url.host)
        return httpx.Response(200, json={"results": [{"id": "1"}], "_links": {"next": next_link}})
    c = ConfluenceCloudConnector(_client(h))
    _, token = c.list_page(None, 1)
    with pytest.raises(Exception):
        c.list_page(token, 1)
    assert hosts == ["companya.atlassian.net"]


def test_same_site_absolute_link_is_allowed():
    calls = []

    def h(req):
        calls.append(str(req.url))
        return httpx.Response(200, json={"results": [], "_links": {}})
    ConfluenceCloudConnector(_client(h)).list_page(f"{SITE}/wiki/api/v2/pages?cursor=abc", 1)
    assert calls == [f"{SITE}/wiki/api/v2/pages?cursor=abc"]


# ---------------------------------------------------------------- pagination
def test_jira_search_without_isLast_is_not_truncated():
    pages = {None: (["A-1"], "t2"), "t2": (["A-2"], "t3"), "t3": (["A-3"], None)}

    def h(req):
        if req.url.path.endswith("project/search"):
            return httpx.Response(200, json={"values": [{"key": "A"}], "total": 1})   # no isLast either
        keys, nxt = pages[json.loads(req.content).get("nextPageToken")]
        body = {"issues": [{"id": str(10 + n), "key": k, "fields": {"updated": "2026-09-29T10:00:00.000+0000"}}
                           for n, k in enumerate(keys)]}
        if nxt:
            body["nextPageToken"] = nxt
        return httpx.Response(200, json=body)
    assert JiraCloudConnector(_client(h))._all_ids() == {"A-1", "A-2", "A-3"}


def test_confluence_search_follows_next_links():
    w = World()
    for i in range(130):  # > one page of 100
        w.pages[f"P-{i}"] = dict(space="eng", parent=None, restrict=None, updated=time.time(), title=f"p{i}",
                                 body="x", links=[])
    c = build_connectors(w, "fixture")["confluence"]
    assert len(c._updated_since(time.time() - 60)) == 130


# ---------------------------------------------------------------- deletions
def test_deletions_after_restart_are_not_hidden():
    w = World()
    c1 = build_connectors(w, "fixture")["confluence"]
    cur = c1.start_cursor()
    w.delete("confluence", "CONF-106", push=False)
    saved = c1.changes_since(cur).next_cursor
    c2 = build_connectors(w, "fixture")["confluence"]      # restart: new process, persisted cursor
    c2.changes_since(saved)                                # first pass re-baselines
    w.delete("confluence", "CONF-105", push=False)
    assert [(ch.native_id, ch.kind) for ch in c2.changes_since(saved).changes] == [("CONF-105", "delete")]


def test_mass_deletion_is_held_back_but_edits_still_flow(monkeypatch):
    w = World()
    cs = build_connectors(w, "fixture")
    s = Syncer(cs, Index())
    s.full_load(["jira"])
    for k in ["MIG-1", "MIG-7", "MIG-9", "PAY-101", "PAY-102", "PAY-103"]:   # 6 of 8 vanish at once
        w.issues.pop(k)
    w.jira_update("SEC-4", comment="still flowing", push=False)
    s.poll(["jira"])
    st = s.state("jira")
    assert s.index.get("jira:MIG-1") is not None                       # nothing deleted
    assert "still flowing" in s.index.get("jira:SEC-4").doc.text      # edits not blocked
    assert st.status(300)["health"] == "degraded" and "held back" in st.last_error
    monkeypatch.setattr(config, "ALLOW_MASS_DELETE", True)             # human confirms it's real
    s.poll(["jira"])
    assert s.index.get("jira:MIG-1") is None and s.state("jira").status(300)["health"] == "ok"


# ---------------------------------------------------------------- content
def test_restricted_jira_comments_are_never_indexed():
    def h(req):
        if req.url.path.endswith("/remotelink"):
            return httpx.Response(200, json=[])
        adf = lambda t: {"type": "doc", "content": [{"type": "paragraph", "content": [{"type": "text", "text": t}]}]}
        return httpx.Response(200, json={"id": "1", "key": "PAY-1", "fields": {
            "summary": "s", "status": {"name": "Open"}, "project": {"key": "PAY"}, "updated": "2026-09-29T10:00:00.000+0000",
            "description": adf("desc"), "issuelinks": [],
            "comment": {"comments": [
                {"body": adf("public note"), "author": {"displayName": "Ravi"}},
                {"body": adf("SECRET: attacker IP 10.1.2.3"), "visibility": {"type": "role", "value": "Security"}},
            ]}}})
    c = JiraCloudConnector(_client(h))
    d = c.fetch("PAY-1")
    assert "public note" in d.text and "SECRET" not in d.text
    assert c.restricted_comments_skipped["PAY-1"] == 1


# ---------------------------------------------------------------- performance
def test_jira_checks_many_issues_in_one_call():
    w = World()
    fake = FakeAtlassian(w)
    c = JiraCloudConnector(AtlassianClient(SITE, transport=fake.transport()))
    c._all_ids()                                                        # sync populates key -> id
    n0 = len(fake.calls)
    res = c.check_many(USERS["jdoe"], ["MIG-1", "PAY-101", "PAY-110", "SEC-4", "NOPE-1"])
    perm_calls = [x for x in fake.calls[n0:] if "permissions/check" in x]
    assert len(perm_calls) == 1
    assert {k: r.decision for k, r in res.items()} == {
        "MIG-1": Decision.ALLOWED, "PAY-101": Decision.ALLOWED, "PAY-110": Decision.DENIED,
        "SEC-4": Decision.DENIED, "NOPE-1": Decision.DENIED}
    assert res["NOPE-1"].reason_code == "not_found"


def test_slow_checks_time_out_together_not_one_after_another(monkeypatch):
    monkeypatch.setattr(config, "CHECK_TIMEOUT_S", 0.3)
    c = build_connectors(World(), "sim")["confluence"]
    monkeypatch.setattr(c, "_check", lambda *a: time.sleep(2))
    t0 = time.time()
    res = c.check_many(USERS["jdoe"], [f"CONF-10{i}" for i in range(1, 7)])
    assert time.time() - t0 < 1.0                                        # one shared deadline, not 6 x 0.3s
    assert all(r.decision is Decision.UNAVAILABLE and r.reason_code == "timeout" for r in res.values())


@pytest.mark.skipif(os.environ.get("IB_ATLASSIAN_MODE", "fixture") != "fixture", reason="needs the default fixture mode")
def test_one_question_uses_one_jira_permission_call_per_phase(brain, monkeypatch):
    # The pipeline checks before read and after read, for retrieval, each link hop and release.
    # Each of those phases must cost ONE bulk Jira call, however many issues it covers.
    fake = brain.connectors["jira"].api._http._transport.handler.__self__
    phases, issues = [], []
    real = brain._check_batch
    def spy(user, items):
        jira = [nid for platform, nid in items if platform == "jira"]
        if jira:
            phases.append(1); issues.extend(jira)
        return real(user, items)
    monkeypatch.setattr(brain, "_check_batch", spy)
    n0 = len(fake.calls)
    brain.ask(USERS["ravi"], "What was the root cause of the payment outage last quarter, and what follow-up tickets were created?")
    perm = [x for x in fake.calls[n0:] if "/rest/api/3/permissions/check" in x]
    assert len(issues) > len(phases) >= 2                                # several issues per phase
    assert len(perm) == len(phases)                                      # one bulk call per phase
