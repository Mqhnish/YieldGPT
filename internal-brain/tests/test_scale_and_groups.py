"""Scale-mode generator + group membership changes."""
import dataclasses

from app import identity
from app.brain import Brain
from app.identity import USERS
from app.seeding.scale import generate, summary
from app.sources.registry import build_connectors

from .conftest import cited

SMALL = dict(spaces=8, pages=400, projects=5, issues=200, workspaces=2, channels=20, threads=200, folders=10, files=80)


def test_generator_is_reproducible_and_varied():
    a, b = generate(3, **SMALL), generate(3, **SMALL)
    assert summary(a) == summary(b)
    assert [p["body"] for p in a.pages.values()] == [p["body"] for p in b.pages.values()]
    assert summary(generate(4, **SMALL)) == summary(a) and generate(4, **SMALL).pages["P-00010"]["body"] != a.pages["P-00010"]["body"]
    bodies = [p["body"] for k, p in a.pages.items() if k.startswith("P-")]
    assert len(set(bodies)) == len(bodies)                                    # no copy-paste haystack


def test_generator_has_every_permission_shape():
    w = generate(3, **SMALL)
    assert any(s["view"] == {"group:all-employees"} for s in w.spaces.values())
    assert any(p["restrict"] and next(iter(p["restrict"])).startswith("user:") for p in w.pages.values())
    assert any(p["parent"] for k, p in w.pages.items() if k.startswith("P-"))
    assert any(i["level"] for i in w.issues.values())
    assert any(c["private"] for c in w.channels.values()) and any(not c["private"] for c in w.channels.values())
    assert any("anyone" in f["shares"] for f in w.files.values())


def test_demo_needles_still_found_in_haystack():
    b = Brain(world=generate(3, **SMALL))
    r = b.ask(USERS["ravi"], "What was the root cause of the payment outage last quarter, and what follow-up tickets were created?")
    assert "jira:PAY-101" in cited(r) and "TLS certificate" in r["answer"]
    assert b.ask(USERS["kim"], "Show me the security incident report from the Q3 breach")["citations"] == []


def test_haystack_permissions_hold_through_http_connectors():
    w = generate(3, **SMALL)
    sim, http = build_connectors(w, "sim"), build_connectors(w, "fixture")
    for platform in ("confluence", "jira"):
        ids = sorted(sim[platform]._ids())[::7]
        for u in USERS.values():
            got = http[platform].check_many(u, ids)
            assert all(got[i].decision is sim[platform].check(u, i).decision for i in ids), (platform, u.username)


def test_losing_a_group_takes_effect_on_next_question(monkeypatch):
    """Ravi is moved out of payments + eng (an IdP / Atlassian group change). No sync, no
    event: his very next question must not use payment-gateway content."""
    b = Brain()
    q = "What's the latest runbook for the payment-service incident?"
    assert "confluence:CONF-101" in cited(b.ask(USERS["ravi"], q))
    moved = dataclasses.replace(USERS["ravi"], groups=frozenset({"all-employees"}))
    monkeypatch.setitem(identity.USERS, "ravi", moved)
    r = b.ask(moved, q)
    assert "confluence:CONF-101" not in cited(r) and "jira:PAY-101" not in cited(r)


def test_gaining_a_group_takes_effect_on_next_question(monkeypatch):
    b = Brain()
    q = "Show me all security vulnerabilities"
    assert "jira:SEC-4" not in cited(b.ask(USERS["jdoe"], q))
    promoted = dataclasses.replace(USERS["jdoe"], groups=USERS["jdoe"].groups | {"security"})
    monkeypatch.setitem(identity.USERS, "jdoe", promoted)
    assert "jira:SEC-4" in cited(b.ask(promoted, q))
