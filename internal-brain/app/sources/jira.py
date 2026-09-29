"""Jira connector. Owner: Member 1.

Native model: Browse Projects via the project's permission scheme (roles or
groups) AND, if the issue has a security level, membership of that level.

Production notes
- Use the "get my permissions" / permission-check endpoints as the asker (or an
  admin-scoped bulk permission check) rather than inferring from group names.
- Issue security level changes arrive as issue_updated webhooks: emit kind="acl".
"""
from .base import Decision, SourceDoc
from .sim import SimulatedConnector


class JiraConnector(SimulatedConnector):
    platform = "jira"

    def _ids(self):
        return list(self.w.issues)

    def fetch(self, key):
        self.w.guard(self.platform)
        i = self.w.issues.get(key)
        if not i:
            return None
        text = f"{key} [{i['status']}] {i['summary']}. {i['desc']}"
        return SourceDoc(self.uid(key), self.platform, self.tenant, key, i["project"], f"{key}: {i['summary']}", text,
                         f"https://companya.atlassian.net/browse/{key}", version=f"{i['updated']:.6f}",
                         updated_at=i["updated"], links=list(i["links"]))

    def _browsers(self, project):
        proj = self.w.projects[project]
        return set().union(*(proj["roles"].get(r, set()) for r in proj["browse"]))

    def acl_hint(self, key):
        self.w.guard(self.platform)
        i = self.w.issues[key]
        return set(self.w.security_levels[i["level"]]) if i["level"] else self._browsers(i["project"])

    def _check(self, user, account, key):
        self.w.guard(self.platform)
        i = self.w.issues.get(key)
        if not i:
            return Decision.DENIED, "not_found", "issue does not exist", ""
        ver = f"{i['updated']:.6f}"
        if not self._matches(user, self._browsers(i["project"])):
            return Decision.DENIED, "browse_project_missing", f"no Browse Projects on {i['project']}", ver
        if i["level"]:
            members = self.w.security_levels.get(i["level"])
            if members is None:
                # unknown level = unknown permission state: fail closed (R1)
                return Decision.UNAVAILABLE, "unknown_security_level", f"security level '{i['level']}' not resolvable", ver
            if not self._matches(user, members):
                return Decision.DENIED, "issue_security_level", f"not in security level '{i['level']}'", ver
        return Decision.ALLOWED, "browse_via_project_role", f"browse on {i['project']}", ver
