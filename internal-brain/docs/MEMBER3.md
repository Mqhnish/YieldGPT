# Member 3: audit, reliability and the Drive adapter

Member 3 owns event persistence, checkpoint storage, the verifier, the Drive adapter, the compliance UI, deployment, recovery and submission assembly. The original Member 3 delivery built on `internal-brain-member2.zip`. This integrated revision changes shared files as recorded in CHANGES_INTEGRATED.md.

- **Entrypoint.** Use `uvicorn app.server:app` in place of `app.main:app`. The shared app is mounted under Member 3's layer; ask, previews and replay are protected.
- **Files Member 3 edits:** `app/audit.py`, `app/audit_policy.py`, `app/sync_state.py` (storage only), `app/sources/gdrive.py`, and the gdrive entry in `tests/contract/specs.py`.
- **New files:** `app/checkpoints.py`, `app/reliability.py`, `app/server.py`, `app/static/compliance.html`, `deploy/`, `scripts/{verify_audit,reset_demo,demo_member3}.py`, and `tests/test_member3_*.py`.

## Run it

**Local, no Docker.** This uses the local checkpoint file, which the verifier labels `local_only`.

```sh
python3 -m venv .venv && source .venv/bin/activate
pip install -r deploy/requirements.lock          # requirements.txt + cryptography, hash-pinned
python -m pytest -q                               # every test; the live S3 tests skip without an endpoint
uvicorn app.server:app --port 8000 --workers 1 --no-access-log                # employee UI at /, compliance UI at /compliance
python scripts/demo_member3.py                    # scripted backup demo on isolated data
```

**Deployment with WORM checkpoints (Docker Compose):**

```sh
python3 deploy/make_env.py                        # writes deploy/.env with fresh random secrets
docker compose -f deploy/docker-compose.yml up -d --build
curl http://127.0.0.1:8000/api/health             # {"status":"ok"}
```

Compose starts three services:

- `minio`: S3 storage. It uses Chainguard's MinIO build pinned by digest, because MinIO no longer publishes community images.
- `checkpoint-init`: creates the bucket with Object Lock in **COMPLIANCE** mode for 30 days, a put-only `brain-checkpoint-writer` and a read-only `audit-verifier`.
- `app`: runs as a non-root user with one worker. The image is built from the hash-locked requirements.

The app never receives the storage root credential.

The same code works with Tencent COS or AWS S3. Set `IB_CHECKPOINT_S3_ENDPOINT`, `_BUCKET`, `_PREFIX` and `_REGION`, plus the writer and reader keys, and apply the same two policies (`deploy/minio-init.sh`). URLs are path-style.

**Live S3 tests** (use the values from `deploy/.env`):

```sh
IB_TEST_S3_ENDPOINT=http://127.0.0.1:9000 IB_TEST_WRITER_KEY=... IB_TEST_WRITER_SECRET=... \
IB_TEST_READER_KEY=... IB_TEST_READER_SECRET=... IB_TEST_ROOT_KEY=... IB_TEST_ROOT_SECRET=... \
python -m pytest tests/test_member3_s3.py
```

**Clean reset of isolated demo data:**

- Local: `python scripts/reset_demo.py`. It refuses unless `IB_DEMO_MODE=1` and refuses when S3 checkpoints are configured.
- Compose: `docker compose -f deploy/docker-compose.yml down -v`. WORM means only removing the volume can reset the store, by design.

## Audit trail

### What is recorded

Every request to `/api/ask` gets a `request_id`. It's stored in its own chained column and returned as `X-Request-ID`. It links HTTP-level records to the brain's `query_id`, and it survives partial failures and restarts.

| Record | Written by | Meaning |
|---|---|---|
| `request_received` | middleware | Receipt, with the verified actor (`anonymous` if the token is invalid) |
| `query_received`, `query_planned` | brain | The question and the plan |
| `authz_decision/1` | brain | A decision per considered document, stage, phase and attempt, with reason code and version |
| `context_assembled/1` | brain | The exact `{uid, version, fingerprint, passage_ids}` sent to the model or selector, per attempt |
| `answer_discarded/1` | brain | A draft rebuilt or withheld after a release-time recheck |
| `answer_returned/1` | brain | Release outcome, answer, citations, generation mode |
| `request_failed` | middleware | Terminal failure: HTTP status and `query_id` when one exists |
| `response_withheld` | middleware | The answer was ready, but no protected checkpoint could be committed, so it was not released |
| `response_delivered` / `response_delivery_failed` | middleware | Bytes handed to the HTTP server transport, or the send raised. Client receipt itself isn't observable |
| `request_abandoned` | startup recovery | The request had no terminal record before a restart |
| `retention_applied` | maintenance | Sealed text older than the policy period was redacted |

Reconstruction keeps apart what a document was permitted for and what was actually used. `permitted_not_sent` lists documents allowed at the live stage that never reached the model context. `delivery` is one of `delivered`, `withheld`, `failed`, `delivery_failed`, `abandoned` or `unconfirmed`. `unconfirmed` means there's no HTTP delivery record, for example after a direct `Brain.ask` or a crash after release.

### Ordering under concurrency

Each append is one SQLite `BEGIN IMMEDIATE` transaction: it reads the head hash and inserts the row, in WAL mode with a busy timeout. This makes chain order safe across threads and uvicorn worker processes on one host, which is tested with 8 threads and 4 processes. Ids come from `AUTOINCREMENT`, so a deleted tail row is never reused and the next append exposes the gap.

### Checkpoint semantics (chosen explicitly)

1. **Release rule.** `/api/ask` returns 200 only after a checkpoint covering the request's `answer_returned` row is committed to the WORM store. The response is buffered until then. If the checkpoint fails, the answer is withheld: the client gets a 503 and a `response_withheld` record is written.
2. **Tail.** Events after the last checkpoint form the *uncheckpointed tail*, for example `response_delivered`, logins and audit reads. The maintenance thread commits the head every `IB_CHECKPOINT_INTERVAL_S` (30 s), and also every `ANCHOR_EVERY` rows. The verifier reports `verified_through` and `uncheckpointed_rows`, and never reports the tail as verified. `fully_verified` requires a verified status, an empty tail, and `independent_worm` assurance.

### Threat model

**Detected:** anyone who can write the audit database or its files but cannot delete or overwrite objects in the COMPLIANCE-mode bucket. This covers a DB operator, a restored backup, or a compromised host with the app's put-only credential.

| Tamper | Verifier result |
|---|---|
| Modify any row | `failed`: row modified |
| Delete a middle row | `failed`: row deleted (gap in ids) |
| Edit and recompute every hash | `failed`: chain rewritten (anchor mismatch) |
| Delete or replace a checkpointed tail, or swap in a whole new DB | `failed`: log truncated / anchor mismatch |
| Write a second checkpoint for an existing row | `failed`: conflicting checkpoints (equivocation) |
| Swap or alter sealed text | `failed`: sealed content altered |
| Delete sealed text early | `failed`: content deleted without retention record |
| Delete the uncheckpointed tail | Not provable. The tail was never claimed verified, and the next append exposes the id gap |
| Checkpoint store unreachable, or no checkpoints | `unverifiable` |

**Not covered:**
- An attacker who controls the app at write time and logs false events.
- Physical deletion of the storage volume by the storage administrator. That's outside the S3 API and its lock.
- A local checkpoint file. It's always labeled `local_only`, is never independent, and startup refuses it outside demo mode.

**Evidence:**
- `tests/test_member3_audit.py`
- `tests/test_member3_s3.py`: the live suite shows the writer and even storage root can't delete a locked version.
- `scripts/verify_audit.py`: exit codes 0 verified, 1 failed, 2 unverifiable. It runs outside the app with only the reader credential. Without the content key, sealed text is counted as `unchecked`.

### Protected text (audit policy, agreed with Member 1)

`question, answer, discarded_answer, dropped, title, reason, value, filters` are sealed with AES-GCM in `audit_content`. The chained row keeps only a salted digest, and the digest is also the AEAD associated data, which binds the ciphertext to its row. The key comes from `IB_AUDIT_CONTENT_KEY`, held by the app runtime. In demo mode without that variable, a key file is created beside the DB and health flags it. Anyone reading the DB files or backups sees identifiers and outcomes, not text.

Member 3 adopts the defaults in Member 1's handoff §4.3, recorded in `app/audit_policy.py`:

| Right | Who | Can see |
|---|---|---|
| `audit` | compliance (priya) | Everything, including reconstruction, pseudonym resolution and the verifier |
| `audit_meta` | platform admin (dana) | Event type, time, severity, platform, decision, pseudonymised actor, verifier. No question or answer text, document ids, titles, reasons or reconstruction |
| neither | everyone else | Nothing. Each attempt is logged as `audit_access_denied` |

- Every audit read is itself audited (`audit_accessed`), including verifier runs and pseudonym lookups.
- Text is redacted after `IB_AUDIT_TEXT_RETENTION_DAYS` (90) inside a single transaction that also writes `retention_applied`. The verifier accepts a redaction only when a chained retention record at least as long as the policy covers it.
- Decision metadata is kept for the deployment's lifetime.
- There's no self-service history for employees.
- `tests/test_member3_ops.py` sweeps every read route as admin, employee and contractor, and asserts the question and answer text never appear.

## Reliability

- **Configuration checks** (`reliability.config_problems`). Outside demo mode, startup is refused if any of these hold:
  - a secret is still at its development default
  - checkpoints are local, or checkpoint credentials are incomplete
  - `cryptography` is missing
  - the content key is a local file

  Running more than one worker is always a warning. The index is per process, so deploy with one worker; the audit chain is safe with N.
- **Health.** `GET /api/health` is public and returns only `ok`, `degraded` or `failing`. `GET /api/health/detail` is admin-only and covers:
  - audit writability
  - the last checkpoint's row and age, plus the uncheckpointed row count
  - store reachability and assurance
  - per-platform sync health
  - **observed freshness**: p50, p95 and max of `applied_at - source_at` per platform and path, from change records
  - recent failures and config findings

  The poll interval is shown as configuration, never as a freshness guarantee. Webhook lag measures time to apply after receipt; poll lag includes detection delay. In the simulated estate these numbers show the mechanism, not a production SLA.
- **Durable state.** `SqliteSyncStateStore` writes every change in a `BEGIN IMMEDIATE` transaction: atomic put, and an ordered append-only change log. `prune()` enforces change-log retention (`IB_SYNC_LOG_RETENTION_DAYS`, default 30) and keeps each document's latest tombstone. The index is rebuilt from the connectors at every start; that's the reliable rebuild path, and a platform that's down at startup is re-crawled before any incremental sync.
- **Restart recovery.** At startup `recover_interrupted()` closes every request that has no terminal record with `request_abandoned`, then commits a checkpoint.
- **Dependency locking.** `deploy/requirements.lock` is generated by `uv pip compile --generate-hashes` from `requirements.txt` plus `cryptography`. The image installs it with `--require-hashes`, and base images are pinned by digest.

## Google Drive adapter (`app/sources/gdrive.py`)

The adapter is simulated but contract-complete, and it passes the shared contract suite. It follows Drive API v3 semantics:

- **Identity.** The asker's linked Drive account. A domain share matches only when that account's email domain is `companya.example`; the corporate employee flag isn't used.
- **Sharing.** User, group, domain and `anyone` principals, plus a My Drive owner.
- **Inheritance.** File, then every ancestor folder, then shared-drive membership of the root folder.
- **Limited-access folders** (`limited: True`) stop inheritance. Someone who only reaches the file through a parent is DENIED `limited_access_folder`: metadata is visible, contents are not.
- **Trash.** `fetch()` returns `None`, the file is excluded from the crawl, `check()` returns DENIED `trashed`, and the change kind is `delete`. Untrashing is an upsert.
- **Moves** arrive as `acl` changes, and sync recomputes the ACL hint.

All five cases from handoff §5.4 are contract `extra` cases in `tests/contract/specs.py`. Removal of either access path, change kinds and sync effects are covered in `tests/test_member3_drive.py`.

**Limits:**
- There's no live Google Workspace adapter. The production mapping (permissions.list with supportsAllDrives, drives membership, changes.list with includeRemoved) is documented in the module docstring.
- The index prefilter uses corporate principals, so a contractor whose Drive account is on the company domain would be hidden by the prefilter. That fails closed.
- Link-only sharing ("anyone with the link") isn't modelled.

## Known limits (honest list)

- **Single host for the audit DB.** Ordering relies on SQLite locking, so multiple hosts would need Postgres or a sequencer.
- **Delivery precision.** "Delivered" means handed to the HTTP server. Client receipt isn't observable, and a delivered answer can't be recalled.
- **Tail window.** Up to 30 s of non-answer events can sit in the uncheckpointed tail, and it's labeled as such.
- **Webhook payload shape is still simulated.** `/api/webhooks/{platform}` now checks each platform's own scheme with its own secret (`IB_WEBHOOK_SECRET_<PLATFORM>`): Jira and Confluence `X-Hub-Signature: sha256=<HMAC-SHA256 of the raw body>`, Drive `X-Goog-Channel-Token`. Slack keeps its signed Events endpoint. The body is still `{native_id, kind}`; live adapters must map the native payload (Jira `issue.key`, Drive `changes.list` after a notification). Atlassian Connect apps sign with JWT instead and would need that check. Replays only trigger a re-fetch that sync confirms against the source.
- **Canonical entrypoint.** Direct `app.main` startup is rejected. Deploy with `app.server:app`, as the Dockerfile does.
