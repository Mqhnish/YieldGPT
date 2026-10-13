"""Shared helpers for evidence reports from live Atlassian runs. Owner: Member 1."""
from __future__ import annotations

import subprocess

from .. import config
from ..identity import USERS


def redact(text: str) -> str:
    """Remove the API token, login email, site name and every mapped Atlassian accountId."""
    secrets_ = [config.ATLASSIAN_API_TOKEN, config.ATLASSIAN_EMAIL]
    host = config.ATLASSIAN_SITE.replace("https://", "").replace("http://", "").strip("/")
    if host:
        secrets_ += [host, host.split(".")[0]]
    secrets_ += [a for u in USERS.values() for p, a in u.accounts if p in ("confluence", "jira") and a]
    for s in sorted({s for s in secrets_ if s and len(s) >= 4}, key=len, reverse=True):
        text = text.replace(s, "[redacted]")
    return text


def git(*args) -> str:
    try:
        return subprocess.run(["git", *args], capture_output=True, text=True, check=True).stdout.strip()
    except Exception:  # noqa: BLE001
        return "unknown"


def commit_label() -> tuple[str, bool]:
    return git("rev-parse", "HEAD"), bool(git("status", "--porcelain", "--untracked-files=no"))
