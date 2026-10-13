"""Production entrypoint with Member 3's audit and reliability layer.

Run:  uvicorn app.server:app --workers 1        (app.main stays the shared, unmodified app)

The shared app is mounted unchanged at "/". This module adds:
  - AuditedDelivery on /api/ask (receipt, terminal failure, checkpoint-before-release, delivery)
  - startup: config checks, restart recovery, retention, a startup checkpoint, maintenance
  - /api/health (public status only), /api/health/detail (admin)
  - /api/compliance/requests, /api/audit/pseudonym and the /compliance page, all through audit_policy
"""
from contextlib import asynccontextmanager

from fastapi import Depends, FastAPI, HTTPException
from fastapi.responses import FileResponse
from pydantic import BaseModel, Field

from . import audit, audit_policy, main, reliability, history, slack_oauth
from .identity import User
from .main import STATIC, current_user, require


@asynccontextmanager
async def lifespan(app):
    fatal = reliability.fatal_problems()
    if fatal:
        raise RuntimeError("refusing to start: " + "; ".join(p["message"] for p in fatal))
    async with main.lifespan(app):   # audit.init, sources, index, sync (shared, unchanged)
        abandoned = audit.recover_interrupted()
        redacted = audit.apply_retention()
        audit.try_checkpoint()
        maintenance = reliability.Maintenance(main.brain().syncer.store)
        maintenance.start()
        audit.log("system", "reliability_started", abandoned_requests=abandoned, redacted_rows=redacted,
                  checkpoint_store=audit._store().kind,
                  config_warnings=[p["code"] for p in reliability.config_problems()])
        try:
            yield
        finally:
            maintenance.stop()
            audit.try_checkpoint()


app = FastAPI(title="YieldGPT", lifespan=lifespan)
app.middleware("http")(main.private_responses)
app.add_middleware(reliability.AuditedDelivery)


def _policy(fn, *a):
    try:
        return fn(*a)
    except PermissionError as e:
        raise HTTPException(403, str(e)) from None


class ComplianceIn(BaseModel):
    question: str | None = Field(default=None, max_length=500)
    actor: str | None = None
    platform: str | None = None
    container: str | None = None
    doc_uid: str | None = None
    decision: str | None = None
    query_id: str | None = None
    since: float | None = None
    until: float | None = None


class PseudonymIn(BaseModel):
    pseudonym: str = Field(min_length=1, max_length=64)


@app.get("/compliance")
def compliance_page():
    return FileResponse(STATIC / "compliance.html")


@app.get("/api/health")
def health():
    return reliability.health(main.state.get("brain"))


@app.get("/api/health/detail")
def health_detail(user: User = Depends(require("admin"))):
    return reliability.health(main.state.get("brain"), detail=True)


@app.post("/api/compliance/requests")
def compliance_requests(body: ComplianceIn, user: User = Depends(current_user)):
    filters = audit.parse_question(body.question) if body.question else {}
    filters.update({k: v for k, v in body.model_dump().items() if v not in (None, "") and k != "question"})
    return {"filters": filters, "results": _policy(audit_policy.reconstruct, user, filters)}


@app.post("/api/audit/pseudonym")
def resolve_pseudonym(body: PseudonymIn, user: User = Depends(current_user)):
    return _policy(audit_policy.resolve_pseudonym, user, body.pseudonym)


class SlackConnectIn(BaseModel):
    team: str = Field(pattern=r'^T[A-Z0-9]+$')


@app.post('/api/slack/oauth/start')
def slack_connect(body: SlackConnectIn, user: User = Depends(require('ask'))):
    runtime = slack_oauth.RUNTIME
    if runtime is None:
        raise HTTPException(404, 'Slack OAuth is not configured.')
    try:
        url = runtime.start(user.username, body.team)
        audit.log(user.username, 'slack_connect_started', workspace=body.team)
        return {'authorization_url': url}
    except slack_oauth.OAuthUnavailable:
        raise HTTPException(400, 'Slack connection could not be started.') from None


@app.get('/api/slack/oauth/callback')
def slack_connected(code: str = '', state: str = ''):
    runtime = slack_oauth.RUNTIME
    if runtime is None:
        raise HTTPException(404, 'Slack OAuth is not configured.')
    try:
        actor, team = runtime.finish(code, state)
        audit.log(actor, 'slack_connected', workspace=team)
        return {'connected': True, 'message': 'Slack is connected. Return to the workspace to ask a question.'}
    except Exception:
        raise HTTPException(400, 'Slack connection failed. Start again from your account.') from None


@app.delete('/api/slack/oauth/{team}')
def slack_disconnect(team: str, user: User = Depends(require('ask'))):
    runtime = slack_oauth.RUNTIME
    if runtime is None:
        raise HTTPException(404, 'Slack OAuth is not configured.')
    runtime.store.revoke(user.username, team)
    audit.log(user.username, 'slack_disconnected', workspace=team)
    return {'connected': False}


@app.get('/api/history')
def own_history(user: User = Depends(require('ask'))):
    return {'items': history.list_history(user.username)}


@app.post('/api/history/{query_id}/replay')
def replay_question(query_id: str, user: User = Depends(require('ask'))):
    try:
        return history.replay(main.brain(), user, query_id)
    except history.HistoryUnavailable:
        raise HTTPException(404, 'Previous question is not available.') from None
    except Exception:
        raise HTTPException(503, 'The question could not be replayed securely.') from None


app.mount("/", main.app)
