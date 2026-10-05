"""Confluence Cloud connector (real REST API). Owner: Member 1.

Endpoints used
  GET  /wiki/api/v2/pages?limit=&cursor=                     list pages (cursor pagination via _links.next)
  GET  /wiki/api/v2/pages/{id}?body-format=storage           page + body
  GET  /wiki/api/v2/spaces/{id}                              space id -> key (cached)
  GET  /wiki/rest/api/content/search?cql=...                 changed pages (CQL lastmodified)
  POST /wiki/rest/api/content/{id}/permission/check          can THIS user read it? (native rule engine)
  GET  /wiki/rest/api/content/{id}/restriction/byOperation/read   page read restrictions (prefilter hint)

Authorization decision: we don't re-implement space permissions or restriction
inheritance. We ask Confluence itself, for the asker's accountId, every time.
The integration account must be allowed to check OTHER users' permissions
(site/Confluence admin). See docs/ATLASSIAN_SETUP.md.

Not covered by polling: restriction and space-permission changes don't bump
`lastmodified`, so the prefilter hint can go stale. That is safe (the live check
decides) and is exactly why the live check exists.
"""
from __future__ import annotations

from datetime import datetime, timezone
from urllib.parse import quote

from .. import config
from ..identity import USERS, account_for
from .atlassian_client import AtlassianClient, NotFound
from .base import Decision, SourceDoc, SourceUnavailable
from .cloud_polling import CloudPollingConnector
from .links import dedupe, uid_from_url
from .textconv import storage_to_text


def _ts(iso: str) -> float:
    return datetime.fromisoformat(iso.replace("Z", "+00:00")).timestamp()


def _cql_time(ts: float) -> str:
    return datetime.fromtimestamp(max(ts, 0), timezone.utc).strftime("%Y-%m-%d %H:%M")


class ConfluenceCloudConnector(CloudPollingConnector):
    platform = "confluence"

    def __init__(self, client: AtlassianClient):
        super().__init__()
        self.api = client
        self.tenant = client.host
        self._space_keys: dict[str, str] = {}
        self._by_account = {account_for(u, "confluence"): u.username for u in USERS.values() if account_for(u, "confluence")}

    # ---- listing -------------------------------------------------------------
    def list_page(self, page_token=None, page_size=50):
        data = self.api.get(page_token) if page_token else self.api.get("/wiki/api/v2/pages", limit=page_size)
        ids = [p["id"] for p in data.get("results", [])]
        self._known |= set(ids)
        return ids, (data.get("_links") or {}).get("next")

    def _all_ids(self) -> set[str]:
        ids, token = set(), None
        while True:
            page, token = self.list_page(token, 250)
            ids |= set(page)
            if not token:
                return ids

    def _updated_since(self, ts):
        cql = f'type=page and lastmodified >= "{_cql_time(ts)}" order by lastmodified asc'
        out, data = [], self.api.get("/wiki/rest/api/content/search", cql=cql, limit=100, expand="version")
        for _ in range(10_000):  # hard stop against a server that never ends pagination
            for r in data.get("results", []):
                out.append((r["id"], str(r["version"]["number"]), _ts(r["version"]["when"])))
            links = data.get("_links") or {}
            if not links.get("next"):
                return out
            # v1 "next" links are relative to the /wiki context (cursor pagination)
            data = self.api.get(links.get("context", "/wiki") + links["next"])
        raise SourceUnavailable(f"{self.tenant}: search pagination did not terminate")

    # ---- content ---------------------------------------------------------------
    def _space_key(self, space_id: str) -> str:
        if space_id not in self._space_keys:
            self._space_keys[space_id] = self.api.get(f"/wiki/api/v2/spaces/{quote(str(space_id), safe='')}")["key"]
        return self._space_keys[space_id]

    def fetch(self, pid):
        try:
            p = self.api.get(f"/wiki/api/v2/pages/{quote(pid, safe='')}", **{"body-format": "storage"})
        except NotFound:
            return None
        if p.get("status") not in (None, "current"):
            return None  # trashed / draft / archived: not served
        text, hrefs = storage_to_text(((p.get("body") or {}).get("storage") or {}).get("value", ""))
        links = (p.get("_links") or {})
        url = links.get("base", f"{self.api.site}/wiki") + links.get("webui", "")
        space = self._space_key(p["spaceId"])
        return SourceDoc(self.uid(pid), self.platform, self.tenant, pid, space, p["title"], text, url,
                         version=str(p["version"]["number"]), updated_at=_ts(p["version"]["createdAt"]),
                         parent=str(p.get("parentId") or ""),
                         links=dedupe(u for u in map(uid_from_url, hrefs) if u and u != self.uid(pid)))

    def acl_hint(self, pid):
        """Page's own read restrictions if it has any, else "anyone" (space permissions aren't
        mapped yet). Always a SUPERSET of who check() allows (contract R5)."""
        r = self.api.get(f"/wiki/rest/api/content/{quote(pid, safe='')}/restriction/byOperation/read")
        rs = r.get("restrictions") or {}
        users = [u.get("accountId") for u in (rs.get("user") or {}).get("results", [])]
        groups = [g.get("name") for g in (rs.get("group") or {}).get("results", [])]
        if not users and not groups:
            return {"anyone"}
        return ({f"user:{self._by_account.get(a, 'account:' + str(a))}" for a in users}
                | {f"group:{g}" for g in groups})

    # ---- authorization -----------------------------------------------------------
    def _check(self, user, account, pid):
        try:
            r = self.api.post(f"/wiki/rest/api/content/{quote(pid, safe='')}/permission/check",
                              {"subject": {"type": "user", "identifier": account}, "operation": "read"},
                              _timeout=config.CHECK_TIMEOUT_S)
        except NotFound:
            return Decision.DENIED, "not_found", "page does not exist", ""
        if r.get("hasPermission") is True:
            # Report the page version at check time, so the pipeline's after-read check catches an
            # edit that landed between its read and this check (resource_version != fetched version).
            try:
                p = self.api.get(f"/wiki/api/v2/pages/{quote(pid, safe='')}", _timeout=config.CHECK_TIMEOUT_S)
            except NotFound:
                return Decision.DENIED, "not_found", "page does not exist", ""
            if p.get("status") not in (None, "current"):
                return Decision.DENIED, "not_found", "page is not current", ""
            return (Decision.ALLOWED, "confluence_read_allowed", "Confluence permission check: read allowed",
                    str(p["version"]["number"]))
        if r.get("hasPermission") is False:
            errs = "; ".join(e.get("message", {}).get("key", "") if isinstance(e.get("message"), dict)
                             else str(e.get("message", "")) for e in r.get("errors", []) or [])
            return Decision.DENIED, "confluence_read_denied", f"Confluence permission check: read denied {errs}".strip(), ""
        return Decision.UNAVAILABLE, "unexpected_response", "permission check returned no decision", ""

    def ping(self):
        self.api.get("/wiki/api/v2/spaces", limit=1)

