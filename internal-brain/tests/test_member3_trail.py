"""Member 3: the compliance officer's complete audit trail (/api/audit/trail, /api/audit/export).

Complete means every row, every event type, reachable by paging, with sealed text opened;
compliance only; and every read of it (or attempt) is itself recorded.
"""
import json

import pytest
from fastapi.testclient import TestClient

from app import audit, server

QUESTION = "What's the status of the database migration project and were there any blockers raised in Slack last week?"


@pytest.fixture
def client():
    with TestClient(server.app) as c:
        yield c


def auth(c, user):
    return {"Authorization": "Bearer " + c.post("/api/login", json={"username": user, "password": "demo"}).json()["token"]}


def activity(c):
    """A mix of event types: questions, a denial-heavy question, a failed login, a probing alert."""
    jdoe = auth(c, "jdoe")
    assert c.post("/api/ask", json={"question": QUESTION}, headers=jdoe).status_code == 200
    c.post("/api/ask", json={"question": "Show me the Q3 breach incident report"}, headers=auth(c, "kim"))
    c.post("/api/login", json={"username": "jdoe", "password": "wrong"})
    audit.log("jdoe", "probing_suspected", severity="alert", attempts_on_one_doc_last_10min=5)


def page_all(c, headers, **params):
    rows, before = [], None
    while True:
        q = {**params, "limit": 7, **({"before_id": before} if before else {})}
        r = c.get("/api/audit/trail", params=q, headers=headers)
        assert r.status_code == 200
        body = r.json()
        rows += body["events"]
        before = body["next_before_id"]
        if before is None:
            return rows


def test_paging_reaches_every_row_exactly_once_with_every_event_type(client):
    activity(client)
    priya = auth(client, "priya")
    head = audit.head()[0]
    rows = page_all(client, priya)
    ids = [r["id"] for r in rows if r["id"] <= head]
    assert ids == list(range(head, 0, -1))                    # newest first, no gaps, no repeats
    kinds = {r["event"] for r in rows}
    assert {"query_received", "authz_decision", "answer_returned", "response_delivered", "login",
            "login_failed", "probing_suspected"} <= kinds


def test_sealed_question_and_answer_text_is_opened_for_compliance(client):
    activity(client)
    rows = client.get("/api/audit/trail", params={"event": "query_received", "actor": "jdoe"},
                      headers=auth(client, "priya")).json()["events"]
    assert any(r["detail"].get("question") == QUESTION for r in rows)
    answers = client.get("/api/audit/trail", params={"event": "answer_returned", "actor": "jdoe"},
                         headers=auth(client, "priya")).json()["events"]
    assert answers and answers[0]["detail"].get("answer")


def test_filters_narrow_the_trail(client):
    activity(client)
    priya = auth(client, "priya")
    denied = page_all(client, priya, decision="denied")
    assert denied and all(r["decision"] == "denied" for r in denied)
    alerts = page_all(client, priya, severity="alert")
    assert {r["event"] for r in alerts} >= {"probing_suspected"}


def test_every_trail_read_and_export_is_itself_recorded(client):
    priya = auth(client, "priya")
    client.get("/api/audit/trail", params={"actor": "jdoe"}, headers=priya)
    client.get("/api/audit/export", headers=priya)
    reads = audit.search(actor="priya", event="audit_accessed")
    assert {r["detail"].get("action") for r in reads} >= {"trail", "export"}
    trail_read = next(r for r in reads if r["detail"].get("action") == "trail")
    assert trail_read["detail"]["filters"] == {"actor": "jdoe"}


@pytest.mark.parametrize("user", ["dana", "jdoe", "kim"])
def test_only_compliance_gets_the_full_trail_and_attempts_are_recorded(client, user):
    headers = auth(client, user)
    assert client.get("/api/audit/trail", headers=headers).status_code == 403
    assert client.get("/api/audit/export", headers=headers).status_code == 403
    denied = audit.search(actor=user, event="audit_access_denied")
    assert {r["detail"].get("action") for r in denied} >= {"trail", "export"}


def test_export_is_every_row_with_hash_links_that_chain(client):
    activity(client)
    priya = auth(client, "priya")
    head = audit.head()[0]                                     # the export covers everything up to its own record
    r = client.get("/api/audit/export", headers=priya)
    assert r.status_code == 200 and "attachment" in r.headers["content-disposition"]
    rows = [json.loads(line) for line in r.text.splitlines()]
    assert [x["id"] for x in rows] == list(range(head, 0, -1))
    by_id = {x["id"]: x for x in rows}
    assert all(by_id[i]["prev_hash"] == by_id[i - 1]["hash"] for i in range(2, head + 1))
    assert any(x["detail"].get("question") == QUESTION for x in rows)
