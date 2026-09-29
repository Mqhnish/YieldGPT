"""Identity: who is asking. One corporate identity maps onto every platform.

In production this comes from the IdP (Okta / Google Workspace / Azure AD)
via SSO, and each platform account is linked by email. Here it's a fixed
demo directory.
"""
import hashlib
import hmac
import time
from dataclasses import dataclass, field

from .config import SECRET_KEY


@dataclass(frozen=True)
class User:
    username: str
    name: str
    title: str
    kind: str                      # "employee" | "contractor"
    groups: frozenset = field(default_factory=frozenset)
    app_roles: frozenset = field(default_factory=frozenset)  # rights inside the Internal Brain itself
    # Explicit per-platform account ids. Never assume the username is the same
    # everywhere: in production these come from SCIM / the IdP's app links.
    accounts: tuple = ()   # ((platform, account_id), ...)

    def can(self, right: str) -> bool:
        return right in self.app_roles


def _u(username, name, title, kind, groups, roles, accounts):
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
DEMO_PASSWORD = "demo"
TOKEN_TTL = 8 * 3600


def account_for(user: User, platform: str) -> str | None:
    return dict(user.accounts).get(platform)


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
    if username not in USERS or not hmac.compare_digest(password, DEMO_PASSWORD):
        return None
    payload = f"{username}.{int(time.time()) + TOKEN_TTL}"
    return f"{payload}.{_sign(payload)}"


def verify(token: str) -> User | None:
    try:
        username, expiry, sig = token.rsplit(".", 2)
    except ValueError:
        return None
    if not hmac.compare_digest(sig, _sign(f"{username}.{expiry}")) or int(expiry) < time.time():
        return None
    return USERS.get(username)
