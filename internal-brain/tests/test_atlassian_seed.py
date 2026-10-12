"""End-to-end: seed an EMPTY Atlassian site with the demo company, do the manual admin
steps, then check the real connectors see exactly what the expectations say."""
import pytest

from app.identity import USERS
from app.seeding.atlassian_seed import AtlassianSeeder, Manifest, space_key_for
from app.sources.atlassian_client import AtlassianClient
from app.sources.fake_atlassian import FakeAtlassian
from app.sources.registry import build_connectors
from app.sources.world import World

SITE = "https://companya.atlassian.net"


def empty_atlassian_world() -> World:
    """A fresh site: Slack/Drive demo data kept, Confluence/Jira empty."""
    w = World()
    w.spaces, w.pages, w.projects, w.issues, w.security_levels = {}, {}, {}, {}, {}
    return w


def do_manual_steps(target: World, demo: World):
    """What the admin does by hand: Jira permission schemes + issue security scheme.
    (Confluence space READ grants were already added by the seeder.)"""
    for key, proj in demo.projects.items():
        target.projects[key]["roles"] = {r: set(m) for r, m in proj["roles"].items()}
        target.projects[key]["browse"] = set(proj["browse"])
    target.security_levels.update({k: set(v) for k, v in demo.security_levels.items()})


@pytest.fixture
def seeded():
    target = empty_atlassian_world()
    fake = FakeAtlassian(target)
    seeder = AtlassianSeeder(AtlassianClient(SITE, transport=fake.transport()))
    seeder.run()
    do_manual_steps(target, seeder.demo)
    seeder.run(apply_security=True)
    return target, seeder, fake


def test_everything_is_created_with_real_ids(seeded):
    target, s, _ = seeded
    assert len(target.pages) == len(s.demo.pages) and len(target.issues) == len(s.demo.issues)
    assert set(s.m.spaces.values()) == {"ENG", "PAYMENTGATEWAY", "SECURITY"}
    assert all(pid.isdigit() for pid in s.m.pages.values())                      # server-assigned
    assert s.m.issues["MIG-7"] == "MIG-2" and s.m.issues["PAY-110"] == "PAY-4"   # sequential keys


def test_text_and_links_are_rewritten_to_real_ids(seeded):
    target, s, _ = seeded
    mig1 = target.issues[s.m.issues["MIG-1"]]
    assert "Blocked by MIG-2" in mig1["desc"] and "MIG-7" not in mig1["desc"]
    runbook = target.pages[s.m.pages["CONF-101"]]
    assert f"jira:{s.m.issues['PAY-101']}" in runbook["links"]
    pay = target.issues[s.m.issues["PAY-101"]]
    assert f"confluence:{s.m.pages['CONF-101']}" in pay["links"]          # remote link to the real page
    assert "slack:T0COMPANYA/payments-oncall/3001" in pay["links"]                   # cross-platform link kept


def test_rerun_is_idempotent(seeded):
    target, s, fake = seeded
    pages, issues = len(target.pages), len(target.issues)
    again = AtlassianSeeder(AtlassianClient(SITE, transport=fake.transport()), manifest=Manifest.from_json(s.m.to_json()))
    again.run(apply_security=True)
    assert (len(target.pages), len(target.issues)) == (pages, issues)
    assert again.m.pages == s.m.pages and again.m.issues == s.m.issues


def test_restrictions_and_security_levels_land(seeded):
    target, s, _ = seeded
    assert "user:dana" in target.pages[s.m.pages["CONF-104"]]["restrict"]
    assert target.pages[s.m.pages["CONF-105"]]["parent"] == s.m.pages["CONF-104"]   # inheritance preserved
    assert target.issues[s.m.issues["PAY-110"]]["level"] == "security-only"


def test_real_connectors_match_every_expectation(seeded):
    target, s, _ = seeded
    cs = build_connectors(target, "fixture")
    exps = s.expectations()
    assert len(exps) == len(USERS) * (len(s.demo.pages) + len(s.demo.issues))
    wrong = [(e["user"], e["demo_id"], e["expect"], cs[e["platform"]].check(USERS[e["user"]], e["id"]).decision.value)
             for e in exps]
    wrong = [w for w in wrong if w[2] != w[3]]
    assert wrong == []
    # the important negative cases are really in there
    assert {"user": "jdoe", "platform": "jira", "id": s.m.issues["PAY-110"], "demo_id": "PAY-110", "expect": "denied"} in exps
    assert {"user": "kim", "platform": "confluence", "id": s.m.pages["CONF-103"], "demo_id": "CONF-103", "expect": "denied"} in exps


def test_full_question_against_seeded_site(seeded, monkeypatch):
    target, s, _ = seeded
    from app.brain import Brain
    b = Brain(world=target)
    r = b.ask(USERS["ravi"], "What was the root cause of the payment outage last quarter, and what follow-up tickets were created?")
    cited = {c["uid"] for c in r["citations"]}
    assert f"jira:{s.m.issues['PAY-101']}" in cited and "gdrive:DRV-1" in cited
    assert "TLS certificate" in r["answer"]


def test_manual_checklist_names_the_real_objects(seeded):
    _, s, _ = seeded
    steps = "\n".join(s.manual_checklist())
    assert "PAYMENTGATEWAY" in steps and "security-only" in steps and s.m.issues["PAY-110"] in steps
    assert space_key_for("payment-gateway") == "PAYMENTGATEWAY"


def test_briefs_audit_query_works_on_real_space_keys(seeded):
    from app import audit
    from app.brain import Brain
    target, s, _ = seeded
    Brain(world=target).ask(USERS["ravi"], "What's the latest runbook for the payment-service incident?")
    f = audit.parse_question("Show me everything user 'ravi' accessed related to the "
                             "'payment-gateway' Confluence space in the last 30 days")
    stories = audit.reconstruct(**f)
    assert stories and all(m["doc_uid"].startswith("confluence:") for st in stories for m in st["matched"])
    assert f"confluence:{s.m.pages['CONF-101']}" in {m["doc_uid"] for st in stories for m in st["matched"]}


def test_restrictions_cover_view_and_edit_and_come_before_the_body():
    # Live site: a view-only restriction stopped the listed bot editing the page, so the
    # re-run's body update got 404. Restrict view AND edit, and do it before the body.
    target = empty_atlassian_world()
    fake = FakeAtlassian(target)
    client = AtlassianClient(SITE, transport=fake.transport())
    seen = []
    real = client.request
    def spy(method, path, **kw):
        if method == "PUT":
            seen.append((path, [r["operation"] for r in kw["json"]] if path.endswith("/restriction") else "body"))
        return real(method, path, **kw)
    client.request = spy
    AtlassianSeeder(client).run()
    restricted = [p for p, ops in seen if ops != "body"]
    assert restricted and all(ops == ["read", "update"] for p, ops in seen if ops != "body")
    for path in restricted:
        pid = path.split("/")[-2]
        order = [i for i, (p, ops) in enumerate(seen) if pid in p and p.split("/")[-1] in (pid, "restriction")]
        kinds = [seen[i][1] for i in order]
        assert kinds.index(["read", "update"]) < kinds.index("body")
