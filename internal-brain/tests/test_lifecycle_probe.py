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
    assert any(s.step == "error" and not s.ok for s in steps)
    assert any(s.step == "cleanup: probe object deleted" and s.ok for s in steps)
    assert not _probe_objects(w)


def test_report_redacts_token_email_site_and_account_ids(monkeypatch):
    from app import config
    from app.identity import USERS
    monkeypatch.setattr(config, "ATLASSIAN_API_TOKEN", "ATATT3xFfGF0secret-token-value")
    monkeypatch.setattr(config, "ATLASSIAN_EMAIL", "bot@example.org")
    monkeypatch.setattr(config, "ATLASSIAN_SITE", "https://yieldgpt-demo.atlassian.net")
    sys.path.insert(0, "scripts")
    mod = importlib.import_module("atlassian_lifecycle_probe")
    acct = dict(USERS["ravi"].accounts)["jira"]
    text = mod.redact(f"ATATT3xFfGF0secret-token-value bot@example.org https://yieldgpt-demo.atlassian.net/wiki {acct} ok")
    for leaked in ("secret-token", "bot@example.org", "yieldgpt-demo", acct):
        assert leaked not in text
    assert text.endswith("ok")
