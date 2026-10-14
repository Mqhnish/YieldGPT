"""The brief's scenarios, run through the real pipeline against whichever Atlassian site is
configured (fixture or live). Owner: Member 1. Read-only: asks questions, changes nothing.

Mirrors tests/test_scenarios.py. Demo ids are translated to the site's real ids with the
seeder's manifest (on the fixture site they are the same). Scenarios 2 and 4 need edits and
revokes on the site; scripts/atlassian_lifecycle_probe.py covers those live.
"""
from __future__ import annotations

from dataclasses import dataclass

from .. import audit
from ..grounding import NEUTRAL_NO_ANSWER
from ..identity import USERS

MIGRATION_Q = "What's the status of the database migration project and were there any blockers raised in Slack last week?"
RUNBOOK_Q = "What's the latest runbook for the payment-service incident?"
OUTAGE_Q = "What was the root cause of the payment outage last quarter, and what follow-up tickets were created?"


@dataclass
class Check:
    scenario: str
    check: str
    ok: bool
    detail: str = ""


class Ids:
    """Demo uid -> uid on this site."""

    def __init__(self, manifest: dict | None = None):
        m = manifest or {}
        self.pages, self.issues = m.get("pages", {}), m.get("issues", {})

    def __call__(self, demo_uid: str) -> str:
        platform, _, nid = demo_uid.partition(":")
        if platform == "confluence":
            return f"confluence:{self.pages.get(nid, nid)}"
        if platform == "jira":
            return f"jira:{self.issues.get(nid, nid)}"
        return demo_uid

    def native(self, demo_uid: str) -> str:
        return self(demo_uid).split(":", 1)[1]


def run(brain, ids: Ids) -> list[Check]:
    out: list[Check] = []

    def ask(user, q):
        return brain.ask(USERS[user], q)

    def cited(r):
        return {c["uid"] for c in r["citations"]}

    def add(scenario, check, ok, detail=""):
        out.append(Check(scenario, check, bool(ok), detail))

    # ---- S1 unified query
    r = ask("jdoe", MIGRATION_Q)
    c = cited(r)
    add("S1", "jdoe: migration answer cites the Jira epic and the Slack thread",
        {ids("jira:MIG-1"), "slack:T0COMPANYA/db-migration/2001"} <= c, f"{len(c)} citations")
    add("S1", "answer spans 2+ platforms, all citation links https",
        len({u.split(':')[0] for u in c}) >= 2 and all(x["url"].startswith("https://") for x in r["citations"]),
        ", ".join(sorted({u.split(':')[0] for u in c})))
    add("S1", "private channel jdoe is not in is omitted", "slack:T0COMPANYA/mig-leads/2101" not in c)
    r = ask("ravi", OUTAGE_Q)
    c = cited(r)
    add("S1", "ravi: outage answer stitches Jira root cause, Drive doc and follow-up tickets",
        {ids("jira:PAY-101"), "gdrive:DRV-1"} <= c and bool({ids("jira:PAY-102"), ids("jira:PAY-103")} & c),
        f"{len(c)} citations")

    # ---- S3 negative cases
    restricted = ask("kim", "Show me the security incident report from the Q3 breach")
    nonexistent = ask("kim", "Show me the unicorn migration to mars report")
    add("S3", "kim: restricted report answer identical to a nonexistent one",
        restricted["answer"] == nonexistent["answer"] == NEUTRAL_NO_ANSWER
        and restricted["citations"] == nonexistent["citations"] == [])
    r = ask("jdoe", "Show me all security vulnerabilities")
    hidden = {ids("jira:PAY-110"), ids("jira:SEC-4"), ids("confluence:CONF-103")}
    add("S3", "jdoe: no security-level issue, security project or security space page cited",
        not (hidden & cited(r)) and "tokenisation" not in r["answer"].lower())
    add("S3", "jdoe's denial on the security-level issue (demo PAY-110) is in the audit trail",
        bool(audit.search(actor="jdoe", doc_uid=ids("jira:PAY-110"), decision="denied")))
    add("S3", "asha (security group) does get the security-level issue",
        ids("jira:PAY-110") in cited(ask("asha", "Show me all security vulnerabilities")))
    r = ask("kim", "What's the status of MIG-1 migration epic in Jira?")
    add("S3", "kim (no Atlassian account) gets no Jira citations", not any(u.startswith("jira:") for u in cited(r)))
    conf = brain.connectors["confluence"]
    child = conf.check(USERS["jdoe"], ids.native("confluence:CONF-105"))
    add("S3", "child page of a restricted page is denied (inherited restriction)", not child.allowed, child.reason_code)

    # ---- S5 audit inquiry
    ask("jdoe", RUNBOOK_Q)
    ask("jdoe", "What's the payment gateway architecture?")
    f = audit.parse_question("Show me everything user 'jdoe' accessed related to the "
                             "'payment-gateway' Confluence space in the last 30 days")
    stories = audit.reconstruct(**f)
    add("S5", "compliance question parsed (user, space, platform)",
        f.get("actor") == "jdoe" and f.get("container") == "payment-gateway" and f.get("platform") == "confluence")
    add("S5", "each matching request has the question, per-document decisions and the answer",
        len(stories) >= 2 and all(s["question"] and s["answer"] and s["decisions"] for s in stories),
        f"{len(stories)} request(s)")
    add("S5", "matched documents are allowed Confluence pages in that space",
        stories and all(m["decision"] == "allowed" and m["doc_uid"].startswith("confluence:")
                        for s in stories for m in s["matched"]))
    ask("asha", "Show me the Q3 breach incident report")
    ask("kim", "Show me the Q3 breach incident report")
    who = {s["actor"] for s in audit.reconstruct(**audit.parse_question(f"who retrieved '{ids('confluence:CONF-103')}'"))}
    add("S5", "'who retrieved the breach report' names only asha", who == {"asha"}, ", ".join(sorted(who)))
    return out
