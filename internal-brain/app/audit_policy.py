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

Member 3 sign-off (adopts Member 1's handoff section 4.3 defaults):
  - Compliance may resolve a pseudonym to a username; the lookup is itself audited.
  - Question/answer/draft/title text is sealed at rest (AES-GCM) and redacted after
    TEXT_RETENTION_DAYS; decision metadata is kept for the deployment's lifetime.
  - No self-service history for employees in this release.
  - Alerts stay in audit_meta scope; no separate security-reviewer role.
  - Chain verification results (row ids, hashes, checkpoint status) are operational
    metadata, visible to both scopes.
"""
import hashlib
import hmac
import json

from . import audit
from .config import AUDIT_PSEUDONYM_KEY
from .identity import USERS, User

TEXT_RETENTION_DAYS = audit.retention_days()

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
    result = audit.verify_report()
    audit.log(viewer.username, "audit_accessed", scope=scope, action="verify", ok=result["ok"],
              status=result["status"])
    return result


def resolve_pseudonym(viewer: User, token: str) -> dict:
    if scope_for(viewer) != FULL:
        audit.log(viewer.username, "audit_access_denied", severity="warning", action="resolve_pseudonym")
        raise PermissionError("pseudonym resolution requires full audit access")
    match = next((a for a in sorted(set(USERS) | audit.actors()) if pseudonym(a) == token), None)
    audit.log(viewer.username, "audit_accessed", scope=FULL, action="resolve_pseudonym",
              filters={"pseudonym": token}, results=int(match is not None))
    return {"pseudonym": token, "actor": match}


TRAIL_FILTERS = ("actor", "event", "severity", "decision", "platform", "doc_uid", "query_id", "request_id",
                 "since", "until")
TRAIL_PAGE_MAX = 500
EXPORT_PAGE = 1000


def trail(viewer: User, filters: dict, before_id: int | None = None, limit: int = 100) -> dict:
    """The complete audit trail, one page at a time, newest first, with full (decrypted) detail.
    Every event type is included: requests, decisions, deliveries, logins, alerts and audit reads.
    Compliance only; administrators keep the pseudonymised metadata view (view_events)."""
    filters = {k: v for k, v in filters.items() if k in TRAIL_FILTERS and v not in (None, "")}
    if scope_for(viewer) != FULL:
        audit.log(viewer.username, "audit_access_denied", severity="warning", action="trail", filters=filters)
        raise PermissionError("the complete audit trail requires full audit access")
    limit = max(1, min(int(limit), TRAIL_PAGE_MAX))
    rows = audit.search(**filters, before_id=before_id, limit=limit + 1)
    page, more = rows[:limit], len(rows) > limit
    audit.log(viewer.username, "audit_accessed", scope=FULL, action="trail", filters=filters,
              before_id=before_id, results=len(page))
    return {"events": page, "next_before_id": page[-1]["id"] if more else None}


def export_trail(viewer: User):
    """Every audit row, newest first, as JSON lines with its hash links, so the export can be
    checked offline. The export itself is audited before the first line is produced."""
    if scope_for(viewer) != FULL:
        audit.log(viewer.username, "audit_access_denied", severity="warning", action="export")
        raise PermissionError("exporting the audit trail requires full audit access")
    head = audit.head()
    audit.log(viewer.username, "audit_accessed", scope=FULL, action="export", through_row=head[0] if head else 0)

    def lines():
        before = (head[0] + 1) if head else None
        while before is None or before > 1:
            page = audit.search(before_id=before, limit=EXPORT_PAGE)
            if not page:
                return
            for row in page:
                yield json.dumps(row, sort_keys=True, default=str) + "\n"
            before = page[-1]["id"]
    return lines()
