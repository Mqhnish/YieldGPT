"""Seed a real Atlassian Cloud site with YieldGPT's demo company (Confluence + Jira).

Run it via scripts/seed_atlassian.py. Safe to re-run: everything is looked up before
it's created, and the id mapping is saved in a manifest.

What it does automatically
  Confluence  spaces, space READ grants for the intended groups, pages (parents first),
              page bodies with cross-links rewritten to real ids, page read restrictions
  Jira        site groups (+ members, if real account ids are mapped), projects if missing,
              issues (labelled so re-runs find them), statuses via transitions,
              issue links, remote links to Confluence / Slack / Drive, issue security
              levels (only with --apply-security, after the manual scheme step)
  Outputs     seed_manifest.json   demo id -> real id for every object
              expectations.json    who should / shouldn't see each object, for
                                   scripts/atlassian_live_check.py

What stays manual (admin screens, one-off; listed by manual_checklist())
  - remove default space permissions that grant everyone access
  - Jira permission schemes / project roles (who can browse each project)
  - the issue security scheme and its "security-only" level
These are org-wide policy changes. Automating them against a site we don't fully
control is how you lock yourself out, so a human does them once.

Ids are server-assigned on a real site (page ids are numbers, issue keys are
sequential), so all text that mentions a demo id (e.g. "Blocked by MIG-7") is
rewritten to the real id.
"""
from __future__ import annotations

import json
import re
from dataclasses import dataclass, field
from html import escape
from urllib.parse import quote

from ..identity import USERS, account_for
from ..sources.atlassian_client import AtlassianClient, NotFound
from ..sources.base import SourceUnavailable
from ..sources.confluence import ConfluenceConnector as SimConfluence
from ..sources.jira import JiraConnector as SimJira
from ..sources.links import url_for
from ..sources.world import World

LABEL = "yieldgpt-seed"
_KEY = re.compile(r"\b([A-Z][A-Z0-9_]*-\d+)\b")


def space_key_for(demo_key: str) -> str:
    """Confluence space keys are alphanumeric only: 'payment-gateway' -> 'PAYMENTGATEWAY'."""
    return re.sub(r"[^A-Za-z0-9]", "", demo_key).upper()


@dataclass
class Manifest:
    site: str = ""
    spaces: dict = field(default_factory=dict)    # demo key -> real key
    space_ids: dict = field(default_factory=dict)  # real key -> space id
    pages: dict = field(default_factory=dict)     # demo page id -> real page id
    issues: dict = field(default_factory=dict)    # demo issue key -> real issue key
    projects: dict = field(default_factory=dict)  # demo project key -> real project key
    log: list = field(default_factory=list)       # what happened, for the console

    def to_json(self) -> str:
        d = {k: v for k, v in self.__dict__.items() if k != "log"}
        return json.dumps(d, indent=2, sort_keys=True)

    @classmethod
    def from_json(cls, text: str) -> "Manifest":
        return cls(**json.loads(text))


class AtlassianSeeder:
    def __init__(self, client: AtlassianClient, demo: World | None = None, manifest: Manifest | None = None):
        self.api = client
        self.demo = demo or World()
        self.m = manifest or Manifest(site=client.site)
        self.m.site = client.site

    def note(self, msg: str):
        self.m.log.append(msg)

    # ------------------------------------------------------------------ helpers
    def _rewrite(self, text: str) -> str:
        return _KEY.sub(lambda mt: self.m.issues.get(mt.group(1), mt.group(1)), text)

    def _real_url(self, uid: str) -> str | None:
        platform, _, nid = uid.partition(":")
        if platform == "confluence":
            pid = self.m.pages.get(nid)
            if not pid:
                return None
            space = self.m.spaces[self.demo.pages[nid]["space"]]
            return f"{self.api.site}/wiki/spaces/{space}/pages/{pid}"
        if platform == "jira":
            key = self.m.issues.get(nid)
            return f"{self.api.site}/browse/{key}" if key else None
        return url_for(uid)  # Slack / Drive stay where they are

    def _adf(self, text: str) -> dict:
        return {"type": "doc", "version": 1, "content": [
            {"type": "paragraph", "content": [{"type": "text", "text": line}]}
            for line in text.split("\n") if line.strip()]}

    # ------------------------------------------------------------------ groups
    def seed_groups(self):
        """Every group the demo permissions mention. Members added only for personas whose
        Atlassian account ids are mapped (IB_ACCOUNT_MAP); demo ids are skipped."""
        names = set()
        for s in self.demo.spaces.values():
            names |= {p.split(":", 1)[1] for p in s["view"] if p.startswith("group:")}
        for proj in self.demo.projects.values():
            for members in proj["roles"].values():
                names |= {p.split(":", 1)[1] for p in members if p.startswith("group:")}
        for members in self.demo.security_levels.values():
            names |= {p.split(":", 1)[1] for p in members if p.startswith("group:")}
        for name in sorted(names):
            try:
                self.api.post("/rest/api/3/group", {"name": name})
                self.note(f"group {name}: created")
            except SourceUnavailable:
                self.note(f"group {name}: exists (or no permission to create)")
            for u in USERS.values():
                acct = account_for(u, "jira")
                if name in u.groups and acct and not acct.startswith("atl-557058:"):
                    try:
                        self.api.request("POST", "/rest/api/3/group/user", params={"groupname": name}, json={"accountId": acct})
                    except SourceUnavailable:
                        pass  # already a member

    # ------------------------------------------------------------------ Confluence
    def seed_spaces(self):
        for demo_key, s in sorted(self.demo.spaces.items()):
            key = space_key_for(demo_key)
            found = self.api.get("/wiki/api/v2/spaces", keys=key).get("results", [])
            if found:
                sid = str(found[0]["id"])
                self.note(f"space {key}: exists")
            else:
                r = self.api.post("/wiki/rest/api/space", {"key": key, "name": s["name"]})
                sid = str(r["id"])
                self.note(f"space {key}: created")
            self.m.spaces[demo_key], self.m.space_ids[key] = key, sid
            for p in sorted(s["view"]):
                if p.startswith("group:"):
                    try:
                        self.api.post(f"/wiki/rest/api/space/{key}/permission", {
                            "subject": {"type": "group", "identifier": p.split(":", 1)[1]},
                            "operation": {"key": "read", "target": "space"}})
                    except SourceUnavailable:
                        # Sites in Confluence "roles-only" mode refuse this API for everyone (HTTP 400):
                        # access then comes from space roles, set by hand (manual step).
                        self.note(f"space {key}: could not grant read to {p} by API "
                                  f"(already granted, or the site uses space roles: set it in the manual step)")

    def _page_order(self) -> list[str]:
        order, seen = [], set()

        def visit(pid):
            if pid in seen:
                return
            parent = self.demo.pages[pid]["parent"]
            if parent:
                visit(parent)
            seen.add(pid)
            order.append(pid)
        for pid in sorted(self.demo.pages):
            visit(pid)
        return order

    def _storage(self, pid: str) -> str:
        p = self.demo.pages[pid]
        html = "".join(f"<p>{escape(self._rewrite(line))}</p>" for line in p["body"].split("\n") if line.strip())
        for uid in p["links"]:
            url = self._real_url(uid)
            if url:
                label = self.m.issues.get(uid.split(":", 1)[1], uid.split(":", 1)[1])
                html += f'<p><a href="{escape(url)}">{escape(label)}</a></p>'
        return html

    def seed_pages(self):
        # pass 1: create (parents first) with plain bodies
        for pid in self._page_order():
            p = self.demo.pages[pid]
            space = self.m.spaces[p["space"]]
            sid = self.m.space_ids[space]
            found = self.api.get("/wiki/api/v2/pages", **{"space-id": sid, "title": p["title"], "limit": 1}).get("results", [])
            if found:
                self.m.pages[pid] = str(found[0]["id"])
                self.note(f"page '{p['title']}': exists")
                continue
            body = {"spaceId": sid, "status": "current", "title": p["title"],
                    "body": {"representation": "storage", "value": "<p>(seeding)</p>"}}
            if p["parent"]:
                body["parentId"] = self.m.pages[p["parent"]]
            self.m.pages[pid] = str(self.api.post("/wiki/api/v2/pages", body)["id"])
            self.note(f"page '{p['title']}': created")

    def finish_pages(self):
        """pass 2 (after Jira issues exist): real bodies with rewritten ids and links, then restrictions."""
        bot = self.api.get("/wiki/rest/api/user/current").get("accountId")
        for pid, real in self.m.pages.items():
            p = self.demo.pages[pid]
            cur = self.api.get(f"/wiki/api/v2/pages/{quote(real, safe='')}")
            self.api.request("PUT", f"/wiki/api/v2/pages/{quote(real, safe='')}", json={
                "id": real, "status": "current", "title": p["title"],
                "body": {"representation": "storage", "value": self._storage(pid)},
                "version": {"number": cur["version"]["number"] + 1, "message": "YieldGPT demo seed"}})
            if p["restrict"]:
                # personas without a real account can't be named in a restriction (they see nothing anyway)
                accts = [account_for(USERS[x.split(":", 1)[1]], "confluence")
                         for x in sorted(p["restrict"]) if x.startswith("user:") and x.split(":", 1)[1] in USERS]
                users = [{"type": "known", "accountId": a} for a in accts if a]
                users.append({"type": "known", "accountId": bot})  # never lock the integration out
                groups = [{"type": "group", "name": x.split(":", 1)[1]} for x in sorted(p["restrict"]) if x.startswith("group:")]
                self.api.request("PUT", f"/wiki/rest/api/content/{quote(real, safe='')}/restriction", json=[
                    {"operation": "read", "restrictions": {"user": users, "group": groups}}])
                self.note(f"page '{p['title']}': read restricted to {sorted(p['restrict'])}")

    # ------------------------------------------------------------------ Jira
    def seed_projects(self):
        for demo_key, proj in sorted(self.demo.projects.items()):
            try:
                self.api.get(f"/rest/api/3/project/{demo_key}")
                self.note(f"project {demo_key}: exists")
            except NotFound:
                bot = self.api.get("/rest/api/3/myself").get("accountId")
                try:
                    self.api.post("/rest/api/3/project", {
                        "key": demo_key, "name": proj["name"], "projectTypeKey": "software",
                        "leadAccountId": bot, "assigneeType": "PROJECT_LEAD"})
                    self.note(f"project {demo_key}: created (now set its permission scheme by hand)")
                except SourceUnavailable as e:
                    raise SourceUnavailable(f"project {demo_key} is missing and could not be created ({e}). "
                                            f"Create it by hand in Jira, then re-run.") from None
            self.m.projects[demo_key] = demo_key

    def seed_issues(self):
        # pass 1: create in a stable order so keys are predictable on an empty project
        for key in sorted(self.demo.issues, key=lambda k: (k.split("-")[0], int(k.split("-")[1]))):
            i = self.demo.issues[key]
            label = f"{LABEL}-{key}"
            found = self.api.post("/rest/api/3/search/jql", {"jql": f'labels = "{label}"', "maxResults": 1,
                                                             "fields": ["summary"]}).get("issues", [])
            if found:
                self.m.issues[key] = found[0]["key"]
                self.note(f"issue {key}: exists as {found[0]['key']}")
                continue
            r = self.api.post("/rest/api/3/issue", {"fields": {
                "project": {"key": self.m.projects[i["project"]]}, "summary": i["summary"],
                "issuetype": {"name": "Task"}, "labels": [LABEL, label],
                "description": self._adf("(seeding)")}})
            self.m.issues[key] = r["key"]
            self.note(f"issue {key}: created as {r['key']}")

    def finish_issues(self, apply_security: bool = False):
        for key, real in self.m.issues.items():
            i = self.demo.issues[key]
            fields = {"description": self._adf(self._rewrite(i["desc"]))}
            self.api.request("PUT", f"/rest/api/3/issue/{real}", json={"fields": fields})
            # status: find a transition into the demo status (workflows differ per site)
            ts = self.api.get(f"/rest/api/3/issue/{real}/transitions").get("transitions", [])
            match = next((t for t in ts if (t.get("to") or {}).get("name", "").lower() == i["status"].lower()), None)
            if match:
                self.api.post(f"/rest/api/3/issue/{real}/transitions", {"transition": {"id": match["id"]}})
            else:
                self.note(f"issue {real}: no transition to '{i['status']}' in this workflow, left as is")
            for uid in i["links"]:
                platform, _, nid = uid.partition(":")
                if platform == "jira" and nid in self.m.issues:
                    self.api.post("/rest/api/3/issueLink", {"type": {"name": "Relates"},
                                                            "outwardIssue": {"key": real},
                                                            "inwardIssue": {"key": self.m.issues[nid]}})
                elif platform != "jira":
                    url = self._real_url(uid)
                    if url:
                        # globalId makes this an upsert, so re-runs don't duplicate links
                        self.api.post(f"/rest/api/3/issue/{real}/remotelink", {
                            "globalId": f"yieldgpt:{uid}", "object": {"url": url, "title": uid}})
            if apply_security and i["level"]:
                try:
                    self.api.request("PUT", f"/rest/api/3/issue/{real}", json={"fields": {"security": {"name": i["level"]}}})
                    self.note(f"issue {real}: security level '{i['level']}' applied")
                except SourceUnavailable:
                    self.note(f"issue {real}: could not apply security level '{i['level']}'. "
                              f"Create the issue security scheme first (manual step 3)")

    # ------------------------------------------------------------------ run
    def run(self, apply_security: bool = False) -> Manifest:
        self.seed_groups()
        self.seed_spaces()
        self.seed_pages()
        self.seed_projects()
        self.seed_issues()
        self.finish_issues(apply_security)
        self.finish_pages()  # last: needs real issue keys and page ids for links
        return self.m

    # ------------------------------------------------------------------ outputs
    def expectations(self) -> list[dict]:
        """Who should see what on the seeded site: the simulator's verdict on the demo
        company, translated to real ids. Feed this to scripts/atlassian_live_check.py."""
        sim_c, sim_j = SimConfluence(self.demo), SimJira(self.demo)
        out = []
        for u in sorted(USERS):
            for pid, real in sorted(self.m.pages.items()):
                out.append({"user": u, "platform": "confluence", "id": real, "demo_id": pid,
                            "expect": sim_c.check(USERS[u], pid).decision.value})
            for key, real in sorted(self.m.issues.items()):
                out.append({"user": u, "platform": "jira", "id": real, "demo_id": key,
                            "expect": sim_j.check(USERS[u], key).decision.value})
        return out

    def manual_checklist(self) -> list[str]:
        steps = []
        for demo_key, s in sorted(self.demo.spaces.items()):
            groups = sorted(p.split(":", 1)[1] for p in s["view"] if p.startswith("group:"))
            steps.append(f"Confluence space {self.m.spaces.get(demo_key, space_key_for(demo_key))}: "
                         f"remove any default 'View' grants so ONLY these groups can view: {', '.join(groups)}")
        for key, proj in sorted(self.demo.projects.items()):
            browse = sorted({p.split(':', 1)[1] for r in proj["browse"] for p in proj["roles"].get(r, set())})
            steps.append(f"Jira project {key}: permission scheme where 'Browse Projects' is granted ONLY to groups: "
                         f"{', '.join(browse)}")
        for level, members in sorted(self.demo.security_levels.items()):
            issues = [self.m.issues.get(k, k) for k, i in sorted(self.demo.issues.items()) if i["level"] == level]
            groups = sorted(p.split(":", 1)[1] for p in members if p.startswith("group:"))
            steps.append(f"Jira issue security scheme with level '{level}' (members: groups {', '.join(groups)}), "
                         f"attached to projects of {', '.join(issues)}. Then re-run with --apply-security")
        steps.append("Add each teammate persona to their groups (Admin > Groups) and write accounts.json. "
                     "Leave the contractor persona WITHOUT an Atlassian account")
        return steps
