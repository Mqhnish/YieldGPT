# Member 2 integration handoff

## Starting point and ownership

This delivery extends the latest supplied **Member 1 `internal-brain (2).zip`**. It does not reuse the earlier example project as its implementation base. Member 1's original `sources/base.py`, `identity.py`, `audit.py`, `audit_policy.py`, `sync.py`, `sync_state.py`, Confluence/Jira/Drive adapters and original handoff remain unchanged.

| Owner | Keep / integrate |
|---|---|
| Member 1 | Native source authorization, trusted identity/account mapping, non-Slack connectors, ingestion and shared connector contract |
| Member 2 | `brain`, `index`, `planner`, `evidence`, `grounding`, `llm`; Slack adapter/events/runtime/worker; employee UI; quality evaluation |
| Member 3 | Audit persistence, independently protected checkpoints, verification/compliance operations, production integration |

`app/main.py` is the shared merge point. Merge its additive routes/lifespan wiring rather than overwriting a teammate's later changes. `app/config.py` adds `IB_DATA_DIR`; existing configuration remains. Original UI is preserved byte-for-byte in `app/static/console.html`; new employee UI uses `index.html`, `styles.css`, `app.js`.

The supplied full ZIP can run immediately. If teammates have newer work, apply the accompanying patch to the Member 1 baseline on an integration branch and resolve overlapping files there. The patch contains code/text changes; the full ZIP also contains screenshots. See `CHANGES_MEMBER2.md` for exact changed and untouched files.

## Stable interfaces

```python
Brain(world=None, sync_store=None, *, connectors=None, index=None, event_sink=None)
Brain.ask(user, question) -> dict
Brain.evidence(user, query_id, ref) -> dict
Index.upsert(doc, acl_hint)
Index.search(query, platforms, since=None)
llm.complete(question, sources, asker) -> str
```

`connectors` is the complete platform-to-Connector dictionary. `index` is a compatible index implementation. `event_sink(actor, event, **fields)` defaults to `audit.log` for pipeline events; shared synchronization continues using Member 1's audit module. The constructor performs the initial load.

The unchanged SourceDoc/Connector contract remains authoritative. Slack optionally implements `read_authorized(user, native_id)` to fetch with the employee credential rather than the ingestion token. The pipeline uses that extension when present, and does not write the user's restricted projection into the shared index. A new `SlackSourceDoc` subtype adds exact per-message time/offset spans without altering `sources/base.py`.

A broad Slack ACL hint means "consider for native checking", never permission. Native identities can differ from corporate usernames. Permission results must not be cached across questions. Replacing a connector should still pass `tests/contract`; preserve source UIDs to retain citation/audit continuity.

## HTTP integration

Authentication remains the existing Bearer token interface. All `/api/` responses carry `Cache-Control: no-store, private`.

| Route | Contract |
|---|---|
| `POST /api/login` | Existing username/password contract retained |
| `GET /api/session` | User plus demo/source/generation mode; requires authentication |
| `POST /api/ask` | Existing question body and answer/citations/query_id/blocked fields retained; requires ask right |
| `GET /api/evidence/{query_id}/{ref}` | Current actor only; independently checks current permission/content; generic 404 for missing/expired/changed/revoked evidence |
| `GET /api/freshness` | Now admin-only because global indexed counts and health are operational information |
| `POST /api/slack/events` | Optional raw-body Slack signature verification, durable acceptance then worker wake; no employee token |
| `GET /api/slack/maintenance` | Admin-only reconciliation/worker health |
| `POST /api/sync/poll` | Existing admin API; live mode serializes through the maintenance worker |
| `POST /api/sim` | Existing simulated mutations; disabled whenever live Slack is configured |

Ask adds `status` (`answered`, `no_answer`, `blocked`), `quality.mode` (`extractive`, `model_selected`, `extractive_fallback`) and `quality.grounding`. Citations retain `ref`, `uid`, `platform`, `title`, `url`, `container`, `updated_iso`, and `version`. These additions are safe for consumers that ignore unknown fields. Do not expose raw index candidates or denied-source metadata to employees.

The cache holds bounded, short-lived citation excerpts scoped by actor and query. It never authorizes access. Evidence expires after five minutes or capacity eviction; the UI asks the employee to rerun the question. An answer already delivered cannot be recalled from someone's memory/browser by revocation.

## Audit handoff

Existing `authz_decision/1`, `context_assembled/1`, `answer_discarded/1` and `answer_returned/1` schemas are retained. Additive metadata:

- Authorization records may appear more than once per stage. `phase=before_read` / `after_read` and `attempt` distinguish boundary checks. Do not assume exactly one event per document/stage.
- Context entries add content fingerprint and selected passage IDs alongside uid/version; only authorized snapshots appear.
- Generation metadata records whether a model was used or the local fallback selected evidence.
- A changed version/content during final checking discards the attempt like revoked access. A second failed attempt is withheld.
- `evidence_viewed` records separately checked citation previews. `generation_fallback` explains safe provider failures using fixed reason codes.
- Live Slack adds maintenance health events with exception types, not arbitrary secret-bearing exception messages.

The answer is delivered only after the terminal audit call succeeds. Pipeline exceptions surface as generic HTTP 503 responses. Dropped drafts and retrieval decisions can be sensitive audit content; retain Member 1's audit read policy. The Member 2 pipeline does **not** replace Member 3's audit chain or implement protected external anchors.

## Answer quality and scope

Complete source passages are intentionally stricter than free-text summarization. The optional model chooses evidence IDs; server-side reconstruction prevents invented numbers or unsupported paraphrases from becoming factual output. Grounding establishes exact passage support, not truth, relevance perfection or a complete contradiction-resolution system. Preserve contradictory evidence and source dates; do not describe this as a semantic entailment engine.

The ranker uses per-document lexical scores to avoid hidden documents changing visible ranking statistics. It has no global pre-authorization top-k. Cross-platform diversity, exact IDs, light stemming/synonyms and link expansion improve recall. No embedding service or Tencent VectorDB is included. Measure live candidate authorization costs before a large deployment.

Slack windows use original message timestamps, not a thread's latest update time. "Last week" is rolling seven days; "last sprint" is fourteen days for this fixture. Time filtering applies to conversations, while current manuals remain eligible.

The current live Slack runtime covers one workspace and an explicit conversation allowlist. Multi-workspace production identity dispatch, OAuth installation/refresh storage and broader discovery require coordinated Member 1 work. Detailed limits and official API references are in `SLACK_MEMBER2.md`.

## Verification and demo sequence

1. Run `python -m pytest -q` (225 tests in this delivery).
2. Run `python scripts/evaluate.py` (65 curated cases; outputs can be saved using the README command).
3. Start the local app, choose Jane and ask the migration question. Open cited Jira/Slack/Drive evidence.
4. Choose Kim and ask for the Q3 breach incident report. Observe neutral absence and no metadata.
5. With Dana in `/console`, demonstrate a simulated permission change; ask again with the affected user. Do not present fixture behavior as live Slack verification.
6. Configure an approved live model/Slack test installation only after teammate identity mappings and secrets are supplied; run a separate live smoke test and report its results separately.

Saved browser screenshots and reproducible browser checks are included. The synthetic benchmark measures only local search over 19,700 generated records, not SaaS permission throughput, model latency or a freshness SLA. The default offline path remains usable without external services.
