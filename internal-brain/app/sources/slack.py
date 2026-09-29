"""Offline Slack connector with account-based authorization and whole-thread reads.

Legacy fixture IDs remain stable. New/live adapters use workspace-scoped IDs;
see slack_live.py. Public-channel discovery is explicitly opt-in in fixtures,
so existing membership-only demonstrations retain their stated semantics.
"""
import hashlib
import json
import time

from ..identity import USERS, account_for
from .base import Decision
from .sim import SimulatedConnector
from .base import SourceUnavailable
from .slack_content import SlackSourceDoc, thread_text


class SlackConnector(SimulatedConnector):
    platform = "slack"

    def _ids(self):
        return list(self.w.threads)

    def _channel(self, tid):
        # A new fixture may set channel explicitly and use TEAM/CHANNEL/TS IDs.
        thread = self.w.threads.get(tid, {})
        return thread.get("channel", tid.rsplit("/", 1)[0])

    def _live_msgs(self, tid):
        ch = self.w.channels.get(self._channel(tid))
        if not ch or tid not in self.w.threads:
            return []
        days = ch.get("retention_days")
        cutoff = time.time() - days * 86400 if days is not None else 0
        return [m for m in self.w.threads[tid]["msgs"] if m[1] >= cutoff]

    def fetch(self, tid):
        self.w.guard(self.platform)
        msgs = self._live_msgs(tid)
        if not msgs:
            return None
        channel = self._channel(tid)
        ch = self.w.channels[channel]
        latest = max(max(m[1] for m in msgs), self.w.threads[tid].get("edited_at", 0))
        version = hashlib.sha256(json.dumps(msgs, separators=(",", ":")).encode()).hexdigest()
        label = "Direct conversation" if ch.get("is_im") or ch.get("is_mpim") else f"#{channel}"
        text, spans = thread_text([(f"@{u}: {t}", ts) for u, ts, t in msgs])
        return SlackSourceDoc(self.uid(tid), self.platform, ch["workspace"], tid, channel,
                         f"{label} thread by @{msgs[0][0]}", text,
                         f"https://companya.slack.com/archives/{channel}/p{tid.rsplit('/', 1)[1].replace('.', '')}",
                         version=version, updated_at=latest, parent=channel, author=msgs[0][0], message_spans=spans)

    @staticmethod
    def _accounts(ch):
        """The fixture directory resolves native identity, never the asker's name."""
        accounts = set(ch.get("member_accounts", ()))
        for member in ch.get("members", ()):
            if member in USERS:
                linked = account_for(USERS[member], "slack")
                if linked:
                    accounts.add(linked)
            elif "/" in member:
                accounts.add(member)
        return accounts

    def acl_hint(self, tid):
        self.w.guard(self.platform)
        # Conservative superset: alias accounts can map to different corporate
        # names. An index hint must never overrule authoritative native checks.
        return {"anyone"}

    def _check(self, user, account, tid):
        self.w.guard(self.platform)
        ch = self.w.channels.get(self._channel(tid))
        doc = self.fetch(tid)
        if not ch or doc is None:
            return Decision.DENIED, "not_found", "thread is unavailable", ""
        if account in self._accounts(ch):
            return Decision.ALLOWED, "conversation_member", "mapped account is a conversation member", doc.version
        # Model public discovery explicitly, including the workspace membership
        # and user scopes; being an employee does not imply access to every team.
        if (ch.get("public_read", False) and not ch.get("private")
                and not ch.get("is_im") and not ch.get("is_mpim")
                and account in ch.get("workspace_accounts", ())):
            return Decision.ALLOWED, "public_workspace_read", "mapped account can read public conversation", doc.version
        return Decision.DENIED, "not_in_conversation", "mapped account cannot read conversation", ""

    def read_authorized(self, user, native_id):
        result = self.check(user, native_id)
        if result.decision is Decision.UNAVAILABLE:
            raise SourceUnavailable("Slack authorization unavailable")
        return self.fetch(native_id) if result.allowed else None
