"""Independent Member 2 review regressions for evidence and release boundaries."""
import time

import pytest

from app import audit, grounding, llm
from app.evidence import EvidenceUnavailable
from app.identity import USERS


def test_valid_reference_cannot_launder_an_unrelated_citation():
    sources = [
        {"ref": "S1", "text": "The cutover is not approved."},
        {"ref": "S2", "text": "The cafeteria opens at noon."},
    ]
    answer, stats = grounding.enforce("The cutover is not approved. [S1][S2]", sources)
    assert answer == grounding.NEUTRAL_NO_ANSWER
    assert stats["dropped"] == 1


def test_multiple_references_are_valid_when_each_supports_the_whole_claim():
    sources = [{"ref": ref, "text": "The cutover is not approved."} for ref in ("S1", "S2")]
    answer, stats = grounding.enforce("The cutover is not approved. [S1][S2]", sources)
    assert answer == "The cutover is not approved. [S1][S2]"
    assert stats["dropped"] == 0


def test_supported_prefix_does_not_validate_an_unsupported_clause():
    sources = [{"ref": "S1", "text": "The cutover is not approved."}]
    answer, stats = grounding.enforce("The cutover is not approved, but the CEO approved the budget. [S1]", sources)
    assert answer == grounding.NEUTRAL_NO_ANSWER
    assert stats["dropped"] == 1


@pytest.mark.parametrize("mutation", ["revoke", "edit"])
def test_change_during_release_fetch_discards_the_answer(brain, monkeypatch, mutation):
    generated = False
    changed = False
    complete, read = llm.complete, brain._fetch

    def generate(question, sources, asker):
        nonlocal generated
        result = complete(question, sources, asker)
        generated = True
        return result

    def fetch_then_change(conn, user, native_id):
        nonlocal changed
        snapshot = read(conn, user, native_id)
        if generated and not changed and conn.platform == "confluence" and native_id == "CONF-101":
            changed = True
            if mutation == "revoke":
                brain.world.confluence_restrict("CONF-101", {"user:asha"}, push=False)
            else:
                brain.world.confluence_update("CONF-101", "Step 5: A newer approved procedure supersedes this copy.", push=False)
        return snapshot

    monkeypatch.setattr(llm, "complete", generate)
    monkeypatch.setattr(brain, "_fetch", fetch_then_change)
    result = brain.ask(USERS["ravi"], "What's the latest runbook for the payment-service incident?")
    assert changed
    assert "confluence:CONF-101" not in {c["uid"] for c in result["citations"]}
    discarded = audit.search(query_id=result["query_id"], event="answer_discarded")
    assert discarded and "confluence:CONF-101" in discarded[0]["detail"]["revoked"]
    assert "Step 1:" not in result["answer"]


def test_evidence_preview_rejects_edit_during_final_authorization(brain, monkeypatch):
    user = USERS["ravi"]
    result = brain.ask(user, "Show me CONF-101.")
    ref = next(c["ref"] for c in result["citations"] if c["uid"] == "confluence:CONF-101")
    connector = brain.connectors["confluence"]
    check, calls = connector.check, 0

    def check_after_edit(asker, native_id):
        nonlocal calls
        calls += 1
        if calls == 2:
            brain.world.confluence_update("CONF-101", "Step 5: This document changed during the preview read.", push=False)
        return check(asker, native_id)

    monkeypatch.setattr(connector, "check", check_after_edit)
    with pytest.raises(EvidenceUnavailable):
        brain.evidence(user, result["query_id"], ref)


def test_recent_unrelated_reply_does_not_make_old_blocker_recent(brain):
    now = time.time()
    native_id = "db-migration/9001"
    old_message = "Archive checksum blocker: backup chunks are missing and the restore cannot proceed."
    brain.world.threads[native_id] = {
        "ts": now - 86400,
        "msgs": [("ravi", now - 20 * 86400, old_message),
                 ("jdoe", now - 86400, "Thanks; the lunch order is confirmed.")],
    }
    brain.syncer.on_webhook("slack", native_id)
    result = brain.ask(USERS["jdoe"], "Which archive checksum blocker messages appeared in Slack last week?")
    assert old_message not in result["answer"]
    assert "backup chunks are missing" not in result["answer"]
    for citation in result["citations"]:
        preview = brain.evidence(USERS["jdoe"], result["query_id"], citation["ref"])
        assert all(old_message not in passage["text"] for passage in preview["passages"])
