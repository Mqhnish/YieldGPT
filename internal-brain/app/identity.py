"""Identity: who is asking. One corporate identity maps onto every platform.

In production this comes from the IdP (Okta / Google Workspace / Azure AD)
via SSO, and each platform account is linked by email. Here it's a fixed
demo directory.
"""
import os
import hashlib
import hmac
import json
import os
import time
from dataclasses import dataclass, field, replace

from .config import SECRET_KEY
from . import config


@dataclass(frozen=True)
class User:
    username: str
    name: str
    title: str
    kind: str                      # "employee" | "contractor"
    groups: frozenset = field(default_factory=frozenset)
    app_roles: frozenset = field(default_factory=frozenset)  # rights inside YieldGPT itself
    # Explicit per-platform account ids. Never assume the username is the same
    # everywhere: in production these come from SCIM / the IdP's app links.
    accounts: tuple = ()   # ((platform, account_id), ...)

    def can(self, right: str) -> bool:
        return right in self.app_roles


def _u(username, name, title, kind, groups, roles, accounts):
    if username in {"jdoe", "dana"}:
        accounts["slack:T0VENDOR"] = f"T0VENDOR/U0{username.upper()}"
    return User(username, name, title, kind, frozenset(groups), frozenset(roles), tuple(sorted(accounts.items())))


def _atl(u):  # one Atlassian account covers Confluence + Jira on the same site
    return {"confluence": f"atl-557058:{u}", "jira": f"atl-557058:{u}"}


def _emp(u):
    return {**_atl(u), "slack": f"T0COMPANYA/U0{u.upper()}", "gdrive": f"{u}@companya.example"}


# App rights:
#   ask         use the assistant (answers are always scoped to the asker's own source access)
#   audit       FULL audit access: questions, answers, per-document decisions (compliance)
#   audit_meta  operational metadata only: event types, times, health, chain status (sysadmin)
#   admin       run the system: sync, demo controls. Grants NO source or audit-content access.
USERS = {
    "jdoe":  _u("jdoe", "Jane Doe", "Backend engineer", "employee", {"all-employees", "eng"}, {"ask"}, _emp("jdoe")),
    "ravi":  _u("ravi", "Ravi Menon", "SRE, payments on-call", "employee", {"all-employees", "eng", "payments"}, {"ask"}, _emp("ravi")),
    "asha":  _u("asha", "Asha Tan", "Security engineer", "employee", {"all-employees", "eng", "security"}, {"ask"}, _emp("asha")),
    # contractor: guest in the vendor Slack workspace + external Drive email, NO Atlassian account
    "kim":   _u("kim", "Kim Lee", "External contractor (vendor)", "contractor", {"contractors"}, {"ask"},
                {"slack": "T0VENDOR/U0KIM", "gdrive": "kim@vendorco.example"}),
    "priya": _u("priya", "Priya Nair", "Compliance officer", "employee", {"all-employees", "compliance"}, {"ask", "audit"}, _emp("priya")),
    "dana":  _u("dana", "Dana Koh", "Platform admin", "employee", {"all-employees", "it"}, {"ask", "admin", "audit_meta"}, _emp("dana")),
}


def apply_account_map(mapping: dict, users: dict | None = None) -> None:
    """Live mode: map demo personas to REAL Atlassian account ids without editing code.
      {"jdoe": {"confluence": "557058:abc...", "jira": "557058:abc..."}, "kim": {}}
    Listed platforms replace the demo ids. A persona that is missing from the map, or maps to
    {}, has NO Atlassian account on the live site: its demo placeholder ids are dropped, so they
    are never sent to Atlassian (they'd be rejected, or worse, collide). The file holds ids, not secrets."""
    users = USERS if users is None else users
    for username, user in list(users.items()):
        merged = {k: v for k, v in user.accounts if k not in ("confluence", "jira")}
        merged.update({k: v for k, v in (mapping.get(username) or {}).items()
                       if v and k in ("confluence", "jira")})
        users[username] = replace(user, accounts=tuple(sorted(merged.items())))


def _apply_account_map():
    path = os.getenv("IB_ACCOUNT_MAP")
    if not path:
        return
    with open(path) as f:
        apply_account_map(json.load(f))


_apply_account_map()
DEMO_PASSWORD = "demo"
TOKEN_TTL = 8 * 3600


def account_for(user: User, platform: str, tenant: str | None = None) -> str | None:
    accounts = dict(user.accounts)
    if tenant is None:
        return accounts.get(platform)
    if platform == 'slack':
        from . import slack_oauth
        if slack_oauth.RUNTIME is not None:
            stored = slack_oauth.RUNTIME.store.account(user.username, tenant)
            if stored:
                return stored
    explicit = accounts.get(f'{platform}:{tenant}')
    if explicit:
        return explicit if explicit.startswith(tenant + '/') else None
    primary = accounts.get(platform)
    return primary if primary and primary.startswith(tenant + '/') else None


def principals(user: User) -> set[str]:
    """Flat principal set, used ONLY for the fast index prefilter.
    Exact decisions always go through each platform's native check."""
    p = {f"user:{user.username}", "anyone"} | {f"group:{g}" for g in user.groups}
    if user.kind == "employee":
        p.add("domain")
    return p


def _sign(payload: str) -> str:
    return hmac.new(SECRET_KEY.encode(), payload.encode(), hashlib.sha256).hexdigest()[:32]


def login(username: str, password: str) -> str | None:
    if not config.DEMO_MODE or os.getenv('IB_SLACK_CONFIG', '').strip():
        return None
    if username not in USERS or not hmac.compare_digest(password, DEMO_PASSWORD):
        return None
    payload = f"{username}.{int(time.time()) + TOKEN_TTL}"
    return f"{payload}.{_sign(payload)}"


def verify(token: str) -> User | None:
    # This verifier is exclusively the fictional demo identity provider. Member 1
    # must replace login/verify with trusted SSO before enabling real source access.
    if not config.DEMO_MODE or os.getenv('IB_SLACK_CONFIG', '').strip():
        return None
    try:
        username, expiry, sig = token.rsplit(".", 2)
    except ValueError:
        return None
    if len(expiry)>12 or not expiry.isascii() or not expiry.isdigit() or not hmac.compare_digest(sig, _sign(f"{username}.{expiry}")) or int(expiry) < time.time():
        return None
    return USERS.get(username)
