"""Thin HTTP client for Atlassian Cloud (Confluence + Jira share one site and one auth).

Error mapping is the important part, because it decides fail-closed behaviour:

  404                        -> NotFound          (resource doesn't exist)
  401 / 403                  -> SourceUnavailable (our credentials are wrong or lack a scope:
                                                   we can't decide, so we must not allow)
  429 / 5xx / network / TLS  -> SourceUnavailable
  other 4xx                  -> SourceUnavailable (a bug on our side is still "can't decide")

Error text never includes the auth header or token (contract R12).

Credentials only ever go to the configured site. Pagination links come from server
responses, so an absolute URL (or a protocol-relative "//host/..." path) pointing
anywhere else is refused before any request is made.
"""
from __future__ import annotations

import httpx

from .base import SourceUnavailable


class NotFound(Exception):
    pass


class AtlassianClient:
    def __init__(self, site: str, email: str = "", api_token: str = "",
                 transport: httpx.BaseTransport | None = None, timeout_s: float = 10.0):
        if not site.startswith("https://"):
            site = "https://" + site
        self.site = site.rstrip("/")
        self.host = httpx.URL(self.site).host
        auth = (email, api_token) if email and api_token else None
        self._http = httpx.Client(base_url=self.site, auth=auth, transport=transport, timeout=timeout_s,
                                  headers={"Accept": "application/json"}, follow_redirects=False)

    def _safe_path(self, path: str) -> str:
        if path.startswith("//") or "://" in path.split("?", 1)[0]:
            u = httpx.URL(path if "://" in path else "https:" + path)
            if u.scheme != "https" or u.host != self.host:
                raise SourceUnavailable(f"{self.host}: refused link to another host")
            return u.raw_path.decode()
        if not path.startswith("/"):
            raise SourceUnavailable(f"{self.host}: refused relative link")
        return path

    def request(self, method: str, path: str, *, params=None, json=None, timeout: float | None = None):
        path = self._safe_path(path)
        try:
            r = self._http.request(method, path, params=params, json=json,
                                   timeout=timeout if timeout is not None else httpx.USE_CLIENT_DEFAULT)
        except httpx.HTTPError as e:
            raise SourceUnavailable(f"{self.host}: {type(e).__name__}") from None
        if r.status_code == 404:
            raise NotFound(path)
        if r.status_code in (401, 403):
            raise SourceUnavailable(f"{self.host}: HTTP {r.status_code} (check API token and scopes)")
        if r.status_code == 429:
            raise SourceUnavailable(f"{self.host}: rate limited (Retry-After={r.headers.get('Retry-After', '?')})")
        if r.status_code >= 400:
            raise SourceUnavailable(f"{self.host}: HTTP {r.status_code}")
        return r.json() if r.content else None

    def get(self, path, _timeout: float | None = None, **params):
        return self.request("GET", path, params=params or None, timeout=_timeout)

    def post(self, path, body, _timeout: float | None = None):
        return self.request("POST", path, json=body, timeout=_timeout)

    def close(self):
        self._http.close()
