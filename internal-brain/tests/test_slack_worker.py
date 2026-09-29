"""Serialized live Slack scheduling, tested with clocks and events, never sleep."""
import threading

import pytest

from app.slack_worker import SlackMaintenance
from app.sources.base import SourceUnavailable


class Clock:
    def __init__(self): self.now = 0.0
    def __call__(self): return self.now


class Connector:
    def __init__(self, calls): self.calls, self.failure = calls, False
    def reconcile(self):
        self.calls.append("reconcile")
        if self.failure: raise SourceUnavailable("xoxp-private-do-not-log")
        return 7


class Syncer:
    def __init__(self, calls): self.calls, self.failure = calls, False
    def poll(self, platforms=None):
        self.calls.append(("poll", platforms))
        if self.failure: raise RuntimeError("xoxp-private-do-not-log")
        return {"slack": 2}
    def full_load(self, platforms=None):
        self.calls.append(("full", platforms))
        if self.failure: raise RuntimeError("xoxp-private-do-not-log")
        return 10


def worker(poll=10, reconcile=30):
    calls, logs, clock = [], [], Clock()
    source, syncer = Connector(calls), Syncer(calls)
    obj = SlackMaintenance(syncer, source, poll_interval_s=poll, reconcile_interval_s=reconcile,
        event_sink=lambda *args, **kwargs: logs.append((args, kwargs)), clock=clock, wall_clock=clock)
    return obj, source, syncer, clock, calls, logs


def test_periodic_schedule_reconciles_before_polling_and_event_does_not_defer():
    obj, _, _, clock, calls, _ = worker()
    assert obj.run_once()["polled"] is None
    clock.now = 9
    assert obj.run_once(event_wake=True)["polled"] == "slack"
    clock.now = 10
    assert obj.run_once()["polled"] == "all"
    clock.now = 29
    obj.run_once(event_wake=True)
    calls.clear()
    clock.now = 30
    result = obj.run_once()
    assert result["reconciled"] and calls == ["reconcile", ("poll", ["slack"])]
    # Poll at 29 advanced the all-platform deadline to 39, while Slack's
    # independent reconcile deadline stayed at 30.
    assert obj.status()["last_reconcile_success_at"] == 30


def test_simultaneously_due_work_reconciles_then_polls_all():
    obj, _, _, clock, calls, _ = worker()
    clock.now = 30
    assert obj.run_once() == {"reconciled": True, "polled": "all", "stopped": False}
    assert calls == ["reconcile", ("poll", None)]
    assert obj.run_once()["polled"] is None


def test_reconcile_failure_keeps_success_timestamp_and_still_consumes_events():
    obj, source, _, clock, calls, logs = worker()
    clock.now = 30
    obj.run_once()
    source.failure, clock.now = True, 60
    calls.clear()
    result = obj.run_once()
    assert result["reconcile_error_type"] == "SourceUnavailable"
    assert calls == ["reconcile", ("poll", None)]
    assert obj.status()["last_reconcile_success_at"] == 30
    assert obj.status()["reconcile_failures"] == 1
    assert "xoxp" not in repr(logs)
    source.failure, clock.now = False, 90
    obj.run_once()
    assert obj.status()["last_reconcile_success_at"] == 90
    assert obj.status()["reconcile_failures"] == 0


def test_poll_failure_is_safe_observable_and_does_not_kill_next_cycle():
    obj, _, syncer, clock, _, logs = worker()
    syncer.failure = True
    assert obj.run_once(event_wake=True)["poll_error_type"] == "RuntimeError"
    assert "xoxp" not in repr(logs)
    syncer.failure, clock.now = False, 10
    assert obj.run_once()["polled"] == "all"
    assert obj.status()["last_poll_error_type"] is None


def test_authorized_refresh_is_serialized_and_failure_sanitized():
    obj, _, syncer, _, calls, logs = worker()
    assert obj.refresh(["slack"]) == 10
    assert calls == [("full", ["slack"])]
    syncer.failure = True
    with pytest.raises(SourceUnavailable) as exc: obj.refresh()
    assert "xoxp" not in str(exc.value) + repr(logs)


def test_wake_is_nonblocking_and_multiple_starts_do_not_duplicate_worker():
    obj, _, syncer, _, calls, _ = worker()
    polled = threading.Event()
    original = syncer.poll
    def poll(platforms=None):
        original(platforms)
        polled.set()
    syncer.poll = poll
    obj.start()
    first = obj._thread
    obj.start()
    assert obj._thread is first and first.daemon
    obj.wake()
    assert polled.wait(1)
    assert calls == [("poll", ["slack"])]
    assert obj.stop(timeout_s=1)
    assert not obj.status()["running"]


def test_shutdown_is_bounded_when_source_call_is_in_progress():
    obj, _, syncer, _, _, logs = worker()
    entered, release = threading.Event(), threading.Event()
    def blocked_poll(platforms=None):
        entered.set()
        assert release.wait(1)
    syncer.poll = blocked_poll
    obj.start()
    obj.wake()
    assert entered.wait(1)
    assert obj.stop(timeout_s=0) is False
    assert any(args[1] == "slack_maintenance_shutdown_pending" for args, _ in logs)
    release.set()
    assert obj.stop(timeout_s=1)
    assert obj.run_once(event_wake=True)["stopped"]
    with pytest.raises(RuntimeError, match="cannot be restarted"): obj.start()


def test_manual_cycles_and_admin_refresh_cannot_overlap_source_mutation():
    obj, source, syncer, clock, _, _ = worker()
    clock.now = 30
    entered, release, refreshed = threading.Event(), threading.Event(), threading.Event()
    busy = threading.Lock()
    def reconcile():
        assert busy.acquire(blocking=False)
        entered.set()
        assert release.wait(1)
        busy.release()
        return 1
    def refresh(platforms=None):
        assert busy.acquire(blocking=False)
        busy.release()
        refreshed.set()
        return 1
    source.reconcile, syncer.full_load = reconcile, refresh
    cycle = threading.Thread(target=obj.run_once)
    admin = threading.Thread(target=obj.refresh)
    cycle.start()
    assert entered.wait(1)
    admin.start()
    assert not refreshed.is_set()
    release.set()
    cycle.join(1)
    admin.join(1)
    assert refreshed.is_set()


@pytest.mark.parametrize("value", [0, -1, True, float("nan"), float("inf"), "30"])
def test_invalid_intervals_rejected(value):
    with pytest.raises(ValueError): SlackMaintenance(None, None, poll_interval_s=value)
    with pytest.raises(ValueError): SlackMaintenance(None, None, reconcile_interval_s=value)


def test_event_sink_failure_is_reported_without_source_details(caplog):
    obj, source, _, clock, _, _ = worker()
    def broken_sink(*args, **kwargs): raise RuntimeError("xoxp-secret-log-sink")
    obj._event_sink, source.failure, clock.now = broken_sink, True, 30
    obj.run_once()
    assert "Maintenance event sink failed (RuntimeError)" in caplog.text
    assert "slack_reconciliation_failed (SourceUnavailable)" in caplog.text
    assert "xoxp" not in caplog.text


def test_unexpected_scheduler_failure_is_visible_and_sanitized():
    obj, _, _, _, _, logs = worker()
    def broken_clock(): raise RuntimeError("xoxp-secret-in-fatal-error")
    obj._clock = broken_clock
    with pytest.raises(RuntimeError, match="worker stopped unexpectedly") as exc:
        obj._loop()
    assert "xoxp" not in str(exc.value) + repr(logs)
    assert obj.status()["fatal_error_type"] == "RuntimeError"
    assert obj.status()["stopping"] is True


def test_manual_poll_preserves_incremental_semantics_and_safe_failures():
    obj, _, syncer, _, calls, logs = worker()
    assert obj.poll(["slack"]) == {"slack": 2}
    assert calls == [("poll", ["slack"])]
    syncer.failure = True
    with pytest.raises(SourceUnavailable, match="Maintenance poll failed") as exc:
        obj.poll()
    assert "xoxp" not in str(exc.value) + repr(logs)
    obj.stop(timeout_s=0)
    with pytest.raises(SourceUnavailable, match="stopping"):
        obj.poll()


def test_manual_poll_preserves_poll_semantics_and_stopping_boundary():
    obj, _, _, _, calls, _ = worker()
    assert obj.poll(['slack']) == {'slack':2}
    assert calls == [('poll',['slack'])]
    obj.stop()
    with pytest.raises(SourceUnavailable):
        obj.poll()


def test_manual_poll_failure_does_not_leak_exception_text():
    obj, _, syncer, _, _, logs = worker()
    syncer.failure = True
    with pytest.raises(SourceUnavailable, match='Maintenance poll failed'):
        obj.poll()
    assert 'xoxp' not in str(logs)
