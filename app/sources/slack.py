"""Slack connector. Owner: Member 2 (moved from the shared file; logic unchanged).

Native model (simulated scope): conversation membership, plus workspace
boundary and channel retention. The unit of meaning is a thread.

TODO(Member 2): public-channel semantics per the installed app's token/scopes,
DMs, edits/deletions, workspace-scoped user ids.
"""
import time

from .base import Decision, SourceDoc
from .sim import SimulatedConnector


class SlackConnector(SimulatedConnector):
    platform = "slack"

    def _ids(self):
        return list(self.w.threads)

    def _live_msgs(self, tid):
        ch = self.w.channels[tid.split("/")[0]]
        cutoff = time.time() - ch["retention_days"] * 86400
        return [m for m in self.w.threads[tid]["msgs"] if m[1] >= cutoff]

    def fetch(self, tid):
        self.w.guard(self.platform)
        if tid not in self.w.threads:
            return None
        msgs = self._live_msgs(tid)
        if not msgs:
            return None  # fully expired under retention = gone
        channel = tid.split("/")[0]
        latest = max(m[1] for m in msgs)
        return SourceDoc(self.uid(tid), self.platform, self.w.channels[channel]["workspace"], tid, channel,
                         f"#{channel} thread by @{msgs[0][0]}", "\n".join(f"@{u}: {t}" for u, _, t in msgs),
                         f"https://companya.slack.com/archives/{channel}/p{tid.split('/')[1]}",
                         version=f"{latest:.6f}:{len(msgs)}", updated_at=latest, parent=channel, author=msgs[0][0])

    def acl_hint(self, tid):
        self.w.guard(self.platform)
        return {f"user:{u}" for u in self.w.channels[tid.split("/")[0]]["members"]}

    def _check(self, user, account, tid):
        self.w.guard(self.platform)
        channel = tid.split("/")[0]
        ch = self.w.channels.get(channel)
        if not ch or tid not in self.w.threads:
            return Decision.DENIED, "not_found", "thread does not exist", ""
        if user.username not in ch["members"]:
            code = "not_in_private_channel" if ch["private"] else "not_in_channel"
            return Decision.DENIED, code, f"not a member of #{channel}", ""
        return Decision.ALLOWED, "channel_member", f"member of #{channel}", ""
