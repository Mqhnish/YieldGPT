# Integrated Member 2 handoff

Base: the supplied `Tencent---YieldGPT-main.zip`, which includes Member 3’s audit, reliability and Drive work. This delivery preserves that layer and adds the fixes described in [INTEGRATION_REVIEW.md](INTEGRATION_REVIEW.md). Do not overwrite it with the older Member 1-only project.

## Shared boundaries

- Start `app.server:app --workers 1 --no-access-log`. The mounted `app.main` owns shared handlers; the outer server owns checkpoint-before-release, delivery records and compliance APIs. Direct child startup fails.
- `Brain(world=None, sync_store=None, *, connectors=None, index=None, event_sink=None)` and `Brain.ask(user, question)` remain compatible. `Brain.evidence` rechecks current source access/version. `Connector` and `SourceDoc` stay authoritative.
- `llm.complete(question, sources, asker)` still returns a string-compatible Completion, now with a measurement dictionary. `IB_LLM_REQUIRE_LIVE=1` forbids silent offline fallback.
- Audit schemas `authz_decision/1`, `context_assembled/1`, `answer_returned/1` remain. Additive events: `model_measurement`, `query_performance`, `history_listed`, `question_replayed`, Slack OAuth connect/disconnect events. Raw model response, tokens and arbitrary provider errors are not logged.
- Member 3 seals sensitive audit content with AES-GCM and supports independent S3 Object Lock checkpoints using separate credentials. Missing encryption refuses text persistence. Local checkpoints are a demo mode, not independent protection.

## HTTP additions

| Route | Behavior |
|---|---|
| GET /api/history | Actor-scoped timestamp/query-ID list of delivered, retained questions; no old text |
| POST /api/history/{query_id}/replay | Uses retained question, reruns complete retrieval/current permission checks, and creates a new audited query/delivery |
| GET /api/evidence/{query_id}/{ref} | Current access/version check; generic unavailable response; now delivery-checkpoint protected |
| POST /api/slack/oauth/start | Authenticated ask-right user starts linking a configured workspace |
| GET /api/slack/oauth/callback | Single-use state, workspace check and Slack auth.test; stores encrypted delegated token |
| DELETE /api/slack/oauth/{team} | Revokes the current actor's installation locally; preserves a tombstone to prevent environment-token fallback |
| POST /api/slack/events | Verifies raw-body signature with the matching installation before persistence |

Replay survives process restart; its availability follows encrypted audit retention. Citation previews retain their short TTL. A preview delivery cannot convert a withheld answer into saved history. Account changes clear answer/evidence/history UI and abort pending requests.

## Slack identity and configuration

`account_for(user, 'slack', tenant)` supports per-workspace `slack:TTEAM` account links and OAuth-bound identities. Resource IDs are `TTEAM/CHANNEL/THREAD_TS`; all default Slack fixtures now include workspace IDs. The federated connector fits the existing single `slack` registry slot and dispatches authorization, reads, snapshots and cursors per workspace. Keep the explicit conversation ingestion allowlist. Do not infer corporate identity from a submitted Slack ID, username or arbitrary matching email.

Manual env-token deployments must supply trusted account links in Member 1's authenticated User object. OAuth binds a Slack-verified account to the authenticated corporate actor. SSO itself remains unimplemented. Storage and refresh are currently single-process, matching the deployment's one-worker index.

## Reproduce and merge

Run the entire test suite, `scripts/compare.py`, and the five-scenario demo. Saved current results are in `evaluation/reports`; older supplied Member 3 evidence is labeled historical and was not re-certified here. The package includes a changes manifest and a patch against the supplied Member 3 ZIP for review.

For live acceptance, fill approved `.env` settings, run `evaluate.py --mode live`, and run `verify_live_slack.py` for each prepared lifecycle phase. The latter only reads; a workspace owner prepares, edits, revokes, deletes or expires disposable test fixtures. Do not mark live acceptance complete from MockTransport tests. Verify independent checkpoints using Member 3's live S3 suite. Confirm exact Tencent service minima with organizers; record the rule/reference in `TENCENT_REQUIREMENTS.md`.

Security integration note: seeded demo login and demo-token verification are disabled outside demo mode or when live Slack configuration is present. Member 1 must supply the trusted identity provider before real-source employee access or OAuth linking. This guard prevents the public `demo` password from opening real company data.
