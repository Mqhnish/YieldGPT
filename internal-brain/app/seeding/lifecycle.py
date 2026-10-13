"""Lifecycle probe for Confluence and Jira (metrics L05, L06, G14). Owner: Member 1.

For each platform it creates ONE probe object, then proves through the real pipeline
(Brain.ask, same connectors and permission checks the app uses):

  create   the new object becomes retrievable for a persona who can see it
  edit     the new version is served, the old text is not
  revoke   after a page restriction / issue security level, the next query is denied
           (no reindex), and the denial looks exactly like "no results"
  delete   the object is never served again, before and after the index catches up

Each step is timed. Only objects this probe created are written to, and they are
deleted in a `finally` (Confluence moves the page to the trash). The report it builds
holds no tokens, emails, accountIds or site name.
"""
from __future__ import annotations

import secrets
import time
from dataclasses import dataclass, field
from urllib.parse import quote

from ..identity import USERS
from ..sources.atlassian_client import NotFound

QUIET = "I couldn't find anything available to you"


@dataclass
class Step:
    platform: str
    step: str
    ok: bool
    seconds: float
    detail: str = ""


@dataclass
class ProbeConfig:
    space_key: str = "ENG"            # a space the viewer can read
    project_key: str = "MIG"          # a project the viewer can browse
    viewer: str = "ravi"              # sees the object until it is revoked
    insider: str = "asha"             # still sees it after the revoke
    security_level: str = "security-only"
    timeout_s: float = 240.0          # live search indexes can lag; polling has minute precision
    poll_every_s: float = 5.0


@dataclass
class LifecycleProbe:
    brain: object
    cfg: ProbeConfig = field(default_factory=ProbeConfig)
    sleep: callable = time.sleep
    steps: list[Step] = field(default_factory=list)
    created: dict = field(default_factory=dict)   # platform -> native id, for cleanup
    stage: str = ""                               # current step, named in error reports

    # ------------------------------------------------------------------ helpers
    @property
    def api(self):
        return self.brain.connectors["confluence"].api

    def _ask(self, who, tok):
        return self.brain.ask(USERS[who], f"lifecycle probe {tok}")

    @staticmethod
    def _cites(resp, uid):
        return [c for c in resp["citations"] if c["uid"] == uid]

    def _until(self, platform, fn):
        """Poll the platform and retry fn() until it returns truthy or the timeout passes."""
        t0, tries = time.perf_counter(), 0
        while True:
            tries += 1
            self.brain.syncer.poll([platform])
            got = fn()
            if got or time.perf_counter() - t0 > self.cfg.timeout_s:
                return got, time.perf_counter() - t0, tries
            self.sleep(self.cfg.poll_every_s)

    def _record(self, platform, step, ok, seconds, detail=""):
        self.steps.append(Step(platform, step, bool(ok), round(seconds, 3), detail))
        return ok

    # ------------------------------------------------------------------ Confluence writes
    def _c_body(self, tok):
        return {"representation": "storage",
                "value": f"<p>YieldGPT lifecycle probe {tok}. Temporary test page, deleted automatically.</p>"}

    def _c_create(self, tok):
        sid = self.api.get("/wiki/api/v2/spaces", keys=self.cfg.space_key)["results"][0]["id"]
        r = self.api.post("/wiki/api/v2/pages", {"spaceId": sid, "status": "current",
                                                  "title": f"YieldGPT lifecycle probe {tok}", "body": self._c_body(tok)})
        return str(r["id"])

    def _c_edit(self, pid, tok):
        cur = self.api.get(f"/wiki/api/v2/pages/{quote(pid, safe='')}")
        self.api.request("PUT", f"/wiki/api/v2/pages/{quote(pid, safe='')}", json={
            "id": pid, "status": "current", "title": cur["title"], "body": self._c_body(tok),
            "version": {"number": cur["version"]["number"] + 1, "message": "lifecycle probe edit"}})

    def _c_revoke(self, pid):
        bot = self.api.get("/wiki/rest/api/user/current").get("accountId")
        users = [{"type": "known", "accountId": a} for a in
                 (self._account(self.cfg.insider, "confluence"), bot) if a]   # never lock the integration out
        # view AND edit, as the Confluence UI does: a view-only restriction can stop the bot deleting it
        self.api.request("PUT", f"/wiki/rest/api/content/{quote(pid, safe='')}/restriction", json=[
            {"operation": op, "restrictions": {"user": users, "group": []}} for op in ("read", "update")])

    def _c_delete(self, pid):
        self.api.request("DELETE", f"/wiki/api/v2/pages/{quote(pid, safe='')}")

    # ------------------------------------------------------------------ Jira writes
    @staticmethod
    def _adf(text):
        return {"type": "doc", "version": 1,
                "content": [{"type": "paragraph", "content": [{"type": "text", "text": text}]}]}

    def _j_create(self, tok):
        r = self.api.post("/rest/api/3/issue", {"fields": {
            "project": {"key": self.cfg.project_key}, "issuetype": {"name": "Task"},
            "summary": f"YieldGPT lifecycle probe {tok}",
            "description": self._adf(f"YieldGPT lifecycle probe {tok}. Temporary test issue, deleted automatically.")}})
        return r["key"]

    def _j_edit(self, key, tok):
        self.api.request("PUT", f"/rest/api/3/issue/{quote(key, safe='')}", json={"fields": {
            "summary": f"YieldGPT lifecycle probe {tok}",
            "description": self._adf(f"YieldGPT lifecycle probe {tok}. Temporary test issue, deleted automatically.")}})

    def _j_revoke(self, key):
        self.api.request("PUT", f"/rest/api/3/issue/{quote(key, safe='')}",
                         json={"fields": {"security": {"name": self.cfg.security_level}}})

    JIRA_NEEDS = ("BROWSE_PROJECTS", "CREATE_ISSUES", "EDIT_ISSUES", "SET_ISSUE_SECURITY", "DELETE_ISSUES")

    def _j_missing(self):
        """Project permissions the integration account lacks. Checked BEFORE creating anything,
        so a missing grant can't leave a probe issue behind (seen live: no Delete Issues)."""
        r = self.api.get("/rest/api/3/mypermissions", projectKey=self.cfg.project_key,
                         permissions=",".join(self.JIRA_NEEDS))
        perms = r.get("permissions", {})
        return [p for p in self.JIRA_NEEDS if not (perms.get(p) or {}).get("havePermission")]

    def _j_delete(self, key):
        self.api.request("DELETE", f"/rest/api/3/issue/{quote(key, safe='')}")

    @staticmethod
    def _account(username, platform):
        return dict(USERS[username].accounts).get(platform)

    # ------------------------------------------------------------------ the lifecycle
    def run_platform(self, platform):
        conn = self.brain.connectors[platform]
        if platform == "jira":
            self.stage = "preflight"
            missing = self._j_missing()
            self._record(platform, "preflight: integration account has the Jira permissions it needs", not missing,
                         0.0, f"missing in {self.cfg.project_key}: {', '.join(missing)}" if missing else "")
            if missing:
                return
        w = {"confluence": (self._c_create, self._c_edit, self._c_revoke, self._c_delete),
             "jira": (self._j_create, self._j_edit, self._j_revoke, self._j_delete)}[platform]
        create, edit, revoke, delete = w
        tok1, tok2 = "zq" + secrets.token_hex(4), "zq" + secrets.token_hex(4)

        # 1. create -> retrievable
        self.stage = "create"
        t = time.perf_counter()
        nid = create(tok1)
        self.created[platform] = nid
        uid = conn.uid(nid)
        write_s = time.perf_counter() - t
        hit, s, tries = self._until(platform, lambda: self._cites(self._ask(self.cfg.viewer, tok1), uid))
        self._record(platform, "create: retrievable by viewer", hit, write_s + s,
                     f"write {write_s:.2f}s, then {tries} poll+ask round(s)")
        if not hit:
            return

        # 2. edit -> new version served, old text gone
        self.stage = "edit"
        t = time.perf_counter()
        edit(nid, tok2)
        write_s = time.perf_counter() - t
        live_version = conn.fetch(nid).version
        def new_served():
            c = self._cites(self._ask(self.cfg.viewer, tok2), uid)
            return c if c and c[0]["version"] == live_version else None
        hit, s, tries = self._until(platform, new_served)
        # The old token's question may still match the page through its title; what must never
        # come back is the old version or the old text.
        old = self._ask(self.cfg.viewer, tok1)
        old_gone = (all(c["version"] == live_version for c in self._cites(old, uid))
                    and tok1 not in old["answer"])
        self._record(platform, "edit: new version served, old text not served", hit and old_gone, write_s + s,
                     f"{tries} poll+ask round(s); old version or text served: {not old_gone}")

        # 3. revoke -> denied on the very next query, no reindex, looks like "no results"
        self.stage = "revoke"
        t = time.perf_counter()
        revoke(nid)
        write_s = time.perf_counter() - t
        t = time.perf_counter()
        resp = self._ask(self.cfg.viewer, tok2)                   # no poll: the index still has the doc
        next_q_s = time.perf_counter() - t
        denied_now = not self._cites(resp, uid)
        check = conn.check(USERS[self.cfg.viewer], nid)
        self._record(platform, "revoke: viewer denied on next query (no reindex)", denied_now and
                     check.decision.value == "denied", write_s + next_q_s,
                     f"revoke write {write_s:.2f}s, next query {next_q_s:.2f}s, check={check.reason_code}")
        # Atlassian's permission engine can take a moment to apply a change everywhere (seen live:
        # the same bulk check flipped between calls seconds apart). Measure how long until the
        # denial holds: 3 denied queries in a row. F04's bar is 5 s after the source confirms.
        t, streak, flips = time.perf_counter(), 0, 0
        while True:
            resp = self._ask(self.cfg.viewer, tok2)
            if self._cites(resp, uid):
                flips += streak > 0
                streak = 0
            else:
                streak += 1
            if streak >= 3 or time.perf_counter() - t > self.cfg.timeout_s:
                break
            self.sleep(min(self.cfg.poll_every_s, 1.0))
        held_s = write_s + time.perf_counter() - t
        self._record(platform, "revoke: denial holds within 5 s of the revoke", streak >= 3 and held_s <= 5.0,
                     held_s, f"3 denied queries in a row; allowed again after a denial: {flips} time(s)")
        missing = self._ask(self.cfg.viewer, "zq" + secrets.token_hex(4))   # never existed
        same_as_missing = (resp["answer"], resp["citations"], resp["status"]) == \
                          (missing["answer"], missing["citations"], missing["status"])
        self._record(platform, "revoke: denial identical to a nonexistent document", same_as_missing, 0.0)
        insider_ok, s, _ = self._until(platform, lambda: self._cites(self._ask(self.cfg.insider, tok2), uid))
        self._record(platform, "revoke: insider still served", insider_ok, s)

        # 4. delete -> never served again
        self.stage = "delete"
        t = time.perf_counter()
        delete(nid)
        write_s = time.perf_counter() - t
        t = time.perf_counter()
        gone_now = not self._cites(self._ask(self.cfg.insider, tok2), uid)
        next_q_s = time.perf_counter() - t
        self._record(platform, "delete: not served on next query (no reindex)", gone_now, write_s + next_q_s,
                     f"delete write {write_s:.2f}s, next query {next_q_s:.2f}s")
        purged, s, tries = self._until(platform, lambda: self.brain.index.get(uid) is None)
        still_gone = not self._cites(self._ask(self.cfg.insider, tok2), uid)
        self._record(platform, "delete: removed from index by reconciliation, still not served",
                     purged and still_gone, s, f"{tries} poll round(s)")
        self.created.pop(platform, None)

    def cleanup(self):
        """Delete whatever this probe created and has not deleted yet. Touches nothing else."""
        for platform, nid in list(self.created.items()):
            try:
                (self._c_delete if platform == "confluence" else self._j_delete)(nid)
                self._record(platform, "cleanup: probe object deleted", True, 0.0)
            except NotFound:
                pass
            except Exception as e:  # noqa: BLE001
                self._record(platform, "cleanup: probe object deleted", False, 0.0,
                             f"{type(e).__name__}: delete it by hand ({platform} {nid})")
            self.created.pop(platform, None)

    def run(self, platforms=("confluence", "jira")):
        try:
            for p in platforms:
                try:
                    self.run_platform(p)
                except Exception as e:  # noqa: BLE001  (record and move on; cleanup below)
                    self._record(p, "error", False, 0.0, f"during {self.stage or 'setup'}: {type(e).__name__}: {e}")
        finally:
            self.cleanup()
        return self.steps
