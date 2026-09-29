"""One serialized maintenance scheduler for live Slack and the shared syncer.

Use this INSTEAD OF Syncer.start_polling when Slack is live. Verified webhook
handlers call wake() and ACK; source reads happen only in this background
worker. Manual admin refreshes must use refresh(), not call the syncer directly.
"""
from __future__ import annotations

import logging
import math
import threading
import time

from .sources.base import SourceUnavailable

_LOG = logging.getLogger(__name__)


class SlackMaintenance:
    def __init__(self, syncer, connector, *, poll_interval_s=300,
                 reconcile_interval_s=900, event_sink=None,
                 clock=time.monotonic, wall_clock=time.time):
        for value in (poll_interval_s, reconcile_interval_s):
            if isinstance(value, bool) or not isinstance(value, (int, float)) or not math.isfinite(value) or value <= 0:
                raise ValueError("Maintenance intervals must be finite positive seconds")
        self.syncer, self.connector = syncer, connector
        self.poll_interval_s, self.reconcile_interval_s = float(poll_interval_s), float(reconcile_interval_s)
        self._event_sink, self._clock, self._wall_clock = event_sink, clock, wall_clock
        self._cycle_lock = threading.Lock()
        self._state_lock = threading.Lock()
        self._lifecycle_lock = threading.Lock()
        self._signal, self._stop = threading.Event(), threading.Event()
        self._thread = None
        now = clock()
        self._next_poll, self._next_reconcile = now + self.poll_interval_s, now + self.reconcile_interval_s
        self._state = {"last_poll_at": None, "last_reconcile_attempt_at": None,
                       "last_reconcile_success_at": None, "last_reconcile_error_type": None,
                       "last_poll_error_type": None, "reconcile_failures": 0,
                       "fatal_error_type": None}

    def _report(self, event: str, **fields):
        # No source exception messages, request objects, credential variables or
        # traceback details are passed to logs. Failure types are sufficient.
        if self._event_sink is not None:
            try:
                self._event_sink("system", event, **fields)
                return
            except Exception as error:
                _LOG.error("Maintenance event sink failed (%s)", type(error).__name__)
        if "error_type" in fields:
            _LOG.error("%s (%s)", event, fields["error_type"])
        else:
            _LOG.info("%s", event)

    def status(self) -> dict:
        with self._state_lock:
            return {**self._state, "running": bool(self._thread and self._thread.is_alive()),
                    "stopping": self._stop.is_set(), "poll_interval_s": self.poll_interval_s,
                    "reconcile_interval_s": self.reconcile_interval_s}

    def wake(self):
        """Non-blocking: coalesce verified events; never read a source in ACK."""
        if not self._stop.is_set():
            self._signal.set()

    def run_once(self, *, event_wake=False) -> dict:
        """Perform due work once; fake clocks make scheduling testable without sleep.

        Reconcile is attempted before polling when due. Failures preserve its
        last-success timestamp and are observable. Already queued events are
        still polled after a reconciliation failure. Event wakes never postpone
        either periodic deadline. A slow operation can delay later work; a
        single worker intentionally never overlaps runs to hide that delay.
        """
        with self._cycle_lock:
            if self._stop.is_set():
                return {"reconciled": False, "polled": None, "stopped": True}
            now = self._clock()
            reconcile_due, poll_due = now >= self._next_reconcile, now >= self._next_poll
            result = {"reconciled": False, "polled": None, "stopped": False}
            if reconcile_due:
                self._next_reconcile = now + self.reconcile_interval_s
                with self._state_lock:
                    self._state["last_reconcile_attempt_at"] = self._wall_clock()
                try:
                    count = self.connector.reconcile()
                except Exception as error:
                    kind = type(error).__name__
                    with self._state_lock:
                        self._state["last_reconcile_error_type"] = kind
                        self._state["reconcile_failures"] += 1
                    self._report("slack_reconciliation_failed", error_type=kind)
                    result["reconcile_error_type"] = kind
                else:
                    with self._state_lock:
                        self._state["last_reconcile_success_at"] = self._wall_clock()
                        self._state["last_reconcile_error_type"] = None
                        self._state["reconcile_failures"] = 0
                    self._report("slack_reconciliation_completed", thread_count=count if isinstance(count, int) else 0)
                    result["reconciled"] = True
            if self._stop.is_set():
                result["stopped"] = True
                return result
            if poll_due or event_wake or reconcile_due:
                if poll_due:
                    self._next_poll = now + self.poll_interval_s
                platforms = None if poll_due else ["slack"]
                with self._state_lock:
                    self._state["last_poll_at"] = self._wall_clock()
                try:
                    self.syncer.poll(platforms)
                except Exception as error:
                    kind = type(error).__name__
                    with self._state_lock:
                        self._state["last_poll_error_type"] = kind
                    self._report("slack_maintenance_poll_failed", error_type=kind)
                    result["poll_error_type"] = kind
                else:
                    # Syncer captures individual source failures in its own
                    # PlatformSyncState; this field only covers raised failures.
                    with self._state_lock:
                        self._state["last_poll_error_type"] = None
                result["polled"] = "all" if platforms is None else "slack"
            return result

    def poll(self, platforms=None):
        """Serialize an authorized manual incremental poll without a full crawl."""
        with self._cycle_lock:
            if self._stop.is_set():
                raise SourceUnavailable("Maintenance worker is stopping")
            try:
                return self.syncer.poll(platforms)
            except Exception as error:
                self._report("slack_maintenance_manual_poll_failed", error_type=type(error).__name__)
                raise SourceUnavailable("Maintenance poll failed") from None

    def poll(self, platforms=None):
        """Serialize an authorized manual poll with scheduled work."""
        with self._cycle_lock:
            if self._stop.is_set():
                raise SourceUnavailable("Maintenance worker is stopping")
            try:
                return self.syncer.poll(platforms)
            except Exception as error:
                self._report("slack_maintenance_poll_failed", error_type=type(error).__name__)
                raise SourceUnavailable("Maintenance poll failed") from None

    def refresh(self, platforms=None):
        """Serialize an authorized admin full refresh with all worker activity."""
        with self._cycle_lock:
            if self._stop.is_set():
                raise SourceUnavailable("Maintenance worker is stopping")
            try:
                return self.syncer.full_load(platforms)
            except Exception as error:
                self._report("slack_maintenance_refresh_failed", error_type=type(error).__name__)
                raise SourceUnavailable("Maintenance refresh failed") from None

    def start(self):
        """Start once; an existing live worker is reused rather than duplicated."""
        with self._lifecycle_lock:
            if self._thread and self._thread.is_alive():
                return self
            if self._stop.is_set():
                raise RuntimeError("A stopped maintenance worker cannot be restarted")
            self._thread = threading.Thread(target=self._loop, name="slack-maintenance", daemon=True)
            self._thread.start()
        return self

    def _loop(self):
        try:
            while not self._stop.is_set():
                # Bound each wait so stop() is responsive; Event.set also wakes
                # it immediately. Reading deadlines only requires the cycle
                # lock briefly and never overlaps connector work.
                with self._cycle_lock:
                    delay = max(0.0, min(self._next_poll, self._next_reconcile) - self._clock())
                self._signal.wait(min(delay, 60.0))
                if self._stop.is_set():
                    break
                is_event = self._signal.is_set()
                self._signal.clear()
                self.run_once(event_wake=is_event)
        except BaseException as error:
            # Expected source failures are handled by run_once. Unexpected
            # scheduler failures must be visible and stop the worker. Re-raise
            # a sanitized error so Python reports a fatal thread exit without
            # exposing arbitrary exception text or source credentials.
            kind = type(error).__name__
            with self._state_lock:
                self._state["fatal_error_type"] = kind
            self._stop.set()
            self._report("slack_maintenance_stopped_unexpectedly", error_type=kind)
            raise RuntimeError("Slack maintenance worker stopped unexpectedly") from None

    def stop(self, timeout_s=2.0) -> bool:
        """Request shutdown and join for at most timeout_s; report incomplete stop.

        This cannot cancel an in-flight HTTP request. If False is returned, do
        not close its HTTP client while that operation is still running. The
        daemon will observe stop after the current bounded source call/cycle.
        """
        if isinstance(timeout_s, bool) or not isinstance(timeout_s, (int, float)) or not math.isfinite(timeout_s) or timeout_s < 0:
            raise ValueError("Shutdown timeout must be finite non-negative seconds")
        self._stop.set()
        self._signal.set()
        thread = self._thread
        if thread and thread is not threading.current_thread():
            thread.join(timeout=timeout_s)
        stopped = not thread or not thread.is_alive()
        if not stopped:
            self._report("slack_maintenance_shutdown_pending", error_type="ShutdownTimeout")
        return stopped
