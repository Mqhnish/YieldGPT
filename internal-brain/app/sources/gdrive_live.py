"""Live Google Drive (API v3) connector. Owner: Member 3.

Same trust split as the live Slack connector:
  * The INGESTION token only discovers and indexes content (list, changes, fetch, acl_hint).
  * Every permission check and user-visible read uses the ASKER's own delegated token,
    verified with about.get to belong to the linked Drive account (contract rule R2).
    Drive itself answers, so shared drives, limited-access folders, domain shares and
    group membership are never re-implemented here.

Errors surface only as fixed codes: no response body, URL or token reaches an exception (R12).
Tokens are short-lived OAuth access tokens supplied by the caller (env or resolver);
minting them from a service-account key is deliberately out of scope here.
"""
from __future__ import annotations

import re
import time
from collections.abc import Callable
from datetime import datetime
from urllib.parse import quote

import httpx

from ..identity import User
from .base import Change, ChangePage, Connector, Decision, SourceDoc, SourceUnavailable

API = "https://www.googleapis.com/drive/v3"
ID = re.compile(r"[A-Za-z0-9_-]{6,128}")
FOLDER = "application/vnd.google-apps.folder"
EXPORT = {"application/vnd.google-apps.document": "text/plain",
          "application/vnd.google-apps.presentation": "text/plain",
          "application/vnd.google-apps.spreadsheet": "text/csv"}
INDEXABLE = ("(" + " or ".join(f"mimeType='{m}'" for m in EXPORT) + " or mimeType contains 'text/')")
META = "id,name,mimeType,trashed,modifiedTime,version,parents,webViewLink,capabilities(canDownload)"
SHARED = {"supportsAllDrives": "true", "includeItemsFromAllDrives": "true"}
_RATE = {"rateLimitExceeded", "userRateLimitExceeded", "quotaExceeded", "sharingRateLimitExceeded",
         "backendError", "internalError"}


class DriveAPIError(SourceUnavailable):
    def __init__(self, code: str):
        self.code = code
        super().__init__(f"Drive API unavailable ({code})")


class _Gone(Exception):
    """The platform answered: not found or not permitted for this credential."""


class DriveLiveConnector(Connector):
    platform = "gdrive"

    def __init__(self, domain: str, ingestion_token: Callable[[], str] | str,
                 user_token_resolver: Callable[[str], str | None], *, client: httpx.Client | None = None,
                 page_size: int = 100, max_pages: int = 1000, request_timeout: float = 2.0,
                 max_chars: int = 200_000):
        if not re.fullmatch(r"[a-z0-9.-]+\.[a-z]{2,}", domain):
            raise ValueError("Drive tenant must be the company domain")
        if not ingestion_token or not callable(user_token_resolver):
            raise ValueError("Drive ingestion credential and user credential resolver required")
        if not 1 <= page_size <= 1000 or not 1 <= max_pages <= 10000 or not 0 < request_timeout <= 10:
            raise ValueError("Invalid Drive limits")
        self.tenant = domain
        self._ingestion = ingestion_token if callable(ingestion_token) else (lambda: ingestion_token)
        self._resolve_token = user_token_resolver
        self.client = client or httpx.Client(follow_redirects=False)
        self.page_size, self.max_pages, self.timeout, self.max_chars = page_size, max_pages, request_timeout, max_chars

    # ---------------------------------------------------------------- HTTP
    def _get(self, token: str, path: str, params: dict | None = None, *, text: bool = False):
        """200 -> JSON (or text). 404 and non-rate-limit 403 -> _Gone. Everything else raises DriveAPIError."""
        # ponytail: no retries (R11: a slow answer is no answer); the sync poll loop retries on its next tick
        try:
            r = self.client.get(f"{API}/{path}", params=params or {}, headers={"Authorization": f"Bearer {token}"},
                                timeout=self.timeout, follow_redirects=False)
        except Exception:
            raise DriveAPIError("transport") from None
        if r.status_code == 200:
            if text:
                return r.text
            try:
                body = r.json()
            except Exception:
                raise DriveAPIError("invalid_response") from None
            if not isinstance(body, dict):
                raise DriveAPIError("invalid_response")
            return body
        try:
            reason = r.json()["error"]["errors"][0]["reason"]
        except Exception:  # noqa: BLE001
            reason = ""
        if r.status_code == 401:
            raise DriveAPIError("invalid_auth")
        if r.status_code == 404 or (r.status_code == 403 and reason not in _RATE):
            raise _Gone()
        raise DriveAPIError("rate_limited" if r.status_code in (403, 429) else f"http_{r.status_code}")

    def _token(self, fn) -> str:
        try:
            token = fn()
        except Exception:
            raise DriveAPIError("credential") from None
        if not token:
            raise DriveAPIError("credential")
        return token

    def _user_token(self, account: str) -> str:
        token = self._token(lambda: self._resolve_token(account))
        try:
            who = self._get(token, "about", {"fields": "user(emailAddress)"})
        except _Gone:
            raise DriveAPIError("invalid_auth") from None
        if str((who.get("user") or {}).get("emailAddress", "")).lower() != account.lower():
            raise DriveAPIError("identity_mismatch")
        return token

    # ---------------------------------------------------------------- one file
    def _meta(self, token: str, fid: str) -> dict | None:
        """Metadata the credential may see, or None (missing, trashed, or not permitted)."""
        if not ID.fullmatch(fid or ""):
            return None
        try:
            m = self._get(token, f"files/{quote(fid, safe='')}", {"fields": META, "supportsAllDrives": "true"})
        except _Gone:
            return None
        if m.get("trashed") or m.get("mimeType") == FOLDER or m.get("id") != fid:
            return None
        return m

    def _readable(self, m: dict) -> bool:
        return bool((m.get("capabilities") or {}).get("canDownload", False))

    def _doc(self, token: str, fid: str) -> SourceDoc | None:
        m = self._meta(token, fid)
        if not m or not self._readable(m):
            return None
        mime, path = m.get("mimeType", ""), f"files/{quote(fid, safe='')}"
        try:
            if mime in EXPORT:
                text = self._get(token, f"{path}/export", {"mimeType": EXPORT[mime]}, text=True)
            elif mime.startswith("text/"):
                text = self._get(token, path, {"alt": "media", "supportsAllDrives": "true"}, text=True)
            else:
                return None
        except _Gone:
            return None
        link = str(m.get("webViewLink", ""))
        url = link if link.startswith("https://") else f"https://drive.google.com/file/d/{fid}/view"
        try:
            updated = datetime.fromisoformat(str(m["modifiedTime"]).replace("Z", "+00:00")).timestamp()
        except (KeyError, ValueError):
            raise DriveAPIError("invalid_response") from None
        parent = (m.get("parents") or [""])[0]
        # ponytail: truncates very large files; chunk into passages if long Drive docs matter
        return SourceDoc(self.uid(fid), self.platform, self.tenant, fid, parent or "personal", str(m.get("name", fid)),
                         text[:self.max_chars], url, str(m.get("version") or m["modifiedTime"]), updated, parent=parent)

    def fetch(self, native_id):
        return self._doc(self._token(self._ingestion), native_id)

    def read_authorized(self, user: User, native_id: str) -> SourceDoc | None:
        """Re-read as the asker right before model input. Denied or absent -> None; outage raises."""
        from ..identity import account_for
        account = account_for(user, self.platform)
        return self._doc(self._user_token(account), native_id) if account else None

    # ---------------------------------------------------------------- authorization
    def _check(self, user, account, native_id):
        token = self._user_token(account)
        if not ID.fullmatch(native_id or ""):
            return Decision.DENIED, "not_found", "malformed file id", ""
        try:
            m = self._get(token, f"files/{quote(native_id, safe='')}", {"fields": META, "supportsAllDrives": "true"})
        except _Gone:
            return Decision.DENIED, "not_found", "file missing or not visible to the mapped account", ""
        ver = str(m.get("version") or m.get("modifiedTime", ""))
        if m.get("trashed"):
            return Decision.DENIED, "trashed", "file is in the trash", ver
        if m.get("mimeType") == FOLDER or m.get("id") != native_id:
            return Decision.DENIED, "not_found", "not an indexed file", ""
        if not self._readable(m):
            return Decision.DENIED, "limited_access_folder", "metadata visible but contents not downloadable", ver
        return Decision.ALLOWED, "delegated_read", "Drive returned the file for the verified mapped user", ver

    def acl_hint(self, native_id) -> set[str]:
        """Flatten permissions.list (inherited and shared-drive grants included) into the app's principals."""
        out: set[str] = set()
        try:
            perms = self._get(self._token(self._ingestion), f"files/{quote(native_id, safe='')}/permissions",
                              {"fields": "permissions(type,emailAddress,deleted)", "supportsAllDrives": "true"})
        except _Gone:
            return out
        for p in perms.get("permissions", []):
            if p.get("deleted"):
                continue
            kind, local = p.get("type"), str(p.get("emailAddress", "")).partition("@")[0].lower()
            if kind in ("anyone", "domain"):
                out.add("anyone" if kind == "anyone" else "domain")
            elif kind == "user" and local:
                out.add(f"user:{local}")
            elif kind == "group" and local:
                out.add(f"group:{local}")
        return out

    def ping(self):
        self._get(self._token(self._ingestion), "about", {"fields": "user(emailAddress)"})

    # ---------------------------------------------------------------- ingestion
    def start_cursor(self) -> str:
        return str(self._get(self._token(self._ingestion), "changes/startPageToken", {"supportsAllDrives": "true"})
                   .get("startPageToken", ""))

    def list_page(self, page_token=None, page_size=50):
        q = f"trashed=false and mimeType!='{FOLDER}' and {INDEXABLE}"
        r = self._get(self._token(self._ingestion), "files",
                      {**SHARED, "corpora": "allDrives", "q": q, "fields": "nextPageToken,files(id)",
                       "pageSize": min(page_size, self.page_size), **({"pageToken": page_token} if page_token else {})})
        return [f["id"] for f in r.get("files", [])], r.get("nextPageToken") or None

    def changes_since(self, cursor: str, page_size: int = 100) -> ChangePage:
        r = self._get(self._token(self._ingestion), "changes",
                      {**SHARED, "pageToken": cursor, "includeRemoved": "true", "pageSize": min(page_size, self.page_size),
                       "fields": "nextPageToken,newStartPageToken,changes(fileId,removed,time,file(trashed))"})
        changes = []
        for c in r.get("changes", []):
            gone = c.get("removed") or (c.get("file") or {}).get("trashed")
            try:
                at = datetime.fromisoformat(str(c["time"]).replace("Z", "+00:00")).timestamp()
            except (KeyError, ValueError):
                at = time.time()
            # A permission or folder change arrives as a plain file change; sync refetches and
            # recomputes acl_hint on every upsert, so the kind is only a hint (see sync._apply).
            changes.append(Change(c["fileId"], "delete" if gone else "upsert", at))
        if r.get("nextPageToken"):
            return ChangePage(changes, r["nextPageToken"], True)
        return ChangePage(changes, r.get("newStartPageToken") or cursor, False)


def from_env() -> DriveLiveConnector | None:
    """None unless IB_DRIVE_CONFIG names a JSON file:
    {"domain": "...", "ingestion_token_env": "VAR", "user_token_envs": {"user@domain": "VAR"}}.
    Token values are read from the environment on every use, so rotation needs no restart."""
    import json
    import os
    path = os.getenv("IB_DRIVE_CONFIG", "").strip()
    if not path:
        return None
    try:
        cfg = json.loads(open(path, encoding="utf-8").read())
        domain, ingestion_env, user_envs = cfg["domain"], cfg["ingestion_token_env"], dict(cfg["user_token_envs"])
    except Exception:
        raise ValueError("Drive configuration file is unreadable or missing required fields") from None
    if not os.environ.get(ingestion_env, "").strip():
        raise ValueError("A required Drive credential environment variable is unset")
    return DriveLiveConnector(domain, lambda: os.environ.get(ingestion_env, ""),
                              lambda account: os.environ.get(user_envs.get(account, ""), "") or None)
