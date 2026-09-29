"""Audit access policy: who may look at audit records, and how much they see.

Agreed between Member 1 (permissions) and Member 3 (audit). Enforced here, in one
place, for every audit read path (API, UI, exports).

  Right        Who (demo)        Sees
  -----------  ----------------  ---------------------------------------------------------------
  audit        compliance        EVERYTHING: questions, answers (incl. discarded drafts), every
                                 per-document decision with reason, versions sent to the model,
                                 request reconstruction.
  audit_meta   platform admin    OPERATIONAL METADATA ONLY: event type, time, severity, platform,
                                 decision outcome, chain verification status. Actor ids are
                                 pseudonymised. No question/answer text, no doc ids, titles,
                                 containers or reasons. No reconstruction.
  (neither)    everyone else     Nothing.

Principles
  P1  Running the system is not the same as reading what people asked. Admin rights
      grant no source access and no audit content.
  P2  Audit records can reveal restricted content (titles, answer text), so full access
      is limited to compliance, who are accountable for it.
  P3  Every read of the audit trail is itself audited ("audit_accessed"), including
      the viewer, scope, filters and result count.
  P4  Pseudonyms are stable (same user -> same token) so admins can still spot one
      account generating many alerts, and compliance can resolve the token if needed.
"""
import hashlib
import hmac

from . import audit
from .config import AUDIT_PSEUDONYM_KEY
from .identity import User

FULL = "full"
META = "meta"

META_FIELDS = ("id", "ts", "event", "severity", "platform", "decision")
SYSTEM_ACTORS = {"system", "webhook"}


def scope_for(user: User) -> str | None:
    if user.can("audit"):
        return FULL
    if user.can("audit_meta"):
        return META
    return None


def pseudonym(actor: str) -> str:
    if actor in SYSTEM_ACTORS:
        return actor
    return "user-" + hmac.new(AUDIT_PSEUDONYM_KEY.encode(), actor.encode(), hashlib.sha256).hexdigest()[:10]


def view_events(viewer: User, events: list[dict], filters: dict | None = None) -> list[dict]:
    scope = scope_for(viewer)
    if scope is None:
        audit.log(viewer.username, "audit_access_denied", severity="warning", filters=filters or {})
        raise PermissionError("no audit access")
    if scope == FULL:
        out = events
    else:
        out = [{**{k: e.get(k) for k in META_FIELDS}, "actor": pseudonym(e["actor"])} for e in events]
    audit.log(viewer.username, "audit_accessed", scope=scope, filters=filters or {}, results=len(out))
    return out


def reconstruct(viewer: User, filters: dict) -> list[dict]:
    if scope_for(viewer) != FULL:
        audit.log(viewer.username, "audit_access_denied", severity="warning", action="reconstruct", filters=filters)
        raise PermissionError("request reconstruction requires full audit access")
    stories = audit.reconstruct(**filters)
    audit.log(viewer.username, "audit_accessed", scope=FULL, action="reconstruct", filters=filters,
              results=len(stories))
    return stories


def verify(viewer: User) -> dict:
    scope = scope_for(viewer)
    if scope is None:
        audit.log(viewer.username, "audit_access_denied", severity="warning", action="verify")
        raise PermissionError("no audit access")
    result = audit.verify()
    audit.log(viewer.username, "audit_accessed", scope=scope, action="verify", ok=result.get("ok"))
    return result
