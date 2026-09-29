"""One test group per scenario in the Aspire challenge brief."""
from app import audit
from app.grounding import NEUTRAL_NO_ANSWER
from app.identity import USERS

from .conftest import cited

MIGRATION_Q = "What's the status of the database migration project and were there any blockers raised in Slack last week?"
RUNBOOK_Q = "What's the latest runbook for the payment-service incident?"
NEW_STEP = "Step 5: If the certificate cannot be renewed within 10 minutes, fail over payment-service to the secondary card network gateway."


# ---------------------------------------------------------------- Scenario 1
def test_s1_unified_query_across_platforms_with_citations(ask):
    r = ask("jdoe", MIGRATION_Q)
    c = cited(r)
    assert "jira:MIG-1" in c and "slack:db-migration/2001" in c
    assert len({uid.split(":")[0] for uid in c}) >= 2          # genuinely cross-platform
    assert all(ci["url"].startswith("https://") for ci in r["citations"])


def test_s1_private_channel_the_engineer_is_not_in_is_omitted(ask):
    r = ask("jdoe", MIGRATION_Q)
    assert "slack:mig-leads/2101" not in cited(r)
    assert "licence" not in r["answer"].lower()
    denied = audit.search(actor="jdoe", doc_uid="slack:mig-leads/2101", decision="denied")
    assert denied, "the denial must still be recorded in the audit trail"


def test_s1_linked_context_is_stitched_across_platforms(ask):
    r = ask("ravi", "What was the root cause of the payment outage last quarter, and what follow-up tickets were created?")
    c = cited(r)
    assert {"jira:PAY-101", "gdrive:DRV-1"} <= c
    assert {"jira:PAY-102", "jira:PAY-103"} & c


# ---------------------------------------------------------------- Scenario 2
def test_s2_update_via_webhook_is_indexed_immediately(brain):
    brain.world.confluence_update("CONF-101", NEW_STEP, push=True)
    assert "secondary card network gateway" in brain.index.get("confluence:CONF-101").doc.text


def test_s2_missed_webhook_is_caught_by_polling(brain):
    brain.world.confluence_update("CONF-101", NEW_STEP, push=False)
    assert "secondary" not in brain.index.get("confluence:CONF-101").doc.text
    brain.syncer.poll()
    assert "secondary" in brain.index.get("confluence:CONF-101").doc.text


def test_s2_stale_index_is_never_served_read_through(brain, ask):
    brain.world.confluence_update("CONF-101", NEW_STEP, push=False)  # webhook lost, no poll yet
    r = ask("ravi", RUNBOOK_Q)
    assert "secondary card network gateway" in r["answer"]
    assert audit.search(event="read_through_refresh", doc_uid="confluence:CONF-101")


# ---------------------------------------------------------------- Scenario 3
def test_s3_contractor_gets_neutral_answer_no_existence_leak(ask):
    restricted = ask("kim", "Show me the security incident report from the Q3 breach")
    nonexistent = ask("kim", "Show me the unicorn migration to mars report")
    assert restricted["answer"] == nonexistent["answer"] == NEUTRAL_NO_ANSWER
    assert restricted["citations"] == nonexistent["citations"] == []
    assert "credential" not in restricted["answer"].lower()


def test_s3_junior_engineer_cannot_see_security_vulns(ask):
    r = ask("jdoe", "Show me all security vulnerabilities")
    assert not any(u in cited(r) for u in ("jira:PAY-110", "jira:SEC-4", "confluence:CONF-103"))
    assert "tokenisation" not in r["answer"].lower()
    # issue-level security: jdoe CAN browse PAY, but PAY-110 has a security level
    assert audit.search(actor="jdoe", doc_uid="jira:PAY-110", decision="denied")


def test_s3_security_engineer_can(ask):
    assert "jira:PAY-110" in cited(ask("asha", "Show me all security vulnerabilities"))


def test_s3_contractor_cannot_query_internal_jira(ask):
    r = ask("kim", "What's the status of MIG-1 migration epic in Jira?")
    assert not any(u.startswith("jira:") for u in cited(r))


def test_s3_page_restrictions_are_inherited(brain):
    conf = brain.connectors["confluence"]
    assert conf.check(USERS["jdoe"], "CONF-105").allowed is False       # child of restricted CONF-104
    assert conf.check(USERS["dana"], "CONF-105").allowed is True


# ---------------------------------------------------------------- Scenario 4
def test_s4_slack_removal_takes_effect_even_without_webhook(brain, ask):
    assert "slack:db-migration/2001" in cited(ask("jdoe", MIGRATION_Q))
    brain.world.slack_remove_member("db-migration", "jdoe", push=False)   # index ACL now stale
    r = ask("jdoe", MIGRATION_Q)
    assert "slack:db-migration/2001" not in cited(r)
    d = audit.search(actor="jdoe", doc_uid="slack:db-migration/2001", decision="denied")
    assert d and d[0]["detail"]["stage"] == "live"


def test_s4_confluence_restriction_takes_effect_immediately(brain, ask):
    q = "Summarize the auth service design decision"
    assert "confluence:CONF-102" in cited(ask("jdoe", q))
    brain.world.confluence_restrict("CONF-102", {"user:asha"}, push=False)
    assert "confluence:CONF-102" not in cited(ask("jdoe", q))
    assert "confluence:CONF-102" in cited(ask("asha", q))


# ---------------------------------------------------------------- Scenario 5
def test_s5_compliance_can_reconstruct_user_activity(ask):
    ask("jdoe", RUNBOOK_Q)
    ask("jdoe", "What's the payment gateway architecture?")
    f = audit.parse_question("Show me everything user 'jdoe' accessed related to the "
                             "'payment-gateway' Confluence space in the last 30 days")
    assert f["actor"] == "jdoe" and f["container"] == "payment-gateway" and f["platform"] == "confluence"
    stories = audit.reconstruct(**f)
    assert len(stories) == 2
    for s in stories:
        assert s["question"] and s["answer"] and s["decisions"]
        assert all(m["decision"] == "allowed" for m in s["matched"])
        assert all(m["doc_uid"].startswith("confluence:") for m in s["matched"])


def test_s5_who_retrieved_a_sensitive_doc(ask):
    ask("asha", "Show me the Q3 breach incident report")
    ask("kim", "Show me the Q3 breach incident report")
    f = audit.parse_question("who retrieved 'confluence:CONF-103'")
    actors = {s["actor"] for s in audit.reconstruct(**f)}
    assert actors == {"asha"}
