"""Google Drive connector. Owner: Member 3.

Native model (simulated; mirrors Drive API v3 semantics, see docs/MEMBER3.md):
  Identity     The asker's linked Drive account email. A domain share matches only when
               that account's email domain is the company domain; the corporate
               "employee" flag is not consulted.
  Principals   user:<name>, group:<name>, domain, anyone, plus an optional file owner.
  Inheritance  A file's own permissions, then every ancestor folder, then membership of
               the shared drive that the root folder belongs to (w.shared_drives).
               My Drive files (no folder) have only their own permissions/owner.
  Limited      A folder with limited=True is a "limited-access folder": inheritance stops
               there. People who only reach it through a parent or the shared drive may
               see it in listings (metadata) but are DENIED its contents.
  Trash        A trashed file is gone for the Brain: fetch() -> None, excluded from the
               crawl, check() DENIED "trashed"; it arrives as change kind "delete".
  Moves        Changing a file's folder changes inherited access; it arrives as kind "acl".

Real API mapping: permissions.list (supportsAllDrives, inheritedPermissionsDisabled),
drives.get membership, files.get(fields=parents,trashed), changes.list with
includeItemsFromAllDrives + includeRemoved. The asker's access is evaluated from these
permissions for the asker's account, never from the ingestion identity's ability to read.
"""
from ..identity import principals as corporate_principals
from .base import Decision, SourceDoc
from .sim import SimulatedConnector

DOMAIN = "companya.example"


class DriveConnector(SimulatedConnector):
    platform = "gdrive"

    def _ids(self):
        return [fid for fid, f in self.w.files.items() if not f.get("trashed")]

    def _live(self, fid):
        f = self.w.files.get(fid)
        return f if f and not f.get("trashed") else None

    def _grants(self, fid) -> tuple[dict, dict]:
        """(content, metadata_only): principals that may open the file, and principals
        that only reach it through a parent above a limited-access folder."""
        f = self.w.files[fid]
        content, above = dict(f["shares"]), {}
        if f.get("owner"):
            content[f["owner"]] = "owner"
        target, folder, root = content, f["folder"], None
        while folder:
            d = self.w.folders[folder]
            target.update(d["shares"])
            if d.get("limited"):
                target = above
            root, folder = folder, d["parent"]
        drive = self.w.folders[root].get("drive") if root else None
        if drive:
            target.update(getattr(self.w, "shared_drives", {}).get(drive, {}).get("members", {}))
        return content, above

    def fetch(self, fid):
        self.w.guard(self.platform)
        f = self._live(fid)
        if not f:
            return None
        return SourceDoc(self.uid(fid), self.platform, self.tenant, fid, f["folder"] or "personal", f["name"], f["text"],
                         f"https://drive.google.com/file/d/{fid}", version=f"{f['updated']:.6f}",
                         updated_at=f["updated"], parent=f["folder"] or "", links=list(f["links"]))

    def acl_hint(self, fid):
        self.w.guard(self.platform)
        return set(self._grants(fid)[0]) if self._live(fid) else set()

    def _check(self, user, account, fid):
        self.w.guard(self.platform)
        f = self.w.files.get(fid)
        if not f:
            return Decision.DENIED, "not_found", "file does not exist", ""
        ver = f"{f['updated']:.6f}"
        if f.get("trashed"):
            return Decision.DENIED, "trashed", "file is in the trash", ver
        mine = self._drive_principals(user, account)
        content, above = self._grants(fid)
        match = sorted(mine & set(content))
        if match:
            return Decision.ALLOWED, "shared", f"shared via {match[0]} ({content[match[0]]})", ver
        if mine & set(above):
            return (Decision.DENIED, "limited_access_folder",
                    "reachable only through a parent of a limited-access folder: metadata visible, contents denied", ver)
        return Decision.DENIED, "not_shared", "not shared with user, their groups, or domain", ver

    @staticmethod
    def _drive_principals(user, account):
        found = corporate_principals(user) - {"domain"}
        if account.rpartition("@")[2].lower() == DOMAIN:
            found.add("domain")
        return found
