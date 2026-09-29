"""Confluence connector. Owner: Member 1.

Native model: space VIEW permission AND every page restriction on the page and
its ancestors (restrictions inherit downwards).

Production notes
- Content permission check for another user needs extra privileges on the calling
  identity (see Atlassian content-permissions API). Validate the integration
  identity early.
- Space permissions are not in page webhooks. Poll space permissions or subscribe
  to space events and emit kind="acl" changes for affected pages.
"""
from .base import Decision, SourceDoc
from .sim import SimulatedConnector


class ConfluenceConnector(SimulatedConnector):
    platform = "confluence"

    def _ids(self):
        return list(self.w.pages)

    def _restrictions(self, pid):
        chain = []
        while pid:
            page = self.w.pages[pid]
            if page["restrict"]:
                chain.append((pid, page["restrict"]))
            pid = page["parent"]
        return chain

    def fetch(self, pid):
        self.w.guard(self.platform)
        p = self.w.pages.get(pid)
        if not p:
            return None
        return SourceDoc(self.uid(pid), self.platform, self.tenant, pid, p["space"], p["title"], p["body"],
                         f"https://companya.atlassian.net/wiki/spaces/{p['space']}/pages/{pid}",
                         version=f"{p['updated']:.6f}", updated_at=p["updated"], parent=p["parent"] or "",
                         links=list(p["links"]))

    def acl_hint(self, pid):
        self.w.guard(self.platform)
        page = self.w.pages[pid]
        restr = self._restrictions(pid)
        return set(restr[0][1]) if restr else set(self.w.spaces[page["space"]]["view"])

    def _check(self, user, account, pid):
        self.w.guard(self.platform)
        page = self.w.pages.get(pid)
        if not page:
            return Decision.DENIED, "not_found", "page does not exist", ""
        ver = f"{page['updated']:.6f}"
        if not self._matches(user, self.w.spaces[page["space"]]["view"]):
            return Decision.DENIED, "space_view_missing", f"no view permission on space '{page['space']}'", ver
        for anc, allowed in self._restrictions(pid):
            if not self._matches(user, allowed):
                code = "page_restricted" if anc == pid else "ancestor_restricted"
                return Decision.DENIED, code, f"view restriction on {anc}", ver
        return Decision.ALLOWED, "space_view_and_restrictions_ok", f"space '{page['space']}' view, restrictions pass", ver
