"""HTTP API + demo UI.

Run:  uvicorn app.server:app --reload     then open http://localhost:8000
"""
import hashlib
import hmac
from contextlib import asynccontextmanager
from pathlib import Path

from fastapi import Depends, FastAPI, Header, HTTPException, Request
from fastapi.responses import FileResponse
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel, Field, field_validator

from dataclasses import asdict
from functools import partial

import anyio

from . import audit, audit_policy, identity, llm
from .brain import Brain
from .evidence import EvidenceUnavailable
from .config import DATA_DIR, DEMO_MODE, POLL_INTERVAL_S, WEBHOOK_SECRET, WEBHOOK_SECRETS
from .identity import User
from .sync_state import SqliteSyncStateStore
from .slack_runtime import create_live_slack_from_env
from .slack_worker import SlackMaintenance
from .sources.registry import build_connectors
from .sources.world import World

STATIC = Path(__file__).parent / "static"
state: dict = {}


@asynccontextmanager
async def lifespan(_app):
    if _app is app:
        raise RuntimeError("Use app.server:app; direct app.main startup bypasses audited delivery")
    audit.init()
    live = create_live_slack_from_env()
    world = World()
    connectors = build_connectors(world)
    if live:
        connectors['slack'] = live[0]
    service = Brain(world, sync_store=SqliteSyncStateStore(DATA_DIR / "sync_state.db"), connectors=connectors)
    worker = SlackMaintenance(service.syncer, live[0], poll_interval_s=POLL_INTERVAL_S,
                              reconcile_interval_s=900, event_sink=audit.log) if live else None
    state.update(brain=service, slack_receiver=live[1] if live else None, slack_worker=worker,
                 demo_mode=DEMO_MODE and not bool(live), source_mode='mixed' if live else 'simulated')
    try:
        audit.log("system", "startup", indexed_docs=len(service.index), source_mode=state['source_mode'])
        if worker:
            worker.start()
        else:
            service.syncer.start_polling(POLL_INTERVAL_S)
        yield
    finally:
        stopped = worker.stop() if worker else True
        service.syncer.stop()
        if live and stopped:
            live[0].client.close()
            from . import slack_oauth
            if slack_oauth.RUNTIME is not None:
                slack_oauth.RUNTIME.client.close()
                slack_oauth.RUNTIME = None
        state.clear()


app = FastAPI(title="The Internal Brain", lifespan=lifespan)
app.mount('/static', StaticFiles(directory=STATIC), name='static')


@app.middleware('http')
async def private_responses(request, call_next):
    response = await call_next(request)
    if request.url.path.startswith('/api/'):
        response.headers['Cache-Control'] = 'no-store, private'
        response.headers['Vary'] = 'Authorization'
    response.headers['X-Content-Type-Options'] = 'nosniff'
    response.headers['Referrer-Policy'] = 'no-referrer'
    return response


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
    question: str = Field(min_length=1, max_length=2000)

    @field_validator('question')
    @classmethod
    def not_blank(cls, value):
        if not value.strip():
            raise ValueError('Enter a question.')
        return value.strip()


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


@app.get('/console')
def console():
    return FileResponse(STATIC / 'console.html')


@app.get('/api/session')
def session(user: User = Depends(current_user)):
    return {'user': {'username': user.username, 'name': user.name, 'title': user.title,
                     'rights': sorted(user.app_roles)}, 'demo_mode': state.get('demo_mode', DEMO_MODE),
            'generation_mode': 'extractive' if llm.LLM_PROVIDER in ('stub', 'extractive') else 'model_selected',
            'source_mode': state.get('source_mode', 'simulated')}


@app.post("/api/login")
def login(body: LoginIn):
    if not DEMO_MODE or not state.get('demo_mode', False):
        raise HTTPException(403, 'Demo sign-in is disabled. Configure the trusted identity provider.')
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
    try:
        return brain().ask(user, body.question)
    except ValueError:
        raise HTTPException(422, 'Enter a question of up to 2000 characters.') from None
    except Exception:
        # Do not expose SQL, source details, model responses, tokens or a partial answer.
        raise HTTPException(503, 'The answer could not be completed. Please try again.') from None


@app.get('/api/evidence/{query_id}/{ref}')
def evidence(query_id: str, ref: str, user: User = Depends(require('ask'))):
    try:
        return brain().evidence(user, query_id, ref)
    except EvidenceUnavailable:
        raise HTTPException(404, 'Evidence is not available. Ask the question again.') from None
    except Exception:
        raise HTTPException(503, 'Evidence could not be loaded. Please try again.') from None


@app.get("/api/freshness")
def freshness(user: User = Depends(require('admin'))):
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


@app.get('/api/slack/maintenance')
def slack_maintenance(user: User = Depends(require('admin'))):
    worker = state.get('slack_worker')
    return worker.status() if worker else {'configured': False}


@app.get("/api/sync/changes")
def sync_changes(platform: str | None = None, outcome: str | None = None, limit: int = 50,
                 user: User = Depends(require("admin"))):
    return [asdict(c) for c in brain().syncer.store.recent(platform, outcome, limit)]


# ------------------------------------------------------------------ platform plumbing
@app.post('/api/slack/events')
async def slack_event(request: Request):
    receiver = state.get('slack_receiver')
    if receiver is None:
        raise HTTPException(404, 'not found')
    # Bound memory before parsing. Verify the raw signed bytes before any sync.
    body = bytearray()
    async for chunk in request.stream():
        if len(body) + len(chunk) > 1_000_000:
            raise HTTPException(413, 'Event body too large.')
        body.extend(chunk)
    try:
        result = receiver.receive(bytes(body), request.headers)
    except ValueError:
        raise HTTPException(400, 'Invalid Slack event.') from None
    except Exception:
        # A failed durable write must be retried by Slack, not acknowledged.
        raise HTTPException(503, 'Event could not be accepted.') from None
    if 'challenge' not in result:
        state['slack_worker'].wake()
    return result


def webhook_verified(platform: str, raw: bytes, headers) -> bool:
    """Each platform's own scheme. Replays are harmless: a webhook only triggers a re-fetch,
    and sync confirms the change against the source before applying it."""
    secret = WEBHOOK_SECRETS[platform]
    if platform == "gdrive":  # Drive push channel: the token set in files.watch / changes.watch
        return hmac.compare_digest(headers.get("x-goog-channel-token", ""), secret)
    # Jira / Confluence Cloud webhooks with a secret: X-Hub-Signature: sha256=<HMAC of raw body>
    expected = "sha256=" + hmac.new(secret.encode(), raw, hashlib.sha256).hexdigest()
    return hmac.compare_digest(headers.get("x-hub-signature", ""), expected)


@app.post("/api/webhooks/{platform}")
async def webhook(platform: str, request: Request):
    if platform == 'slack' and state.get('slack_receiver') is not None:
        raise HTTPException(404, 'Use the signed Slack Events endpoint.')
    if platform not in WEBHOOK_SECRETS:
        raise HTTPException(404, 'Unknown platform.')
    raw = await request.body()
    if not webhook_verified(platform, raw, request.headers):
        await anyio.to_thread.run_sync(partial(audit.log, "webhook", "webhook_rejected",
                                               severity="alert", platform=platform))
        raise HTTPException(401, "bad webhook signature")
    try:
        body = WebhookIn.model_validate_json(raw)
    except ValueError:
        raise HTTPException(422, "invalid webhook body") from None
    await anyio.to_thread.run_sync(brain().syncer.on_webhook, platform, body.native_id, body.kind)
    return {"ok": True}


@app.post("/api/sync/poll")
def poll_now(user: User = Depends(require("admin"))):
    worker = state.get('slack_worker')
    try:
        return worker.poll() if worker else brain().syncer.poll()
    except Exception:
        raise HTTPException(503, 'Sync could not be completed.') from None


@app.post("/api/sim")
def simulate(body: SimIn, user: User = Depends(require("admin"))):
    """Demo control panel: mutate the simulated platforms to show freshness + revocation live.
    Disabled unless IB_DEMO_MODE=1: in a real deployment nobody should be able to change
    source permissions through the Brain."""
    if not state.get('demo_mode', DEMO_MODE):
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
