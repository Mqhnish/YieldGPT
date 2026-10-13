"""The lifecycle probe (scripts/atlassian_lifecycle_probe.py) passes on a correct pipeline,
catches a broken one, always cleans up, and never leaks credentials into its report."""
import importlib
import os
import sys

import pytest

from app.brain import Brain
from app.seeding.lifecycle import LifecycleProbe, ProbeConfig
from app.sources.base import Decision
from app.sources.registry import build_connectors
from app.sources.world import World

pytestmark = pytest.mark.skipif(os.environ.get("IB_ATLASSIAN_MODE", "fixture") != "fixture",
                                reason="the probe drives the HTTP connectors (fixture mode)")


def _probe():
    w = World()
    b = Brain(world=w, connectors=build_connectors(w, atlassian_mode="fixture"))
    return w, LifecycleProbe(b, ProbeConfig(space_key="eng", timeout_s=1, poll_every_s=0), sleep=lambda s: None)


def _probe_objects(w):
    return ([p for p in w.pages.values() if "lifecycle probe" in p["title"]] +
            [i for i in w.issues.values() if "lifecycle probe" in i["summary"]])


def test_probe_passes_on_fixture_and_leaves_nothing_behind():
    w, probe = _probe()
    steps = probe.run()
    assert steps and all(s.ok for s in steps), [s for s in steps if not s.ok]
    assert {s.platform for s in steps} == {"confluence", "jira"}
    assert not _probe_objects(w)


def test_probe_catches_a_revocation_that_is_ignored(monkeypatch):
    w, probe = _probe()
    jira = probe.brain.connectors["jira"]
    real = jira._check_batch

    def leaky(user, account, keys):           # a bug: security levels ignored
        out = real(user, account, keys)
        return {k: (Decision.ALLOWED, "jira_browse_allowed", "bug", "") for k in out}
    monkeypatch.setattr(jira, "_check_batch", leaky)
    steps = probe.run(("jira",))
    failed = {s.step for s in steps if not s.ok}
    assert "revoke: viewer denied on next query (no reindex)" in failed
    assert not _probe_objects(w)


def test_probe_cleans_up_when_a_step_crashes(monkeypatch):
    w, probe = _probe()
    monkeypatch.setattr(probe, "_c_revoke", lambda pid: (_ for _ in ()).throw(RuntimeError("boom")))
    steps = probe.run(("confluence",))
    assert any(s.step == "error" and not s.ok and s.detail.startswith("during revoke") for s in steps)
    assert any(s.step == "cleanup: probe object deleted" and s.ok for s in steps)
    assert not _probe_objects(w)


def test_report_redacts_token_email_site_and_account_ids(monkeypatch):
    from app import config
    from app.identity import USERS
    monkeypatch.setattr(config, "ATLASSIAN_API_TOKEN", "ATATT3xFfGF0secret-token-value")
    monkeypatch.setattr(config, "ATLASSIAN_EMAIL", "bot@example.org")
    monkeypatch.setattr(config, "ATLASSIAN_SITE", "https://example-site.atlassian.net")
    sys.path.insert(0, "scripts")
    mod = importlib.import_module("atlassian_lifecycle_probe")
    acct = dict(USERS["ravi"].accounts)["jira"]
    text = mod.redact(f"ATATT3xFfGF0secret-token-value bot@example.org https://example-site.atlassian.net/wiki {acct} ok")
    for leaked in ("secret-token", "bot@example.org", "example-site", acct):
        assert leaked not in text
    assert text.endswith("ok")


def test_probe_reports_a_revocation_that_lags(monkeypatch):
    # Seen live: Atlassian's permission check can keep answering the old way for a moment.
    w, probe = _probe()
    jira = probe.brain.connectors["jira"]
    real = jira._check_batch
    stale = {"left": 0}
    real_revoke = probe._j_revoke

    def revoke(key):
        real_revoke(key)
        # Long enough to outlast one whole question. (With only 2 stale answers the pipeline's
        # release re-check already denies it, so the issue is never cited.)
        stale["left"] = 8

    def lagging(user, account, keys):
        out = real(user, account, keys)
        if stale["left"] > 0 and user.username == "ravi":
            stale["left"] -= 1
            return {k: (Decision.ALLOWED, "jira_browse_allowed", "stale", "") for k in out}
        return out
    monkeypatch.setattr(probe, "_j_revoke", revoke)
    monkeypatch.setattr(jira, "_check_batch", lagging)
    steps = {s.step: s for s in probe.run(("jira",))}
    assert not steps["revoke: viewer denied on next query (no reindex)"].ok      # caught, not hidden
    assert steps["revoke: denial holds within 5 s of the revoke"].ok              # and it settles
    assert not _probe_objects(w)


def test_short_stale_allow_is_stopped_by_the_release_recheck(monkeypatch):
    # Defense in depth: if Atlassian still says "allowed" for the before-read and after-read
    # checks right after a revoke, the release re-check denies it and nothing is cited.
    w, probe = _probe()
    jira = probe.brain.connectors["jira"]
    real, stale, real_revoke = jira._check_batch, {"left": 0}, probe._j_revoke

    def revoke(key):
        real_revoke(key)
        stale["left"] = 2

    def lagging(user, account, keys):
        out = real(user, account, keys)
        if stale["left"] > 0 and user.username == "ravi":
            stale["left"] -= 1
            return {k: (Decision.ALLOWED, "jira_browse_allowed", "stale", "") for k in out}
        return out
    monkeypatch.setattr(probe, "_j_revoke", revoke)
    monkeypatch.setattr(jira, "_check_batch", lagging)
    steps = {s.step: s for s in probe.run(("jira",))}
    assert steps["revoke: viewer denied on next query (no reindex)"].ok
    assert not _probe_objects(w)


def test_missing_jira_permission_stops_before_creating_anything():
    # Live: the bot lacked Delete Issues, so three runs each left a probe issue behind.
    w, probe = _probe()
    fake = probe.brain.connectors["jira"].api._http._transport.handler.__self__
    fake.bot_lacks = {"DELETE_ISSUES"}
    before = set(w.issues)
    steps = probe.run(("jira",))
    assert [(s.step, s.ok) for s in steps] == [("preflight: integration account has the Jira permissions it needs", False)]
    assert "DELETE_ISSUES" in steps[0].detail
    assert set(w.issues) == before and not any("POST /rest/api/3/issue" == c for c in fake.calls)
