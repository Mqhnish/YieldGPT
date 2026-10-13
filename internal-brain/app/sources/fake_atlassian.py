"""Fake Atlassian Cloud site for tests and the offline demo ("fixture" mode).

Plugged into the real connectors as an httpx transport, so the connectors run their
real HTTP code, pagination, JSON parsing and error handling. Only the network is fake.

Content comes live from the simulated World, so a test that restricts a page or
removes a project role changes what this "site" answers immediately, just like the
real thing. Permission decisions reuse the simulator's rules as the stand-in for
Atlassian's permission engine.

Response shapes follow the public Atlassian Cloud REST docs. They are an
approximation: docs/ATLASSIAN_SETUP.md has the live conformance run that confirms
them against a real site.
"""
from __future__ import annotations

import json
import time
import re
from datetime import datetime, timezone
from html import escape
from urllib.parse import unquote

import httpx

from ..identity import USERS, account_for
from .base import Decision
from .confluence import ConfluenceConnector as SimConfluence
from .jira import JiraConnector as SimJira
from .links import ATLASSIAN_SITE, url_for
from .world import World

BASE = f"https://{ATLASSIAN_SITE}"


def _iso_confluence(ts: float) -> str:
    return datetime.fromtimestamp(ts, timezone.utc).isoformat(timespec="milliseconds").replace("+00:00", "Z")


def _iso_jira(ts: float) -> str:
    return datetime.fromtimestamp(ts, timezone.utc).strftime("%Y-%m-%dT%H:%M:%S.%f")[:-3] + "+0000"


def _minute(lit: str, fmt: str) -> float:
    return datetime.strptime(lit, fmt).replace(tzinfo=timezone.utc).timestamp()


class _LiveAccounts:
    """accountId -> CURRENT User. Looked up on every call (never cached), because on a real
    site group membership changes take effect immediately and the fake must behave the same."""

    def get(self, account_id, default=None):
        for u in USERS.values():
            if account_id and account_for(u, "confluence") == account_id:
                return u
        return default


class FakeAtlassian:
    def __init__(self, world: World):
        self.w = world
        self.sim_conf = SimConfluence(world)
        self.sim_jira = SimJira(world)
        self.space_ids: dict[str, str] = {}
        self.space_keys: dict[str, str] = {}
        for k in sorted(world.spaces):
            self._sid(k)
        self._next_page = 65536
        self.groups: dict[str, set[str]] = {}       # site groups created via API (name -> accountIds)
        self.bot_account = "atl-557058:integration-bot"
        self.jira_ids: dict[str, int] = {}
        for k in sorted(world.issues):
            self._jid(k)
        self.by_account = _LiveAccounts()   # resolved per request: group changes apply immediately
        self.calls: list[str] = []  # request log, handy in tests
        self.bot_lacks: set[str] = set()   # Jira project permissions the integration account lacks

    def transport(self) -> httpx.MockTransport:
        return httpx.MockTransport(self.handle)

    # ------------------------------------------------------------------ plumbing
    def _sid(self, key: str) -> str:
        if key not in self.space_ids:
            self.space_ids[key] = str(1001 + len(self.space_ids))
            self.space_keys[self.space_ids[key]] = key
        return self.space_ids[key]

    def _jid(self, key: str) -> int:
        if key not in self.jira_ids:
            self.jira_ids[key] = 10000 + len(self.jira_ids)
        return self.jira_ids[key]

    @staticmethod
    def _json(status, body=None):
        return httpx.Response(status, json=body if body is not None else {})

    def handle(self, req: httpx.Request) -> httpx.Response:
        raw = req.url.raw_path.decode().split("?")[0]
        parts = [unquote(p) for p in raw.strip("/").split("/")]
        self.calls.append(f"{req.method} {raw}")
        product = "confluence" if parts[:1] == ["wiki"] else "jira"
        if product in self.w.outages:
            return self._json(503, {"message": "Service Unavailable"})
        body = json.loads(req.content) if req.content else {}
        q = dict(req.url.params)
        try:
            if product == "confluence":
                return self._confluence(req.method, parts[1:], q, body)
            return self._jira(req.method, parts, q, body)
        except KeyError:
            return self._json(404, {"message": "Not Found"})

    # ------------------------------------------------------------------ Confluence
    def _version(self, pid) -> int:
        return 1 + sum(1 for _, _, p, nid, kind in self.w.changes if p == "confluence" and nid == pid and kind == "upsert")

    def _page(self, pid, body=False):
        p = self.w.pages[pid]
        out = {"id": pid, "status": "current", "title": p["title"], "spaceId": self._sid(p["space"]),
               "parentId": p["parent"], "parentType": "page" if p["parent"] else None,
               "version": {"number": self._version(pid), "createdAt": _iso_confluence(p["updated"])},
               "_links": {"webui": f"/spaces/{p['space']}/pages/{pid}", "base": f"{BASE}/wiki"}}
        if body:
            html = "".join(f"<p>{escape(line)}</p>" for line in p["body"].split("\n") if line.strip())
            for uid in p["links"]:
                space = self.w.pages.get(uid.split(":", 1)[1], {}).get("space", "") if uid.startswith("confluence:") else ""
                html += f'<p><a href="{escape(url_for(uid, space))}">{escape(uid.split(":", 1)[1])}</a></p>'
            out["body"] = {"storage": {"value": html, "representation": "storage"}}
        return out

    def _confluence(self, method, parts, q, body):
        w = self.w
        # v2 ---------------------------------------------------------------
        if parts[:2] == ["api", "v2"]:
            rest = parts[2:]
            if method == "GET" and rest == ["pages"]:
                ids, limit, off = sorted(w.pages), int(q.get("limit", 25)), int(q.get("cursor", 0))
                if "space-id" in q:
                    ids = [i for i in ids if self._sid(w.pages[i]["space"]) == q["space-id"]]
                if "title" in q:
                    ids = [i for i in ids if w.pages[i]["title"] == q["title"]]
                res = {"results": [self._page(i) for i in ids[off:off + limit]], "_links": {}}
                if off + limit < len(ids):
                    res["_links"]["next"] = f"/wiki/api/v2/pages?limit={limit}&cursor={off + limit}"
                return self._json(200, res)
            if method == "GET" and len(rest) == 2 and rest[0] == "pages":
                return self._json(200, self._page(rest[1], body=q.get("body-format") == "storage"))
            if method == "GET" and rest == ["spaces"]:
                keys = set(q["keys"].split(",")) if q.get("keys") else None
                res = [{"id": v, "key": k, "name": w.spaces[k]["name"]} for k, v in self.space_ids.items()
                       if k in w.spaces and (keys is None or k in keys)]
                return self._json(200, {"results": res[:int(q.get("limit", 25))]})
            if method == "GET" and len(rest) == 2 and rest[0] == "spaces":
                key = self.space_keys[rest[1]]
                return self._json(200, {"id": rest[1], "key": key, "name": w.spaces[key]["name"]})
        # v1 ---------------------------------------------------------------
        if parts[:2] == ["rest", "api"]:
            rest = parts[2:]
            if method == "GET" and rest == ["content", "search"]:
                m = re.search(r'lastmodified >= "(\d{4}-\d{2}-\d{2} \d{2}:\d{2})"', q.get("cql", ""))
                if not m:
                    return self._json(400, {"message": "unsupported CQL in fake"})
                t = _minute(m.group(1), "%Y-%m-%d %H:%M")
                hits = sorted((pid for pid, p in w.pages.items() if p["updated"] >= t), key=lambda i: w.pages[i]["updated"])
                start, limit = int(q.get("start", 0)), int(q.get("limit", 25))
                chunk = hits[start:start + limit]
                res = {"results": [{"id": i, "type": "page", "status": "current", "title": w.pages[i]["title"],
                                    "version": {"number": self._version(i), "when": _iso_confluence(w.pages[i]["updated"])}}
                                   for i in chunk], "start": start, "limit": limit, "size": len(chunk),
                       "_links": {"base": f"{BASE}/wiki", "context": "/wiki"}}
                if start + limit < len(hits):
                    from urllib.parse import urlencode
                    res["_links"]["next"] = "/rest/api/content/search?" + urlencode(
                        {"cql": q.get("cql", ""), "limit": limit, "start": start + limit, "expand": "version"})
                return self._json(200, res)
            if method == "POST" and len(rest) == 4 and rest[0] == "content" and rest[2:] == ["permission", "check"]:
                pid = rest[1]
                w.pages[pid]  # 404 if missing
                user = self.by_account.get(body.get("subject", {}).get("identifier"))
                if user is None:
                    return self._json(200, {"hasPermission": False, "errors": [{"message": {"key": "user.not.found"}}]})
                d, *_ = self.sim_conf._check(user, account_for(user, "confluence"), pid)
                if d is Decision.UNAVAILABLE:
                    return self._json(500, {"message": "internal error"})
                return self._json(200, {"hasPermission": d is Decision.ALLOWED})
            if method == "GET" and len(rest) == 5 and rest[0] == "content" and rest[2:] == ["restriction", "byOperation", "read"]:
                restrict = w.pages[rest[1]]["restrict"] or set()
                users = [{"type": "known", "accountId": account_for(USERS[p.split(':', 1)[1]], "confluence")}
                         for p in sorted(restrict) if p.startswith("user:") and p.split(":", 1)[1] in USERS]
                groups = [{"type": "group", "name": p.split(":", 1)[1]} for p in sorted(restrict) if p.startswith("group:")]
                return self._json(200, {"operation": "read", "restrictions": {
                    "user": {"results": users, "size": len(users)}, "group": {"results": groups, "size": len(groups)}}})
        r = self._confluence_write(method, parts, q, body)
        if r is not None:
            return r
        return self._json(501, {"message": f"fake Confluence has no route for {method} /{'/'.join(parts)}"})

    # ------------------------------------------------------------------ Jira
    def _issue_min(self, key):
        return {"id": str(self._jid(key)), "key": key, "fields": {"updated": _iso_jira(self.w.issues[key]["updated"])}}

    def _search(self, body):
        jql, limit = body.get("jql", ""), int(body.get("maxResults", 50))
        off = int(body.get("nextPageToken") or 0)
        m = re.match(r"project in \((.*)\) ORDER BY key ASC", jql)
        lm = re.match(r'labels = "([^"]+)"', jql)
        if lm:
            keys = sorted(k for k, i in self.w.issues.items() if lm.group(1) in i.get("labels", ()))
        elif m:
            projects = set(re.findall(r'"([^"]+)"', m.group(1)))
            keys = sorted(k for k, i in self.w.issues.items() if i["project"] in projects)
        else:
            m = re.search(r'updated >= "(\d{4}/\d{2}/\d{2} \d{2}:\d{2})"', jql)
            if not m:
                return self._json(400, {"errorMessages": ["Unbounded JQL queries are not allowed here."]})
            t = _minute(m.group(1), "%Y/%m/%d %H:%M")
            keys = sorted((k for k, i in self.w.issues.items() if i["updated"] >= t), key=lambda k: self.w.issues[k]["updated"])
        chunk = keys[off:off + limit]
        res = {"issues": [self._issue_min(k) for k in chunk], "isLast": off + limit >= len(keys)}
        if not res["isLast"]:
            res["nextPageToken"] = str(off + limit)
        return self._json(200, res)

    def _issue(self, key):
        i = self.w.issues[key]
        adf = {"type": "doc", "version": 1, "content": [
            {"type": "paragraph", "content": [{"type": "text", "text": line}]} for line in i["desc"].split("\n") if line.strip()]}
        links = [{"id": str(n), "type": {"name": "Relates"}, "outwardIssue": {"key": u.split(":", 1)[1]}}
                 for n, u in enumerate(i["links"]) if u.startswith("jira:")]
        return {"id": str(self._jid(key)), "key": key, "fields": {
            "summary": i["summary"], "status": {"name": i["status"]},
            "project": {"id": str(sorted(self.w.projects).index(i["project"]) + 10000), "key": i["project"]},
            "security": {"id": "10100", "name": i["level"]} if i["level"] else None,
            "updated": _iso_jira(i["updated"]), "description": adf, "issuelinks": links}}

    def _remotelinks(self, key):
        out = []
        for n, u in enumerate(self.w.issues[key]["links"]):
            if u.startswith("jira:"):
                continue
            space = self.w.pages.get(u.split(":", 1)[1], {}).get("space", "") if u.startswith("confluence:") else ""
            out.append({"id": 20000 + n, "object": {"url": url_for(u, space), "title": u}})
        return out

    def _jira(self, method, parts, q, body):
        if parts[:3] != ["rest", "api", "3"]:
            return self._json(501, {"message": "unknown API"})
        rest = parts[3:]
        if method == "GET" and rest == ["myself"]:
            return self._json(200, {"accountId": "atl-557058:integration-bot", "timeZone": "UTC"})
        if method == "GET" and rest == ["project", "search"]:
            vals = [{"id": str(10000 + n), "key": k, "name": self.w.projects[k]["name"]} for n, k in enumerate(sorted(self.w.projects))]
            return self._json(200, {"values": vals, "startAt": 0, "maxResults": 50, "total": len(vals), "isLast": True})
        if method == "POST" and rest == ["search", "jql"]:
            return self._search(body)
        if method == "GET" and len(rest) == 2 and rest[0] == "issue":
            return self._json(200, self._issue(rest[1]))
        if method == "GET" and len(rest) == 3 and rest[0] == "issue" and rest[2] == "remotelink":
            self.w.issues[rest[1]]
            return self._json(200, self._remotelinks(rest[1]))
        if method == "POST" and rest == ["permissions", "check"]:
            user = self.by_account.get(body.get("accountId"))
            by_id = {v: k for k, v in self.jira_ids.items()}
            out = []
            for pp in body.get("projectPermissions", []):
                granted = []
                for iid in pp.get("issues", []):
                    key = by_id.get(int(iid))
                    if key is None or key not in self.w.issues or user is None:
                        continue
                    d, *_ = self.sim_jira._check(user, account_for(user, "jira"), key)
                    if d is Decision.UNAVAILABLE:
                        return self._json(500, {"errorMessages": ["internal error"]})
                    if d is Decision.ALLOWED:
                        granted.append(int(iid))
                for perm in pp.get("permissions", []):
                    out.append({"permission": perm, "issues": granted, "projects": []})
            return self._json(200, {"projectPermissions": out, "globalPermissions": []})
        r = self._jira_write(method, rest, q, body)
        if r is not None:
            return r
        return self._json(501, {"message": f"fake Jira has no route for {method} /{'/'.join(parts)}"})


# ============================================================================ writes
# Enough of Atlassian's write API for scripts/seed_atlassian.py, so seeding can be
# tested end to end offline. Ids are server-assigned (numeric page ids, sequential
# issue keys), exactly like the real site, so the seeder's id mapping is exercised.

def _confluence_write(self, method, parts, q, body):
    from .links import uid_from_url
    from .textconv import storage_to_text
    w = self.w
    if parts == ["rest", "api", "user", "current"] and method == "GET":
        return self._json(200, {"accountId": self.bot_account, "type": "known"})
    if parts == ["rest", "api", "space"] and method == "POST":
        key = body["key"]
        if key in w.spaces:
            return self._json(400, {"message": "space exists"})
        w.spaces[key] = {"name": body.get("name", key), "view": set()}
        return self._json(200, {"id": int(self._sid(key)), "key": key, "name": w.spaces[key]["name"]})
    if len(parts) == 5 and parts[:3] == ["rest", "api", "space"] and parts[4] == "permission" and method == "POST":
        subj, op = body.get("subject", {}), body.get("operation", {})
        if op.get("key") == "read" and subj.get("type") == "group":
            w.spaces[parts[3]]["view"].add(f"group:{subj['identifier']}")
        return self._json(200, {"id": 1})

    def store(pid, b, title, space, parent):
        text, hrefs = storage_to_text(((b or {}).get("storage") or b or {}).get("value", "") if isinstance(b, dict) else "")
        links = []
        for h in hrefs:
            u = uid_from_url(h)
            if u and u not in links:
                links.append(u)
        old = w.pages.get(pid, {})
        w.pages[pid] = dict(space=space, parent=parent, restrict=old.get("restrict"), updated=time.time(),
                            title=title, body=text, links=links)

    if parts == ["api", "v2", "pages"] and method == "POST":
        space = self.space_keys[str(body["spaceId"])]
        if any(p["space"] == space and p["title"] == body["title"] for p in w.pages.values()):
            return self._json(400, {"message": "A page with this title already exists"})
        self._next_page += 1
        pid = str(self._next_page)
        store(pid, body.get("body"), body["title"], space, body.get("parentId"))
        w._changed("confluence", pid, False)
        return self._json(200, self._page(pid))
    if len(parts) == 4 and parts[:3] == ["api", "v2", "pages"] and method == "PUT":
        pid = parts[3]
        p = w.pages[pid]
        if body.get("version", {}).get("number") != self._version(pid) + 1:
            return self._json(409, {"message": "version conflict"})
        store(pid, body.get("body"), body.get("title", p["title"]), p["space"], p["parent"])
        w._changed("confluence", pid, False)
        return self._json(200, self._page(pid))
    if len(parts) == 4 and parts[:3] == ["api", "v2", "pages"] and method == "DELETE":
        w.pages[parts[3]]
        w.delete("confluence", parts[3], push=False)       # real site: moves to trash, GET is 404
        return self._json(204)
    if len(parts) == 5 and parts[:3] == ["rest", "api", "content"] and parts[4] == "restriction" and method == "PUT":
        pid = parts[3]
        w.pages[pid]
        principals = set()
        for r in body if isinstance(body, list) else []:
            if r.get("operation") != "read":
                continue
            for u in (r.get("restrictions") or {}).get("user", []):
                user = self.by_account.get(u.get("accountId"))
                principals.add(f"user:{user.username}" if user else f"account:{u.get('accountId')}")
            for g in (r.get("restrictions") or {}).get("group", []):
                principals.add(f"group:{g.get('name')}")
        w.confluence_restrict(pid, principals, push=False)
        return self._json(200, {"results": []})
    return None


def _jira_write(self, method, rest, q, body):
    from .textconv import adf_to_text
    from .links import uid_from_url
    w = self.w
    if rest == ["mypermissions"] and method == "GET":
        wanted = [x for x in q.get("permissions", "").split(",") if x]
        return self._json(200, {"permissions": {p: {"key": p, "havePermission": p not in self.bot_lacks}
                                                for p in wanted}})
    if rest == ["group"] and method == "POST":
        if body["name"] in self.groups:
            return self._json(400, {"errorMessages": ["group exists"]})
        self.groups[body["name"]] = set()
        return self._json(201, {"name": body["name"]})
    if rest == ["group", "user"] and method == "POST":
        self.groups.setdefault(q.get("groupname", ""), set()).add(body.get("accountId"))
        return self._json(201, {})
    if len(rest) == 2 and rest[0] == "project" and method == "GET" and rest[1] != "search":
        if rest[1] not in w.projects:
            return self._json(404, {"errorMessages": ["No project could be found"]})
        return self._json(200, {"key": rest[1], "name": w.projects[rest[1]]["name"]})
    if rest == ["project"] and method == "POST":
        w.projects[body["key"]] = {"name": body["name"], "roles": {"developers": set()}, "browse": {"developers"}}
        return self._json(201, {"id": 10000 + len(w.projects), "key": body["key"]})
    if rest == ["issue"] and method == "POST":
        f = body["fields"]
        proj = f["project"]["key"]
        n = 1 + max([int(k.split("-")[1]) for k in w.issues if k.split("-")[0] == proj] + [0])
        key = f"{proj}-{n}"
        desc, hrefs = adf_to_text(f.get("description"))
        w.issues[key] = dict(project=proj, level=None, status="To Do", updated=time.time(), summary=f["summary"],
                             desc=desc, links=[u for u in map(uid_from_url, hrefs) if u], labels=list(f.get("labels", [])))
        w._changed("jira", key, False)
        return self._json(201, {"id": str(self._jid(key)), "key": key})
    if len(rest) == 3 and rest[0] == "issue" and rest[2] == "transitions":
        issue = w.issues[rest[1]]
        names = ["To Do", "Open", "In Progress", "Blocked", "Done"]
        if method == "GET":
            return self._json(200, {"transitions": [{"id": str(i), "name": n, "to": {"name": n}} for i, n in enumerate(names)]})
        issue["status"] = names[int(body["transition"]["id"])]
        issue["updated"] = time.time()
        w._changed("jira", rest[1], False)
        return self._json(204)
    if len(rest) == 2 and rest[0] == "issue" and method == "PUT":
        issue = w.issues[rest[1]]
        f = body.get("fields", {})
        if "security" in f:
            name = (f["security"] or {}).get("name")
            if name and name not in w.security_levels:
                return self._json(400, {"errors": {"security": "Security level not found"}})
            issue["level"] = name
        if "description" in f:
            issue["desc"], _ = adf_to_text(f["description"])
        if "summary" in f:
            issue["summary"] = f["summary"]
        issue["updated"] = time.time()
        w._changed("jira", rest[1], False)
        return self._json(204)
    if len(rest) == 2 and rest[0] == "issue" and method == "DELETE":
        w.issues[rest[1]]
        w.delete("jira", rest[1], push=False)
        return self._json(204)
    if rest == ["issueLink"] and method == "POST":
        out, inn = body["outwardIssue"]["key"], body["inwardIssue"]["key"]
        w.issues[inn]
        if f"jira:{inn}" not in w.issues[out]["links"]:
            w.issues[out]["links"].append(f"jira:{inn}")
        return self._json(201)
    if len(rest) == 3 and rest[0] == "issue" and rest[2] == "remotelink" and method == "POST":
        u = uid_from_url(body["object"]["url"])
        issue = w.issues[rest[1]]
        if u and u not in issue["links"]:
            issue["links"].append(u)
        return self._json(201, {"id": 20000 + len(issue["links"])})
    return None


FakeAtlassian._confluence_write = _confluence_write
FakeAtlassian._jira_write = _jira_write
