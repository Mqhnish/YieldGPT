# Slack: Member 2 handoff

The demo continues to work without external credentials. `SlackConnector` uses fictional Company A data. `SlackLiveConnector` is an optional read-only Web API integration tested with `httpx.MockTransport`; it has **not been verified against a live Slack account**. No OAuth credentials are included.

## What is implemented

- Native account authorization in the simulator, including renamed corporate accounts. A corporate username never substitutes for the asker's linked Slack identity.
- Whole-thread content, content-hash versions that change on edits/deletions, retention-aware simulated reads, and explicit simulated public/DM cases. Existing demo channels retain their original conservative membership-only fixture profile; a real public-channel membership removal is not assumed to revoke readability.
- An optional real connector with paginated history/thread reads, a configurable conversation allowlist, native IDs of the form `TEAM/CHANNEL/THREAD_TS`, and `uid = slack:<native_id>`.
- Delegated reads: the application resolves the authenticated user's mapped `TEAM/USER` account to a server-held user credential. `auth.test` verifies the credential's workspace and user, and rejects bot identities. Successful ingestion-token access is never used as evidence of employee access.
- `read_authorized(user, native_id)` returns only the thread that Slack returns to that user at that moment. The pipeline calls this optional extension at its evidence boundaries. Missing/denied resources return `None`; unknown permission state, credential failures, timeouts, pagination truncation and rate limits raise `SourceUnavailable`.
- A persistent SQLite metadata feed, signed Events API validation, a five-minute timestamp window, installation checks, event-ID deduplication, and routing of new messages, edits, deletions and conversation membership changes.
- A separate `reconcile()` backstop that scans every configured conversation completely before recording deletion changes. Rate-limited/failed scans do not infer deletions.

`SlackSourceDoc` subclasses the unchanged `SourceDoc` contract. Its `message_spans` contain exact `start`, `end` string offsets and original message `ts` values. A new reply or edit can update the thread timestamp, but old messages must not be described as occurring in the new time window. Consumers that do not need message windows can treat this as a regular `SourceDoc`.

## Security boundary and integration contract

```text
Authenticated corporate User
    -> account_for(user, "slack") = TEAM/USER
    -> server-owned credential resolver
    -> auth.test verifies TEAM and USER, rejects bots
    -> conversations.replies under that credential
    -> authorized SlackSourceDoc
    -> Member 2 evidence selection / model input
    -> fresh delegated read before answer/citation release
```

`acl_hint()` intentionally returns `{"anyone"}`. Native account aliases cannot be safely reduced to the demo's corporate username principals. This is a broad candidate prefilter, **not an access grant**. Every candidate still passes live authorization. Do not show index records, denied-resource counts, connector reasons or titles directly in the employee UI.

`fetch()` is the ingestion method. Never use its return value as the user's answer context in place of `read_authorized()`. Do not cache a positive permission decision across questions. Source API error messages are normalized to fixed safe strings; HTTP request/response debug logging must remain off because headers contain credentials.

## Optional configuration file

`app.slack_runtime.create_live_slack_from_env()` provides startup wiring. Leave `IB_SLACK_CONFIG` unset for the offline demo. To configure a real installation, create a JSON file containing **environment variable names, never token values**:

```json
{
  "team_id": "TREALTEAM",
  "channels": ["CAPPROVED", "GPRIVATE"],
  "ingestion_token_env": "IB_SLACK_INGESTION_TOKEN",
  "user_token_envs": {
    "TREALTEAM/UJANE": "IB_SLACK_JANE_TOKEN",
    "TREALTEAM/URAVI": "IB_SLACK_RAVI_TOKEN"
  },
  "signing_secret_env": "IB_SLACK_SIGNING_SECRET",
  "app_id": "AREALAPP",
  "page_limit": 100,
  "max_pages": 100,
  "request_timeout": 2.0
}
```

IDs above are placeholders; use your installation's actual IDs. Set `IB_SLACK_CONFIG` to that file's path. Populate the named secret variables through the server environment/secret manager and optionally set `IB_SLACK_EVENTS_DB` to a persistent database path. The resolver reads delegated user credentials afresh on each operation, supporting externally managed token rotation. Ingestion and signing-secret rotation requires recreating the runtime. Startup rejects unknown fields, invalid IDs, cross-workspace account mappings, missing secret values and invalid storage with safe messages.

The factory returns `(connector, receiver)` or `None`; it performs no network requests by itself. Identity is verified when the connector actually reads Slack. Application startup replaces `connectors["slack"]` with this connector before constructing `Brain`; the rest of the code below documents that seam explicitly.

## Wiring into Member 1's application

The new files do not change `sources/base.py`, registry defaults, login, audit storage or the sync contract. `Brain` accepts a connector dictionary for integration. For example, in application startup after obtaining configuration from server secrets:

```python
from app.brain import Brain
from app.sources.registry import build_connectors
from app.sources.world import World
from app.sources.slack_events import SlackEventStore, SlackEventReceiver
from app.sources.slack_live import SlackLiveConnector

world = World()
connectors = build_connectors(world)
store = SlackEventStore("data/slack-events.db")

# Secrets/configuration supplied by your deployment, never a browser request.
# credential_store must be keyed by the verified IdP-to-Slack mapping.
def user_token_resolver(mapped_account):
    return credential_store.get_user_token(mapped_account)

slack = SlackLiveConnector(
    team_id=slack_team_id,                 # e.g. the native T... workspace ID
    channels=slack_conversation_ids,       # explicit C..., G..., D... allowlist
    ingestion_token=slack_ingestion_token,
    user_token_resolver=user_token_resolver,
    event_store=store,
)
connectors["slack"] = slack
brain = Brain(world=world, connectors=connectors, sync_store=sync_store)
receiver = SlackEventReceiver(
    store, slack_signing_secret, slack_team_id, slack_conversation_ids,
    app_id=slack_app_id,
)
```

These names represent deployment values and your credential-store implementation; this snippet is an integration example, not a second application entry point. Keep `IB_DEMO_MODE=0` when connecting real data. Replace the demo login/account directory with Member 1's trusted identity mapping before exposing a real-data deployment. The default configuration remains an offline demo. The application owner can opt into this injection through `IB_SLACK_CONFIG` and the runtime factory.

The credential resolver gets the account from the authenticated `User`; it must never take a submitted Slack user ID or token. Obtain user OAuth consent and appropriate scopes. Store/rotate credentials in the deployment's secret store. The adapter supports `xoxp-` and rotated `xoxe.xoxp-` user access tokens. The integrated `app/slack_oauth.py` now stores encrypted installations, binds the authenticated actor to a Slack-verified TEAM/USER, uses expiring single-use OAuth state, and rotates refresh tokens before expiry. See the multi-workspace setup below.

### Events endpoint

The application already wires `/api/slack/events` as a dedicated endpoint; it disables the shared-secret Slack route in live mode. The following simplified example explains the integration; `app/main.py` also bounds the incoming stream and handles durable-write failures. Do not reuse the simulated webhook-secret scheme for Slack. Verify the **raw bytes** before decoding or acting on the event:

```python
from fastapi import HTTPException, Request

@app.post("/api/slack/events")
async def slack_events(request: Request):
    try:
        response = receiver.receive(await request.body(), request.headers)
    except ValueError:
        raise HTTPException(401, "Invalid event") from None
    # Persisted metadata is now durable. Wake the serialized maintenance
    # worker, then ACK quickly. Never fetch threads inside this ACK.
    maintenance.wake()
    return response
```

Enforce a request body-size limit in the server/proxy as well; the receiver rejects payloads larger than 1 MB after reading. The receiver returns the signed URL-verification challenge during Slack endpoint setup. Duplicate deliveries ACK successfully and create no second change record. Use `app_id` in deployments to pin the installation in addition to the workspace.

### Polling and missed-event repair

`app.slack_worker.SlackMaintenance` supplies a serialized scheduler for the live mode:

```python
from app.slack_worker import SlackMaintenance

maintenance = SlackMaintenance(
    brain.syncer, slack, poll_interval_s=300, reconcile_interval_s=900,
    event_sink=audit.log,
)
maintenance.start()
# After receiver.receive(...) has committed a verified event:
maintenance.wake()  # non-blocking; the endpoint can ACK immediately
# For an authorized admin's manual full refresh:
maintenance.refresh()  # use this instead of brain.syncer.full_load()
# During application shutdown:
stopped = maintenance.stop(timeout_s=2.0)
if stopped:
    slack.client.close()
```

Use this **instead of** `brain.syncer.start_polling()` when live Slack is configured. The same worker polls all platforms on the scheduled interval, reconciles Slack when its independent timer is due, and polls only Slack after event wakes. Every worker/admin-refresh operation is serialized through one lock. The signed endpoint should call only `receiver.receive()` and `maintenance.wake()`, with no direct `syncer.poll()` or full-load call. Other direct mutations of Slack synchronization state must use this same ownership model.

`maintenance.status()` reports last reconciliation attempt/success, failure types and worker state. Observe and alert on failures and time since last successful completion. A local feed poll alone is **not** proof that remote reconciliation succeeded. Source exceptions are logged by type without credential-bearing messages. An unexpected scheduler failure stops visibly with a safe error; it is not silently discarded.

For a small demo estate, reconcile every 15 minutes. Measure actual API work against the installation's limits before promising a one-hour freshness bound. A full reconciliation refreshes all configured thread IDs to catch old edits and retention deletions. It is conservative and can be expensive; scalable incremental scans are Member 1's operational follow-up. A long-running scan delays subsequent work instead of overlapping it. Shutdown cannot cancel an in-flight scan: `stop()` waits only its bounded timeout and returns `False` if it is still running, so callers must not close its HTTP client prematurely.

## Scope and practical limits

- Each adapter instance represents one workspace and explicit conversation allowlist. `SlackWorkspaces` dispatches multiple instances through the existing `slack` registry slot. `account_for(user, "slack", tenant)` resolves only that workspace's verified account. Colliding channel/thread IDs in different workspaces remain distinct. Slack Connect identity equivalence is still outside scope.
- Configured channels, private groups, DMs and group DMs can be read only when the selected credentials/scopes allow it. The system does not auto-discover every private channel or employee DM. A central integration cannot ingest arbitrary private DMs simply because it is an admin or bot.
- Use a credential able to retrieve the intended channel threads for ingestion. Bot token capabilities differ by conversation type; granting a bot broad scopes does not make it a delegated human token. Missing capability fails closed.
- Current message text and thread context are supported. Attachments, binary files, reactions, rich block-only payloads, canvases and cross-workspace Slack Connect identity equivalence are outside this adapter's tested scope. Original Slack links remain accessible for richer context.
- Retention is delegated to what Slack returns during current reads. Absent messages are never restored from the local indexed copy. The simulator additionally enforces explicit retention windows.
- History and replies use cursor pagination with configurable budgets. An incomplete response fails rather than silently claiming the thread is complete. Two short retries are allowed during ingestion; authorization reads never retry. Long `Retry-After` responses are returned as unavailability so the scheduler can retry later.
- The adapter does not claim uninterrupted availability: revoked/missing user tokens, missing scopes, rate limits or expired authorization can withhold an answer safely. Repeated delegated checks are intentionally conservative and need measured latency/rate-budget tuning for a larger rollout.
- Crawl snapshots and event dedup metadata persist across restart. Production retention/cleanup for this metadata store must preserve active cursors and required dedup windows; no automatic cleanup policy is imposed here.

## Verification

```sh
python -m pytest tests/test_slack_member2.py tests/test_slack_runtime.py tests/test_slack_worker.py tests/contract -q
```

The added suite exercises native-account aliases, corporate-name impersonation, DM/public semantics, retention, edit/delete versions, multiple reply pages, duplicate messages, wrong workspace/user credentials, bot rejection, source errors, bounded 429 behavior, incomplete pagination, persistent crawl cursors, incomplete-scan deletion safety, exact per-message timestamps, signature tampering, timestamp replay, wrong installation, durable event dedup, malformed signed-event rejection, deletion after edits across restart, missed-event deletion reconciliation, per-user visible content and edit/delete/revocation routing. Runtime tests cover optional defaults, secret-name-only configuration, rotation and startup failures. Worker tests use fake clocks and synchronization events to verify due work, independent timers, serialized event/admin activity, safe outage reporting, bounded shutdown and visible fatal failures. HTTP tests are mock transport tests, not a live Slack certification.

## Official API references checked during implementation

- [Token types and user delegation](https://docs.slack.dev/authentication/tokens/)
- [Identity verification: auth.test](https://docs.slack.dev/reference/methods/auth.test/)
- [Conversation history: visibility, pagination and rate limits](https://docs.slack.dev/reference/methods/conversations.history/)
- [Thread replies: pagination and installation-specific rate limits](https://docs.slack.dev/reference/methods/conversations.replies/)
- [Request signature verification](https://docs.slack.dev/authentication/verifying-requests-from-slack/)
- [Message edit events](https://docs.slack.dev/reference/events/message/message_changed/)
- [Message deletion events](https://docs.slack.dev/reference/events/message/message_deleted/)

Slack's current method pages distinguish internal customer-built/Marketplace applications from newly commercially distributed non-Marketplace applications. Treat the actual app installation's rate limits as configuration constraints; a generic “Slack free tier” assumption is insufficient.


## Integrated multi-workspace and OAuth setup

Copy `examples/slack-workspaces.example.json` to a private configuration file, replace workspace/conversation IDs, and point `IB_SLACK_CONFIG` at it. Its credential fields are arbitrary **environment-variable names**; `.env.example` shows matching placeholder names. All tokens stay out of JSON and browser responses. Legacy one-workspace configuration remains supported.

Manual delegated credentials require trusted `User.accounts` entries such as `("slack:TTEAMONE", "TTEAMONE/UJANE")`. Alternatively enable the encrypted OAuth store using `IB_SLACK_TOKEN_KEY` (base64-encoded random 32-byte key), `IB_SLACK_CLIENT_ID`, `IB_SLACK_CLIENT_SECRET`, `IB_SLACK_REDIRECT_URI`, and optionally `IB_SLACK_INSTALL_DB`. With OAuth configured, `user_token_envs` may be `{}`. The ingestion credential and per-installation signing secret are still required.

The authenticated frontend/client calls `POST /api/slack/oauth/start` with `{"team":"TTEAMONE"}` and opens the returned authorization URL. The server consumes the callback state once, checks the returned workspace and `auth.test` delegated user identity, and encrypts access/refresh credentials. Disconnect deletes usable token material but keeps a revoked binding so a configured environment token cannot silently reconnect it. OAuth consent requires the workspace user's authorization; no consent was performed in this delivery. Run one worker, matching the in-process index and refresh lock. Use HTTPS in deployment and disable access logs to avoid recording OAuth callback codes.

Official references: [Slack tokens](https://docs.slack.dev/authentication/tokens/), [OAuth token exchange](https://docs.slack.dev/reference/methods/oauth.v2.access/), [token rotation](https://docs.slack.dev/authentication/using-token-rotation/). Requested delegated scopes cover channel/private-group/DM/group-DM history. Workspace/app distribution policies and rate limits still apply.

## Live acceptance evidence

Prepare a disposable fixture and trusted identities; copy and edit `examples/slack-live-checks.example.json`. Run:

```sh
python scripts/verify_live_slack.py --manifest your-live-fixtures.json --phase initial --json evaluation/reports/live-slack-initial.json
```

A workspace owner then performs the fixture edit, membership removal, deletion and retention transition. Run the corresponding `edited`, `revoked`, `deleted` and `expired` phases and save separate reports. The script only reads and never performs these mutations. Include each configured workspace and DM/public/private scopes. Placeholder/missing credentials produce NOT RUN (exit 2); failed assertions exit 1. Simulated and mocked HTTP tests are separate evidence. The current saved live report is NOT RUN.

Security integration note: seeded demo login and demo-token verification are disabled outside demo mode or when live Slack configuration is present. Member 1 must supply the trusted identity provider before real-source employee access or OAuth linking. This guard prevents the public `demo` password from opening real company data.
