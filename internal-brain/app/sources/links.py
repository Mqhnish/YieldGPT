"""Cross-platform link resolution: source URL <-> document uid.

Real content links to other systems by URL (a Confluence page with a Jira link,
a Jira remote link to a Drive file). YieldGPT stitches context across platforms
by uid, so every connector turns the URLs it finds into uids with this module.
Unknown URLs are ignored, never guessed.
"""
import re
from urllib.parse import urlparse

ATLASSIAN_SITE = "companya.atlassian.net"
SLACK_HOST = "companya.slack.com"
# Slack thread ids are workspace-scoped: "<team_id>/<channel>/<root_ts>". A permalink on a
# workspace subdomain doesn't carry the team id, so only known subdomains are resolved.
SLACK_WORKSPACES = {"companya": "T0COMPANYA", "vendor-connect": "T0VENDOR"}


def _slack_ts(digits: str) -> str:
    # Real permalinks drop the dot: p1712345678123456 -> 1712345678.123456
    return f"{digits[:-6]}.{digits[-6:]}" if len(digits) > 6 else digits


def _slack_archive(m):
    team = SLACK_WORKSPACES.get(m.group(1))
    return f"slack:{team}/{m.group(2)}/{_slack_ts(m.group(3))}" if team else None

_PATTERNS = [
    (re.compile(r"^https://[^/]+\.atlassian\.net/browse/([A-Z][A-Z0-9_]*-\d+)(?:[/?#]|$)"), lambda m: f"jira:{m.group(1)}"),
    (re.compile(r"^https://[^/]+\.atlassian\.net/wiki/spaces/[^/]+/pages/([^/?#]+)"), lambda m: f"confluence:{m.group(1)}"),
    (re.compile(r"^https://app\.slack\.com/client/(T[A-Z0-9]+)/([^/?#]+)/thread/\2-([0-9.]+)(?:[/?#]|$)"),
     lambda m: f"slack:{m.group(1)}/{m.group(2)}/{m.group(3)}"),
    (re.compile(r"^https://([a-z0-9-]+)\.slack\.com/archives/([^/?#]+)/p(\d+)"), _slack_archive),
    (re.compile(r"^https://drive\.google\.com/file/d/([^/?#]+)"), lambda m: f"gdrive:{m.group(1)}"),
    (re.compile(r"^https://docs\.google\.com/\w+/d/([^/?#]+)"), lambda m: f"gdrive:{m.group(1)}"),
]


def uid_from_url(url: str) -> str | None:
    url = (url or "").strip()
    if urlparse(url).scheme != "https":
        return None
    for pat, make in _PATTERNS:
        m = pat.match(url)
        if m:
            return make(m)  # may be None: recognised host, but not resolvable without guessing
    return None


def url_for(uid: str, confluence_space: str = "") -> str:
    """Canonical URL for a uid. Used by the fake server and simulated connectors."""
    platform, _, nid = uid.partition(":")
    if platform == "jira":
        return f"https://{ATLASSIAN_SITE}/browse/{nid}"
    if platform == "confluence":
        return f"https://{ATLASSIAN_SITE}/wiki/spaces/{confluence_space or 'x'}/pages/{nid}"
    if platform == "slack":
        parts = nid.split("/")
        if len(parts) == 3:  # workspace-scoped: same URL shape the live Slack connector emits
            team, channel, ts = parts
            return f"https://app.slack.com/client/{team}/{channel}/thread/{channel}-{ts}"
        channel, _, ts = nid.partition("/")
        return f"https://{SLACK_HOST}/archives/{channel}/p{ts}"
    if platform == "gdrive":
        return f"https://drive.google.com/file/d/{nid}"
    raise ValueError(f"unknown platform in uid {uid!r}")


def dedupe(uids) -> list[str]:
    out = []
    for u in uids:
        if u and u not in out:
            out.append(u)
    return out
