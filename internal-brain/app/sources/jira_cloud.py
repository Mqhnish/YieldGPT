"""Jira Cloud connector (real REST API v3). Owner: Member 1.

Endpoints used
  GET  /rest/api/3/project/search                      project keys (bounds the listing JQL)
  POST /rest/api/3/search/jql                          enhanced search, nextPageToken pagination
  GET  /rest/api/3/issue/{key}                         issue fields (description is ADF)
  GET  /rest/api/3/issue/{key}/remotelink              links out to Confluence / Slack / Drive
  POST /rest/api/3/permissions/check                   bulk permission check for another accountId

Authorization decision: we ask Jira whether the ASKER's accountId has BROWSE_PROJECTS
on this specific issue. Jira evaluates the project permission scheme and the issue
security level itself. Checking another user's permissions needs the integration
account to have "Administer Jira". See docs/ATLASSIAN_SETUP.md.

VERIFY ON A LIVE SITE: that the bulk check excludes issues hidden by an issue security
level. The live conformance run must include a security-level issue (our PAY-110 case).
If it doesn't, switch _check to the fallback described in the setup guide.

Notes
  - The new search endpoint rejects unbounded JQL, so listing is "project in (...)".
  - JQL dates are minute precision in the API user's timezone: set the integration
    account's timezone to UTC (the polling overlap window absorbs the rest).
  - Deleted issues never appear in search: found by reconciliation (cloud_polling.py).
"""
from __future__ import annotations

import hashlib
import json
from datetime import datetime, timezone
from urllib.parse import quote

from .. import config
from .atlassian_client import AtlassianClient, NotFound
from .base import Decision, SourceDoc
from .cloud_polling import CloudPollingConnector
from .links import dedupe, uid_from_url
from .textconv import adf_to_text

FIELDS = ["summary", "status", "project", "security", "updated", "description", "issuelinks", "comment"]


def _ts(s: str) -> float:
    return datetime.strptime(s, "%Y-%m-%dT%H:%M:%S.%f%z").timestamp()


def _jql_time(ts: float) -> str:
    return datetime.fromtimestamp(max(ts, 0), timezone.utc).strftime("%Y/%m/%d %H:%M")


class JiraCloudConnector(CloudPollingConnector):
    platform = "jira"

    def __init__(self, client: AtlassianClient):
        super().__init__()
        self.api = client
        self.tenant = client.host
        self._ids: dict[str, str] = {}   # issue key -> numeric id (stable per issue)
        self.restricted_comments_skipped: dict[str, int] = {}

    # ---- search helpers ------------------------------------------------------------
    def _projects(self) -> list[str]:
        keys, start = [], 0
        while True:
            d = self.api.get("/rest/api/3/project/search", startAt=start, maxResults=50)
            vals = d.get("values", [])
            keys += [p["key"] for p in vals]
            # isLast is authoritative when present; otherwise fall back to total, then to "short page"
            last = d["isLast"] if "isLast" in d else (start + len(vals) >= d["total"] if "total" in d else len(vals) < 50)
            if last or not vals:
                return keys
            start += len(vals)

    def _search(self, jql: str, page_size: int, token: str | None, fields: list[str]):
        body = {"jql": jql, "maxResults": page_size, "fields": fields}
        if token:
            body["nextPageToken"] = token
        d = self.api.post("/rest/api/3/search/jql", body)
        for i in d.get("issues", []):
            self._ids[i["key"]] = str(i["id"])
        # A nextPageToken means there's more, whatever else the response says. Treating a missing
        # isLast as "last page" silently truncates, and reconciliation would then delete the rest.
        nxt = d.get("nextPageToken") if d.get("isLast") is not True else None
        return d.get("issues", []), nxt

    # ---- listing -----------------------------------------------------------------------
    def list_page(self, page_token=None, page_size=50):
        if page_token:
            t = json.loads(page_token)
            jql, npt = t["jql"], t["npt"]
        else:
            projects = self._projects()
            if not projects:
                return [], None
            jql = "project in ({}) ORDER BY key ASC".format(", ".join(f'"{p}"' for p in projects))
            npt = None
        issues, nxt = self._search(jql, page_size, npt, ["updated"])
        keys = [i["key"] for i in issues]
        self._known |= set(keys)
        return keys, (json.dumps({"jql": jql, "npt": nxt}) if nxt else None)

    def _all_ids(self):
        ids, token = set(), None
        while True:
            page, token = self.list_page(token, 100)
            ids |= set(page)
            if not token:
                return ids

    def _updated_since(self, ts):
        jql = f'updated >= "{_jql_time(ts)}" ORDER BY updated ASC'
        out, token = [], None
        while True:
            issues, token = self._search(jql, 100, token, ["updated"])
            out += [(i["key"], i["fields"]["updated"], _ts(i["fields"]["updated"])) for i in issues]
            if not token:
                return out

    # ---- content -------------------------------------------------------------------------
    def fetch(self, key):
        try:
            i = self.api.get(f"/rest/api/3/issue/{quote(key, safe='')}", fields=",".join(FIELDS))
        except NotFound:
            return None
        self._ids[i["key"]] = str(i["id"])
        f = i["fields"]
        desc, hrefs = adf_to_text(f.get("description"))
        try:
            remote = self.api.get(f"/rest/api/3/issue/{quote(key, safe='')}/remotelink") or []
        except NotFound:
            remote = []
        links = []
        for l in f.get("issuelinks", []) or []:
            other = l.get("outwardIssue") or l.get("inwardIssue")
            if other:
                links.append(f"jira:{other['key']}")
        links += [uid_from_url(r.get("object", {}).get("url", "")) for r in remote]
        links += [uid_from_url(h) for h in hrefs]
        # Comments: only those visible to everyone who can see the issue. A comment with
        # `visibility` (restricted to a role or group) has its OWN permission, narrower than the
        # issue's, so indexing it into the issue text would leak it. Skipped, never flattened.
        comment_lines, restricted = [], 0
        for cm in ((f.get("comment") or {}).get("comments") or []):
            if cm.get("visibility"):
                restricted += 1
                continue
            body, chrefs = adf_to_text(cm.get("body"))
            hrefs += chrefs
            if body:
                who = (cm.get("author") or {}).get("displayName", "")
                comment_lines.append(f"Comment{' by ' + who if who else ''}: {body}")
        self.restricted_comments_skipped[key] = restricted
        status = (f.get("status") or {}).get("name", "")
        text = f"{key} [{status}] {f.get('summary', '')}. {desc}".strip()
        if comment_lines:
            text += "\n" + "\n".join(comment_lines)
        return SourceDoc(self.uid(key), self.platform, self.tenant, key, f["project"]["key"],
                         f"{key}: {f.get('summary', '')}", text, f"{self.api.site}/browse/{key}",
                         # `updated` alone isn't enough: two edits in the same millisecond share it.
                         version=f'{f["updated"]}#{hashlib.sha256(text.encode()).hexdigest()[:12]}',
                         updated_at=_ts(f["updated"]),
                         links=dedupe(u for u in links if u and u != self.uid(key)))

    def acl_hint(self, key):
        """Prefilter disabled for Jira ("anyone"): mapping permission schemes and security
        levels to principals needs admin-only APIs. Safe, because check() decides (R5)."""
        return {"anyone"}

    # ---- authorization -----------------------------------------------------------------
    def _issue_id(self, key) -> str | None:
        if key not in self._ids:
            try:
                i = self.api.get(f"/rest/api/3/issue/{quote(key, safe='')}", _timeout=config.CHECK_TIMEOUT_S, fields="project")
            except NotFound:
                return None
            self._ids[key] = str(i["id"])
        return self._ids[key]

    supports_batch = True

    def _check(self, user, account, key):
        return self._check_batch(user, account, [key])[key]

    def _check_batch(self, user, account, keys):
        """One bulk call for every issue in the question (instead of one call per issue)."""
        out, ids = {}, {}
        for k in keys:
            iid = self._issue_id(k)
            if iid is None:
                out[k] = (Decision.DENIED, "not_found", "issue does not exist", "")
            else:
                ids[k] = iid
        if not ids:
            return out
        r = self.api.post("/rest/api/3/permissions/check", {
            "accountId": account,
            "projectPermissions": [{"permissions": ["BROWSE_PROJECTS"], "issues": [int(i) for i in ids.values()]}],
        }, _timeout=config.CHECK_TIMEOUT_S)
        granted = {str(x) for pp in r.get("projectPermissions", []) if pp.get("permission") == "BROWSE_PROJECTS"
                   for x in pp.get("issues", [])}
        for k, iid in ids.items():
            out[k] = ((Decision.ALLOWED, "jira_browse_allowed", "Jira bulk check: BROWSE_PROJECTS on issue", "")
                      if iid in granted else
                      (Decision.DENIED, "jira_browse_denied",
                       "Jira bulk check: no BROWSE_PROJECTS on issue (project scheme or security level)", ""))
        return out

    def ping(self):
        self.api.get("/rest/api/3/myself")
