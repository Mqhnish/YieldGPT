"""Google Drive connector. Owner: Member 3 (moved from the shared file; logic unchanged).

Native model (simulated scope): file shares + inherited folder shares, with
user / group / domain / anyone principals.

TODO(Member 3), per docs/HANDOFF_member1_to_member3.md:
- limited-access folders (metadata visible, contents not) instead of a plain union
- shared drives vs My Drive, permission roles, deletion + trash via changes.list
- must pass tests/contract (add Drive-specific cases to tests/contract/specs.py)
"""
from .base import Decision, SourceDoc
from .sim import SimulatedConnector


class DriveConnector(SimulatedConnector):
    platform = "gdrive"

    def _ids(self):
        return list(self.w.files)

    def _effective_shares(self, fid):
        f = self.w.files[fid]
        shares = dict(f["shares"])
        folder = f["folder"]
        while folder:
            shares.update(self.w.folders[folder]["shares"])
            folder = self.w.folders[folder]["parent"]
        return shares

    def fetch(self, fid):
        self.w.guard(self.platform)
        f = self.w.files.get(fid)
        if not f:
            return None
        return SourceDoc(self.uid(fid), self.platform, self.tenant, fid, f["folder"] or "personal", f["name"], f["text"],
                         f"https://drive.google.com/file/d/{fid}", version=f"{f['updated']:.6f}",
                         updated_at=f["updated"], parent=f["folder"] or "", links=list(f["links"]))

    def acl_hint(self, fid):
        self.w.guard(self.platform)
        return set(self._effective_shares(fid))

    def _check(self, user, account, fid):
        self.w.guard(self.platform)
        if fid not in self.w.files:
            return Decision.DENIED, "not_found", "file does not exist", ""
        ver = f"{self.w.files[fid]['updated']:.6f}"
        shares = self._effective_shares(fid)
        match = sorted(self._principals_of(user) & set(shares))
        if not match:
            return Decision.DENIED, "not_shared", "not shared with user, their groups, or domain", ver
        return Decision.ALLOWED, "shared", f"shared via {match[0]} ({shares[match[0]]})", ver

    @staticmethod
    def _principals_of(user):
        from ..identity import principals
        return principals(user)
