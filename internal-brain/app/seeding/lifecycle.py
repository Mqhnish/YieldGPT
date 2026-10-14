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
    hold_within_s: float = 5.0        # F04: denial must hold within this long after the platform confirms


@dataclass
class LifecycleProbe:
    brain: object
    cfg: ProbeConfig = field(default_factory=ProbeConfig)
    sleep: callable = time.sleep
    # Client for the probe's own writes. The connectors' client keeps a short timeout so permission
    # checks fail closed fast; writes don't need that (seen live: a Jira transition took over 10 s).
    writer: object = None
    steps: list[Step] = field(default_factory=list)
    created: list = field(default_factory=list)   # (platform, native id) in creation order, for cleanup
    stage: str = ""                               # current step, named in error reports

    # ------------------------------------------------------------------ helpers
    @property
    def api(self):
        return self.writer or self.brain.connectors["confluence"].api

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

    def _c_create(self, tok, parent=None):
        sid = self.api.get("/wiki/api/v2/spaces", keys=self.cfg.space_key)["results"][0]["id"]
        body = {"spaceId": sid, "status": "current", "title": f"YieldGPT lifecycle probe {tok}", "body": self._c_body(tok)}
        if parent:
            body["parentId"] = parent
        return str(self.api.post("/wiki/api/v2/pages", body)["id"])

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

    def _j_transition(self, key):
        """Move the issue to any other status the workflow offers. Returns the new status name."""
        cur = self.api.get(f"/rest/api/3/issue/{quote(key, safe='')}", fields="status")["fields"]["status"]["name"]
        ts = self.api.get(f"/rest/api/3/issue/{quote(key, safe='')}/transitions").get("transitions", [])
        t = next(t for t in ts if (t.get("to") or {}).get("name") and t["to"]["name"] != cur)
        self.api.post(f"/rest/api/3/issue/{quote(key, safe='')}/transitions", {"transition": {"id": t["id"]}})
        return t["to"]["name"]

    def _j_comment(self, key, tok):
        self.api.post(f"/rest/api/3/issue/{quote(key, safe='')}/comment",
                      {"body": self._adf(f"Lifecycle probe comment {tok}.")})

    def _j_revoke(self, key):
        self.api.request("PUT", f"/rest/api/3/issue/{quote(key, safe='')}",
                         json={"fields": {"security": {"name": self.cfg.security_level}}})

    JIRA_NEEDS = ("BROWSE_PROJECTS", "CREATE_ISSUES", "EDIT_ISSUES", "TRANSITION_ISSUES", "ADD_COMMENTS",
                  "SET_ISSUE_SECURITY", "DELETE_ISSUES")

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

    def _hold_denied(self, who, tok, uid, t0):
        """Ask until 3 denials in a row (or timeout). Returns (held, seconds since t0, re-allows, last response)."""
        streak, flips = 0, 0
        while True:
            resp = self._ask(who, tok)
            if self._cites(resp, uid):
                flips += streak > 0
                streak = 0
            else:
                streak += 1
            if streak >= 3 or time.perf_counter() - t0 > self.cfg.timeout_s:
                return streak >= 3, time.perf_counter() - t0, flips, resp
            self.sleep(min(self.cfg.poll_every_s, 1.0))

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
        self.created.append((platform, nid))
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

        child = child_uid = tok3 = None
        if platform == "confluence":
            # 2b. a child page, to prove restrictions on the parent are inherited (L05)
            self.stage = "child page"
            tok3 = "zq" + secrets.token_hex(4)
            t = time.perf_counter()
            child = self._c_create(tok3, parent=nid)
            self.created.append((platform, child))
            child_uid = conn.uid(child)
            hit, s, tries = self._until(platform, lambda: self._cites(self._ask(self.cfg.viewer, tok3), child_uid))
            self._record(platform, "child page: retrievable by viewer", hit, time.perf_counter() - t,
                         f"{tries} poll+ask round(s)")
        else:
            # 2b. workflow status change and a new comment both served (L06)
            self.stage = "status and comment"
            tok3 = "zq" + secrets.token_hex(4)
            t = time.perf_counter()
            status = self._j_transition(nid)
            self._j_comment(nid, tok3)
            write_s = time.perf_counter() - t
            def updated_served():
                live = conn.fetch(nid)
                c = self._cites(self._ask(self.cfg.viewer, tok3), uid)
                entry = self.brain.index.get(uid)
                return (c and c[0]["version"] == live.version and entry is not None
                        and f"[{status}]" in entry.doc.text and tok3 in entry.doc.text)
            hit, s, tries = self._until(platform, updated_served)
            self._record(platform, "status change and new comment served", hit, write_s + s,
                         f"new status '{status}', {tries} poll+ask round(s)")

        # 3. revoke -> denied on the very next query, no reindex, looks like "no results"
        self.stage = "revoke"
        t = time.perf_counter()
        revoke(nid)
        write_s = time.perf_counter() - t
        confirmed = t = time.perf_counter()
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
        # Timed from when the platform confirmed the revoke (the write returned), as F04 defines it.
        # The write's own latency is Atlassian's and is reported separately.
        held, held_s, flips, resp = self._hold_denied(self.cfg.viewer, tok2, uid, confirmed)
        self._record(platform, "revoke: denial holds within 5 s of the revoke", held and held_s <= self.cfg.hold_within_s,
                     held_s, f"after the platform confirmed (revoke write {write_s:.2f}s); "
                                 f"3 denied queries in a row; allowed again after a denial: {flips} time(s)")
        if child:
            child_now = not self._cites(self._ask(self.cfg.viewer, tok3), child_uid)
            ccheck = conn.check(USERS[self.cfg.viewer], child)
            held_c, s, flips_c, _ = self._hold_denied(self.cfg.viewer, tok3, child_uid, confirmed)
            self._record(platform, "revoke: child page denied too (inherited restriction)",
                         child_now and ccheck.decision.value == "denied" and held_c and s <= self.cfg.hold_within_s,
                         s, f"after the parent's revoke was confirmed; next query denied: {child_now}, "
                            f"check={ccheck.reason_code}, allowed again after a denial: {flips_c} time(s)")
            ok, s, _ = self._until(platform, lambda: self._cites(self._ask(self.cfg.insider, tok3), child_uid))
            self._record(platform, "revoke: insider still served the child page", ok, s)
        missing = self._ask(self.cfg.viewer, "zq" + secrets.token_hex(4))   # never existed
        same_as_missing = (resp["answer"], resp["citations"], resp["status"]) == \
                          (missing["answer"], missing["citations"], missing["status"])
        self._record(platform, "revoke: denial identical to a nonexistent document", same_as_missing, 0.0)
        insider_ok, s, _ = self._until(platform, lambda: self._cites(self._ask(self.cfg.insider, tok2), uid))
        self._record(platform, "revoke: insider still served", insider_ok, s)

        # 4. delete -> never served again
        self.stage = "delete"
        if child:
            delete(child)
            self.created.remove((platform, child))
        t = time.perf_counter()
        delete(nid)
        write_s = time.perf_counter() - t
        t = time.perf_counter()
        gone_now = not self._cites(self._ask(self.cfg.insider, tok2), uid) and \
            not (child and self._cites(self._ask(self.cfg.insider, tok3), child_uid))
        next_q_s = time.perf_counter() - t
        self._record(platform, "delete: not served on next query (no reindex)", gone_now, write_s + next_q_s,
                     f"delete write {write_s:.2f}s, next query {next_q_s:.2f}s")
        purged, s, tries = self._until(platform, lambda: self.brain.index.get(uid) is None and
                                       (not child or self.brain.index.get(child_uid) is None))
        still_gone = not self._cites(self._ask(self.cfg.insider, tok2), uid)
        self._record(platform, "delete: removed from index by reconciliation, still not served",
                     purged and still_gone, s, f"{tries} poll round(s)")
        self.created.remove((platform, nid))

    def cleanup(self):
        """Delete whatever this probe created and has not deleted yet. Touches nothing else."""
        for platform, nid in reversed(list(self.created)):
            try:
                (self._c_delete if platform == "confluence" else self._j_delete)(nid)
                self._record(platform, "cleanup: probe object deleted", True, 0.0)
            except NotFound:
                pass
            except Exception as e:  # noqa: BLE001
                self._record(platform, "cleanup: probe object deleted", False, 0.0,
                             f"{type(e).__name__}: delete it by hand ({platform} {nid})")
            self.created.remove((platform, nid))

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
