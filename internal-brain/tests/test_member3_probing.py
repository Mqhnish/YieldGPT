"""Member 3: probing alert counts repeated attempts on one restricted doc, not raw denied rows."""
from app import audit
from app.config import PROBE_ALERT_THRESHOLD as T


def deny(actor, doc, query_id, stage="prefilter"):
    audit.log(actor, "authz_decision", query_id=query_id, doc_uid=doc, decision="denied", stage=stage)


def alerts(actor="jdoe"):
    return audit.search(actor=actor, event="probing_suspected")


def test_one_broad_search_denying_many_docs_does_not_alert():
    for i in range(200):
        deny("jdoe", f"confluence:doc-{i}", "q1")
    assert not alerts()
    assert len(audit.search(actor="jdoe", decision="denied")) == 200  # one row per decision kept (A02)


def test_several_broad_searches_over_different_docs_do_not_alert():
    for q in range(T + 3):
        for i in range(30):
            deny("jdoe", f"jira:SEC-{q * 30 + i}", f"q{q}")
    assert not alerts()


def test_every_phase_of_one_attempt_counts_once():
    for stage in ("prefilter", "live", "fetch", "release", "release", "release"):
        deny("jdoe", "jira:SEC-4", "q1", stage)
    assert not alerts()


def test_repeated_attempts_on_one_restricted_doc_alert_once():
    for q in range(T - 1):
        deny("jdoe", "jira:SEC-4", f"q{q}")
    assert not alerts()
    deny("jdoe", "jira:SEC-4", "q-last")
    [row] = alerts()
    assert row["severity"] == "alert"
    deny("jdoe", "jira:SEC-4", "q-more")
    assert len(alerts()) == 1  # one alert per 10-minute window


def test_separate_evidence_requests_count_as_separate_attempts():
    for r in range(T):
        audit.log("jdoe", "authz_decision", query_id="q1", doc_uid="jira:SEC-4", decision="denied",
                  stage="release", request_id=f"req-{r}")
    assert alerts()


def test_other_actors_attempts_do_not_count():
    for q in range(T - 1):
        deny("asha", "jira:SEC-4", f"a{q}")
    deny("jdoe", "jira:SEC-4", "j1")
    assert not alerts("jdoe") and not alerts("asha")
