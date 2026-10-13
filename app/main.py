"""HTTP API + demo UI.

Run:  uvicorn app.main:app --reload     then open http://localhost:8000
"""
import hmac
from contextlib import asynccontextmanager
from pathlib import Path

from fastapi import Depends, FastAPI, Header, HTTPException
from fastapi.responses import FileResponse
from pydantic import BaseModel

from dataclasses import asdict

from . import audit, audit_policy, identity
from .brain import Brain
from .config import DATA_DIR, DEMO_MODE, POLL_INTERVAL_S, WEBHOOK_SECRET
from .identity import User
from .sync_state import SqliteSyncStateStore

STATIC = Path(__file__).parent / "static"
state: dict = {}


@asynccontextmanager
async def lifespan(_app):
    audit.init()
    brain = Brain(sync_store=SqliteSyncStateStore(DATA_DIR / "sync_state.db"))
    brain.syncer.start_polling(POLL_INTERVAL_S)
    state["brain"] = brain
    audit.log("system", "startup", indexed_docs=len(brain.index))
    yield
    brain.syncer.stop()


app = FastAPI(title="YieldGPT", lifespan=lifespan)


def brain() -> Brain:
    return state["brain"]


# ------------------------------------------------------------------ auth
def current_user(authorization: str = Header(default="")) -> User:
    user = identity.verify(authorization.removeprefix("Bearer ").strip())
    if not user:
        raise HTTPException(401, "invalid or expired token")
    return user


def require(right: str):
    def dep(user: User = Depends(current_user)) -> User:
        if not user.can(right):
            audit.log(user.username, "app_permission_denied", severity="warning", right=right)
            raise HTTPException(403, f"'{user.username}' lacks the '{right}' right")
        return user
    return dep


class LoginIn(BaseModel):
    username: str
    password: str


class AskIn(BaseModel):
    question: str


class AuditIn(BaseModel):
    question: str | None = None
    actor: str | None = None
    platform: str | None = None
    container: str | None = None
    doc_uid: str | None = None
    decision: str | None = None
    since: float | None = None


class WebhookIn(BaseModel):
    native_id: str
    kind: str = "upsert"   # upsert | acl | delete


class SimIn(BaseModel):
    action: str                # confluence_update | confluence_restrict | slack_remove_member | slack_post | jira_update
    target: str                # page id / channel / issue key
    value: str = ""            # text to append, username, principals csv, status
    push: bool = True          # False = simulate a MISSED webhook


@app.get("/")
def ui():
    return FileResponse(STATIC / "index.html")


@app.post("/api/login")
def login(body: LoginIn):
    token = identity.login(body.username, body.password)
    if not token:
        audit.log(body.username, "login_failed", severity="warning")
        raise HTTPException(401, "bad credentials")
    u = identity.USERS[body.username]
    audit.log(u.username, "login")
    return {"token": token, "user": {"username": u.username, "name": u.name, "title": u.title,
                                     "rights": sorted(u.app_roles)}}


@app.post("/api/ask")
def ask(body: AskIn, user: User = Depends(require("ask"))):
    return brain().ask(user, body.question)


@app.get("/api/freshness")
def freshness(user: User = Depends(current_user)):
    return brain().freshness(POLL_INTERVAL_S)


# ------------------------------------------------------------------ audit (all reads go through audit_policy)
def _policy(fn, *a):
    try:
        return fn(*a)
    except PermissionError as e:
        raise HTTPException(403, str(e))


@app.post("/api/audit/query")
def audit_query(body: AuditIn, user: User = Depends(current_user)):
    filters = audit.parse_question(body.question) if body.question else {}
    filters.update({k: v for k, v in body.model_dump().items() if v is not None and k != "question"})
    return {"filters": filters, "results": _policy(audit_policy.reconstruct, user, filters)}


@app.get("/api/audit/events")
def audit_events(severity: str | None = None, limit: int = 50, user: User = Depends(current_user)):
    events = audit.search(severity=severity, limit=limit)
    return {"scope": audit_policy.scope_for(user),
            "events": _policy(audit_policy.view_events, user, events, {"severity": severity})}


@app.get("/api/audit/verify")
def audit_verify(user: User = Depends(current_user)):
    return _policy(audit_policy.verify, user)


# ------------------------------------------------------------------ sync bookkeeping (operators)
@app.get("/api/sync/state")
def sync_state(user: User = Depends(require("admin"))):
    """Operational: cursors, health, failures. Resource ids only, never content or titles."""
    return brain().syncer.status(POLL_INTERVAL_S)


@app.get("/api/sync/changes")
def sync_changes(platform: str | None = None, outcome: str | None = None, limit: int = 50,
                 user: User = Depends(require("admin"))):
    return [asdict(c) for c in brain().syncer.store.recent(platform, outcome, limit)]


# ------------------------------------------------------------------ platform plumbing
@app.post("/api/webhooks/{platform}")
def webhook(platform: str, body: WebhookIn, x_webhook_secret: str = Header(default="")):
    # Real platforms sign payloads (Slack signing secret, Atlassian JWT, Drive channel token).
    if not hmac.compare_digest(x_webhook_secret, WEBHOOK_SECRET):
        audit.log("webhook", "webhook_rejected", severity="alert", platform=platform)
        raise HTTPException(401, "bad webhook signature")
    brain().syncer.on_webhook(platform, body.native_id, body.kind)
    return {"ok": True}


@app.post("/api/sync/poll")
def poll_now(user: User = Depends(require("admin"))):
    return brain().syncer.poll()


@app.post("/api/sim")
def simulate(body: SimIn, user: User = Depends(require("admin"))):
    """Demo control panel: mutate the simulated platforms to show freshness + revocation live.
    Disabled unless IB_DEMO_MODE=1: in a real deployment nobody should be able to change
    source permissions through the Brain."""
    if not DEMO_MODE:
        raise HTTPException(404, "not found")
    w = brain().world
    try:
        if body.action == "confluence_update":
            w.confluence_update(body.target, body.value, push=body.push)
        elif body.action == "confluence_restrict":
            w.confluence_restrict(body.target, {p.strip() for p in body.value.split(",")}, push=body.push)
        elif body.action == "slack_remove_member":
            w.slack_remove_member(body.target, body.value, push=body.push)
        elif body.action == "slack_post":
            w.slack_post(body.target, user.username, body.value, push=body.push)
        elif body.action == "jira_update":
            w.jira_update(body.target, status=body.value or None, push=body.push)
        else:
            raise HTTPException(400, "unknown action")
    except KeyError as e:
        raise HTTPException(404, f"unknown target {e}")
    audit.log(user.username, "simulated_platform_change", action=body.action, target=body.target,
              value=body.value, webhook_delivered=body.push)
    return {"ok": True}
