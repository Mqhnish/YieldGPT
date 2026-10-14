"""Model-written summaries: only sentences supported by the sources they cite survive."""
from app import synthesis
from app.identity import USERS

SRC = [{"ref": "S1", "platform": "jira", "title": "MIG-1", "passages": [
            {"text": "MIG-1 [In Progress] Epic: Postgres 12 to 16 migration."},
            {"text": "Status: 70% of tables migrated."}, {"text": "Cutover to Postgres 16 is planned for 20 Oct."}]},
       {"ref": "S2", "platform": "slack", "title": "#db-migration", "passages": [
            {"text": "@ravi: Blocker: replication lag on the orders table hit 40s during dual-write, so the migration cutover is on hold until MIG-2 is fixed."}]}]


def test_supported_sentences_are_kept():
    text = ("The Postgres 16 migration is in progress with 70% of tables migrated [S1]. "
            "Cutover is on hold until MIG-2 is fixed because replication lag on the orders table hit 40s [S2].")
    kept, dropped = synthesis.check(text, SRC)
    assert kept == text and dropped == []


def test_wrong_number_unknown_source_missing_citation_and_invented_claim_are_dropped():
    text = ("The migration is 90% done [S1]. "                       # number not in S1
            "Cutover is planned for 20 Oct [S3]. "                   # unknown source
            "The team is confident it will finish early. "           # no citation
            "The CEO approved a budget increase for the database vendor [S1]. "   # words not in the source
            "Cutover to Postgres 16 is planned for 20 Oct [S1].")    # fine
    kept, dropped = synthesis.check(text, SRC)
    assert kept == "Cutover to Postgres 16 is planned for 20 Oct [S1]." and len(dropped) == 4


def test_ticket_id_must_be_in_the_cited_source():
    kept, _ = synthesis.check("The cutover is blocked by MIG-7 [S2].", SRC)
    assert kept == ""


def test_disabled_without_a_configured_model():
    assert synthesis.enabled() is False
    assert synthesis.summarize("q", SRC)[0] is None


def test_brain_puts_a_checked_summary_on_top_and_keeps_the_extracts(brain, monkeypatch):
    monkeypatch.setattr(synthesis, "summarize", lambda q, sources: ("Short checked answer [S1].", {"mode": "summary_checked", "dropped": 1}))
    r = brain.ask(USERS["ravi"], "What was the root cause of the payment outage last quarter, and what follow-up tickets were created?")
    first, second, *rest = r["answer"].split("\n\n")
    assert first == "Short checked answer [S1]." and second.startswith("Evidence from ") and rest
    assert r["quality"]["mode"] == "model_summary"


def test_brain_without_summary_is_unchanged(brain):
    r = brain.ask(USERS["ravi"], "What was the root cause of the payment outage last quarter, and what follow-up tickets were created?")
    assert r["answer"].startswith("Here's what I found in ") and r["quality"]["mode"] == "extractive"
