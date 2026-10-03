# Graph Report - internal-brain  (2026-10-04)

## Corpus Check
- 132 files · ~128,565 words
- Verdict: corpus is large enough that graph structure adds value.
- Unclassified: 8 file(s) not represented in the graph (top: (none) 3, .example 2, .css 1)

## Summary
- 1361 nodes · 3363 edges · 74 communities (64 shown, 10 thin omitted)
- Extraction: 93% EXTRACTED · 7% INFERRED · 0% AMBIGUOUS · INFERRED: 249 edges (avg confidence: 0.9)
- Token cost: 0 input · 0 output

## Community Hubs (Navigation)
- Web UI & Change Log
- Slack Runtime Startup
- Live Drive Connector
- Audit Checkpoint Stores
- Brain Pipeline (baseline)
- Integration Tests & Server
- Member 3 Demo Transcript
- Front-end app.js
- Audit Verifier
- Audit Reconstruction & Revocation
- Connector Contract & Confluence
- Main API Routes
- Slack OAuth Store
- Audit Core (hash chain)
- Guards, Index & Brain Docs
- Brain Ask Pipeline
- Evidence & Pipeline Tests
- Identity & Slack Metadata
- Slack Multi-Workspace Tests
- LLM Selection Layer
- Principals & Contract Suite
- Server Auth & Compliance API
- Connector ABC & Changes
- Audit Logging & Recovery
- Strict Grounding
- Evidence Serialization & Shutdown
- Simulated World & Slack Edits
- Slack Worker Tests
- Audited Delivery
- Synthetic Corpus & Registry
- Sync & Sync State
- Users & Audit Endpoints
- Employee UI Screenshots
- Contract Specs
- Syncer Apply Logic
- Slack Lifecycle Tests
- Member 1 Handoff Tests
- Audit Access Policy
- Simulated Slack Connector
- HTTP API Tests
- Config & Env
- Durable Sync Store
- Security Tests
- Context Assembly
- Source Errors & Reconcile
- Slack Workspaces
- Change Records
- Evaluation Runner
- Compare & Verify Scripts
- Slack Event Tests
- Drive Sim Tests
- Benchmarks
- Evidence Passages
- History
- Lexical Index
- Simulated Drive Connector
- Dependencies
- Brief Acceptance Tests
- Browser Tests
- Evidence Cache
- Test Fixtures
- Judging Demo
- Demo Login
- Connector check()
- Syncer Polling
- Evaluation Cases
- Slack Maintenance Worker
- Release-time Revocation Tests
- MinIO Init
- Evaluation Package
- Synthetic Benchmark
- Inert Text

## God Nodes (most connected - your core abstractions)
1. `User` - 54 edges
2. `World` - 49 edges
3. `search()` - 42 edges
4. `SourceUnavailable` - 42 edges
5. `Decision` - 39 edges
6. `Brain` - 37 edges
7. `SourceDoc` - 36 edges
8. `SlackLiveConnector` - 35 edges
9. `log()` - 30 edges
10. `verify_report()` - 30 edges

## Surprising Connections (you probably didn't know these)
- `test_oauth_state_single_use_expiry_and_encrypted_binding()` --uses--> `OAuthUnavailable`  [INFERRED]
  tests/test_integration_completion.py → app/slack_oauth.py
- `test_ping_raises_when_down()` --uses--> `SourceUnavailable`  [INFERRED]
  tests/test_drive_live.py → app/sources/base.py
- `ContractSpec` --uses--> `Decision`  [INFERRED]
  tests/contract/specs.py → app/sources/base.py
- `test_allowed_denied_and_unlinked()` --uses--> `Decision`  [INFERRED]
  tests/test_drive_live.py → app/sources/base.py
- `test_changes_map_to_upsert_and_delete_and_page()` --uses--> `ChangePage`  [INFERRED]
  tests/test_drive_live.py → app/sources/base.py

## Import Cycles
- None detected.

## Hyperedges (group relationships)
- **Tamper-evident audit integrity mechanism** — docs_member3_audit_hash_chain, docs_member3_s3_object_lock_checkpoints, docs_member3_checkpoint_semantics, docs_member3_verifier, docs_member3_sealed_audit_text [EXTRACTED 0.95]
- **Permission-checked answer release flow** — docs_handoff_member1_to_member3_connector_contract, docs_handoff_member1_to_member3_authz_decision_schema, docs_handoff_member1_to_member3_context_assembled, docs_handoff_member1_to_member3_release_recheck, docs_brief_review_passage_id_grounding [INFERRED 0.85]
- **Compose WORM checkpoint deployment** — deploy_docker_compose_minio, deploy_docker_compose_checkpoint_init, deploy_docker_compose_app_service [EXTRACTED 0.95]
- **Audit tamper-evidence and fail-closed flow** — docs_demo_transcript_member3_chain_verifier, docs_demo_transcript_member3_tamper_detection, docs_demo_transcript_member3_checkpoint_outage_fail_closed, docs_demo_transcript_member3_s3_object_lock, docs_demo_transcript_member3_restart_recovery [INFERRED 0.85]
- **Before/after evaluation reports** — evaluation_reports_baseline, evaluation_reports_current, evaluation_reports_comparison, evaluation_reports_offline_evaluation [EXTRACTED 1.00]
- **Permission-aware answer scenarios** — docs_worked_examples_unified_query, docs_worked_examples_negative_case_no_metadata_disclosure, docs_worked_examples_live_private_channel_revocation, docs_worked_examples_permission_recheck [INFERRED 0.85]
- **Ask, answer with citations, inspect source evidence** — docs_screenshots_employee_workspace_desktop_ask_brain_input, docs_screenshots_employee_answer_desktop_answer_panel, docs_screenshots_employee_answer_evidence_supporting_passages [INFERRED 0.85]

## Communities (74 total, 10 thin omitted)

### Community 0 - "Web UI & Change Log"
Cohesion: 0.05
Nodes (72): Compliance audit UI, Operations console with demo controls, Employee question UI, Integrated changed-file manifest, Integrated verification results (311 tests, 65/65, 28/28), app service, checkpoint-init bucket bootstrap service, minio WORM storage service (+64 more)

### Community 1 - "Slack Runtime Startup"
Cohesion: 0.05
Nodes (29): _build_workspace(), create_live_slack_from_env(), _env_name(), Optional Slack startup wiring. Configuration refers to environment names only.…, Return (connector, receiver) or None when IB_SLACK_CONFIG is unset. Malformed…, _required_secret(), Path, Persist a previously authenticated Events API envelope once. (+21 more)

### Community 2 - "Live Drive Connector"
Cohesion: 0.07
Nodes (25): DriveAPIError, DriveLiveConnector, _Gone, Client, Exception, Metadata the credential may see, or None (missing, trashed, or not permitted)., Re-read as the asker right before model input. Denied or absent -> None; outage…, Flatten permissions.list (inherited and shared-drive grants included) into the… (+17 more)

### Community 3 - "Audit Checkpoint Stores"
Cohesion: 0.07
Nodes (35): CheckpointError, from_env(), LocalCheckpointStore, Exception, Path, Response, Audit checkpoint storage: the trust boundary for the hash chain. Owner: Member…, independent_worm only if the bucket enforces COMPLIANCE-mode Object Lock. (+27 more)

### Community 4 - "Brain Pipeline (baseline)"
Cohesion: 0.07
Nodes (27): collections, Brain, The Internal Brain: one question, end to end. question | 1 input guard…, THE permission decision record. One per (query, document, stage). stage:…, enforce(), LLM safety in a permissioned world: nothing leaves without a source. Even with…, Entry, Index (+19 more)

### Community 5 - "Integration Tests & Server"
Cohesion: 0.08
Nodes (30): search(), fastapi_testclient, client(), installation(), fixture, Regression checks for the integrated Member 2 + Member 3 delivery., test_history_owner_expiry_and_checkpoint_gate(), test_history_rechecks_revocation_and_survives_preview_expiry() (+22 more)

### Community 6 - "Member 3 Demo Transcript"
Cohesion: 0.09
Nodes (41): Member 3 demonstration transcript (integrated, local_file), Member 3 demonstration transcript (s3_object_lock), Demo scene: platform admin cannot read question text, Demo scene: verifier checks chain against protected checkpoints, Demo scene: checkpoint store unreachable, Demo scene: compliance reconstructs the request, Demo scene: contractor asks for restricted material, Demo scene: employee cross-platform question (+33 more)

### Community 7 - "Front-end app.js"
Cohesion: 0.18
Nodes (33): announce(), api(), appendCitedText(), ask(), cancelAsk(), clearAnswer(), clearError(), clearSession() (+25 more)

### Community 8 - "Audit Verifier"
Cohesion: 0.17
Nodes (29): checkpoint(), _hash(), Commit the current head to the protected store. Raises CheckpointError on…, status: verified | failed | unverifiable. `verified_through` is the last…, _store(), verify_report(), multiprocessing, db() (+21 more)

### Community 9 - "Audit Reconstruction & Revocation"
Cohesion: 0.09
Nodes (25): parse_question(), Group matching document decisions back into full request stories: who asked…, Tiny NL -> filter parser for compliance questions. Swap for an LLM tool call…, reconstruct(), cited(), test_platform_outage_fails_closed_but_other_sources_still_answer(), test_repeated_revocation_withholds_answer(), test_revocation_during_generation_discards_and_rebuilds() (+17 more)

### Community 10 - "Connector Contract & Confluence"
Cohesion: 0.13
Nodes (13): Decision, str, THE CONNECTOR CONTRACT. Every platform adapter (Confluence, Jira, Slack, Drive)…, SourceDoc, ConfluenceConnector, Confluence connector. Owner: Member 1. Native model: space VIEW permission AND…, Google Drive connector. Owner: Member 3. Native model (simulated; mirrors Drive…, JiraConnector (+5 more)

### Community 11 - "Main API Routes"
Cohesion: 0.11
Nodes (26): ask(), AskIn, audit_query(), AuditIn, login(), LoginIn, poll_now(), private_responses() (+18 more)

### Community 12 - "Slack OAuth Store"
Cohesion: 0.13
Nodes (13): lifespan(), configure(), InstallationStore, OAuthUnavailable, RuntimeError, SlackOAuth, from_env(), None unless IB_DRIVE_CONFIG names a JSON file: {"domain": "...",… (+5 more)

### Community 13 - "Audit Core (hash chain)"
Cohesion: 0.12
Nodes (25): _append(), apply_retention(), _conn(), encryption_available(), head(), init(), _key(), _key_available() (+17 more)

### Community 14 - "Guards, Index & Brain Docs"
Cohesion: 0.11
Nodes (17): Member 2 pipeline built on Member 1's unchanged connector and audit contracts.…, Security guards on the way in (question), mid-way (retrieved content) and out…, redact(), Thread-safe lexical index. Candidate ranking is independent of hidden corpus…, Plan, Deterministic query planning: broad recall, explicit source limits, dated chat…, Encrypted, actor/workspace-bound delegated installations and OAuth state. No…, Live Google Drive (API v3) connector. Owner: Member 3. Same trust split as the… (+9 more)

### Community 15 - "Brain Ask Pipeline"
Cohesion: 0.14
Nodes (9): Brain, Permission decision records include each check phase and attempt. stage:…, fingerprint(), Measurement, Per-query wall-clock measurements; isolated across concurrent requests., timed(), decorate(), contextvars (+1 more)

### Community 16 - "Evidence & Pipeline Tests"
Cohesion: 0.10
Nodes (13): EvidenceUnavailable, passages(), LookupError, Keep complete sentences/lines. Never trim a negation or qualifier to fit a…, concurrent_futures, Security and quality regressions at Member 1/2/3 integration boundaries., test_audit_failure_prevents_answer_delivery(), test_evidence_actor_scope_revocation_and_version_recheck() (+5 more)

### Community 17 - "Identity & Slack Metadata"
Cohesion: 0.15
Nodes (19): account_for(), _atl(), _emp(), Identity: who is asking. One corporate identity maps onto every platform. In…, Optional Slack metadata without changing Member 1's SourceDoc contract., SlackSourceDoc, thread_text(), native_id() (+11 more)

### Community 18 - "Slack Multi-Workspace Tests"
Cohesion: 0.18
Nodes (19): test_multi_workspace_colliding_channel_ids_cannot_cross_read(), adapter(), FakeSlack, message(), Slack contract extensions, with real HTTP code exercised through MockTransport., test_delegated_visibility_does_not_restore_ingested_hidden_messages(), different_views(), test_live_crawl_paginates_and_survives_restart() (+11 more)

### Community 19 - "LLM Selection Layer"
Cohesion: 0.15
Nodes (19): model_source(), build_messages(), complete(), fallback(), finish(), Completion, configuration_problems(), estimated_cost() (+11 more)

### Community 20 - "Principals & Contract Suite"
Cohesion: 0.16
Nodes (19): principals(), Flat principal set, used ONLY for the fast index prefilter. Exact decisions…, PermissionResult, crawl(), parametrize, THE CONNECTOR CONTRACT SUITE. Every connector must pass every test here. Run…, Enumerate through the PUBLIC contract only, so this suite also runs against…, test_extra_cases() (+11 more)

### Community 21 - "Server Auth & Compliance API"
Cohesion: 0.15
Nodes (20): require(), health(), compliance_page(), compliance_requests(), ComplianceIn, health(), health_detail(), _policy() (+12 more)

### Community 22 - "Connector ABC & Changes"
Cohesion: 0.12
Nodes (9): ABC, Change, ChangePage, Connector, One page of native ids for the initial crawl. Returns (ids, next_token or None)., R13: raise SourceUnavailable if the platform is unreachable. Default: cheap…, SimulatedConnector, Workspace-isolated Slack dispatch, cursors, and event verification. (+1 more)

### Community 23 - "Audit Logging & Recovery"
Cohesion: 0.13
Nodes (15): key_source(), log(), severity: info | warning | alert. Raises if the row can't be committed (callers…, Run at startup: give every request/query without a terminal event an explicit…, recover_interrupted(), try_checkpoint(), config_problems(), fatal_problems() (+7 more)

### Community 24 - "Strict Grounding"
Cohesion: 0.13
Nodes (16): enforce(), normalized(), Strict extractive grounding. Citation validity is not semantic entailment. A…, parametrize, test_grounding_keeps_contradictions_attributed_instead_of_reconciling(), test_grounding_rejects_changed_numbers_dates(), test_grounding_rejects_negation_loss_and_unknown_refs(), test_grounding_removes_short_uncited_claim_even_next_to_valid_one() (+8 more)

### Community 25 - "Evidence Serialization & Shutdown"
Cohesion: 0.13
Nodes (10): Serialize an authorized manual incremental poll without a full crawl., Serialize an authorized manual poll with scheduled work., Serialize an authorized admin full refresh with all worker activity., Start once; an existing live worker is reused rather than duplicated., Request shutdown and join for at most timeout_s; report incomplete stop. This…, Non-blocking: coalesce verified events; never read a source in ACK., Perform due work once; fake clocks make scheduling testable without sleep.…, SlackMaintenance (+2 more)

### Community 26 - "Simulated World & Slack Edits"
Cohesion: 0.16
Nodes (4): (seq, ts, native_id, kind) for one platform after a sequence number., Edit one message, preserving its creation timestamp and thread context., Delete one reply; deleting all messages removes the indexed thread., World

### Community 27 - "Slack Worker Tests"
Cohesion: 0.16
Nodes (14): Clock, Serialized live Slack scheduling, tested with clocks and events, never sleep., test_authorized_refresh_is_serialized_and_failure_sanitized(), test_event_sink_failure_is_reported_without_source_details(), test_manual_poll_failure_does_not_leak_exception_text(), test_manual_poll_preserves_incremental_semantics_and_safe_failures(), test_manual_poll_preserves_poll_semantics_and_stopping_boundary(), test_periodic_schedule_reconciles_before_polling_and_event_does_not_defer() (+6 more)

### Community 28 - "Audited Delivery"
Cohesion: 0.12
Nodes (10): anyio, AuditedDelivery, _log(), Maintenance, observed_freshness(), _pct(), Operational reliability. Owner: Member 3. - AuditedDelivery: request receipt,…, Measured lag = applied_at - source_at, per platform and delivery path. Webhook… (+2 more)

### Community 29 - "Synthetic Corpus & Registry"
Cohesion: 0.16
Nodes (16): build_connectors(), make_corpus(), native_id(), queries(), Deterministic retrieval load fixture, not a simulation of native SaaS ACLs. The…, Yield (SourceDoc, ACL-hint) tuples using a local seeded PRNG., random, env() (+8 more)

### Community 30 - "Sync & Sync State"
Cohesion: 0.14
Nodes (7): Keeps the index fresh using ONLY connector-contract methods (no direct platform…, InMemorySyncStateStore, PlatformSyncState, Sync bookkeeping: where each platform's sync left off, and what changed.…, contextlib, sqlite3, typing

### Community 31 - "Users & Audit Endpoints"
Cohesion: 0.20
Nodes (16): _u(), User, audit_events(), audit_verify(), brain(), console(), evidence(), freshness() (+8 more)

### Community 32 - "Employee UI Screenshots"
Cohesion: 0.15
Nodes (17): Employee answer screen (desktop), Answer panel with inline S1-S4 citation chips, Connected sources: Confluence, Jira, Slack, Google Drive, Follow the evidence source list, Evidence extracts, no language model used, Source evidence side drawer (desktop), Access checked when source is opened, Supporting passages with original source link (+9 more)

### Community 33 - "Contract Specs"
Cohesion: 0.14
Nodes (6): ContractSpec, _drive_domain_share(), _drive_file(), _drive_limited_folder(), _drive_shared_drive_vs_direct(), Per-platform inputs to the shared contract suite. Each connector owner fills in…

### Community 34 - "Syncer Apply Logic"
Cohesion: 0.25
Nodes (4): Exception, Idempotent, fetch-on-notify. The change `kind` is a HINT, never trusted on its…, Syncer, loop()

### Community 35 - "Slack Lifecycle Tests"
Cohesion: 0.14
Nodes (7): fixture, parametrize, Mandatory Slack lifecycle contract; uses the same public adapter boundary. Live…, slack_contract(), edit(), slack_environment(), test_shared_slack_dm_and_public_scope_contract()

### Community 36 - "Member 1 Handoff Tests"
Cohesion: 0.22
Nodes (13): _syncer(), test_change_during_crawl_is_not_lost(), test_decision_records_are_schema_versioned(), test_deletion_leaves_a_tombstone(), test_denied_content_never_reaches_the_model(), test_every_decision_record_is_complete(), test_failed_initial_crawl_is_retried_before_incremental_sync(), test_forged_delete_webhook_cannot_remove_a_live_doc() (+5 more)

### Community 37 - "Audit Access Policy"
Cohesion: 0.25
Nodes (13): actors(), pseudonym(), Audit access policy: who may look at audit records, and how much they see.…, reconstruct(), resolve_pseudonym(), scope_for(), verify(), view_events() (+5 more)

### Community 38 - "Simulated Slack Connector"
Cohesion: 0.24
Nodes (5): The fixture directory resolves native identity, never the asker's name., SlackConnector, test_simulated_account_mapping_not_corporate_username(), test_simulated_dm_retention_and_public_scope(), test_simulated_edit_delete_changes_version_and_feed()

### Community 39 - "HTTP API Tests"
Cohesion: 0.18
Nodes (10): headers(), live_app(), fixture, parametrize, HTTP integration of optional live Slack, with no external credentials or calls., test_invalid_or_unpersisted_events_are_not_acknowledged(), test_live_session_disables_mutations_and_shared_secret_slack_route(), test_operational_counts_are_admin_only_and_poll_is_serialized() (+2 more)

### Community 40 - "Config & Env"
Cohesion: 0.22
Nodes (8): Central config. Everything comes from env vars so nothing secret lives in the…, Small dotenv reader: literal values only, no shell evaluation or expansion., os, pathlib, Clean reset of ISOLATED demo data (audit log, content key, local checkpoints,…, List what the knowledge index holds: uid, title, container, who the ACL hint…, shlex, shutil

### Community 41 - "Durable Sync Store"
Cohesion: 0.26
Nodes (4): Path, Durable store (survives restarts). Hardened by Member 3: - every write is one…, Delete change records older than max_age_s, except each doc's latest tombstone., SqliteSyncStateStore

### Community 42 - "Security Tests"
Cohesion: 0.27
Nodes (10): Legacy shape used by the original console and tests. Prefer verify_report()., verify(), _fill_log(), test_api_rights(), test_audit_detects_deleted_row(), test_audit_detects_full_chain_rewrite_via_anchor(), test_audit_detects_modified_row(), test_audit_detects_truncation_via_anchor() (+2 more)

### Community 43 - "Context Assembly"
Cohesion: 0.23
Nodes (11): assemble(), procedure_request(), Pack only live-approved records, preserving diversity within a relevant…, doc(), _mock_model(), test_index_concurrent_reads_and_writes(), work(), test_invalid_model_response_cannot_invent_claims() (+3 more)

### Community 44 - "Source Errors & Reconcile"
Cohesion: 0.18
Nodes (5): Raised by platform calls when the platform can't be reached or errors., SourceUnavailable, Every connector call goes through this. Simulates an unreachable platform., Connector, test_manual_cycles_and_admin_refresh_cannot_overlap_source_mutation()

### Community 46 - "Change Records"
Cohesion: 0.24
Nodes (5): ChangeRecord, SyncStateStore, Protocol, test_sync_store_concurrent_writes_and_retention(), writer()

### Community 47 - "Evaluation Runner"
Cohesion: 0.27
Nodes (10): load_env(), evaluate_grounding(), main(), markdown(), Path, Run reproducible offline evidence-quality checks, with isolated persistence.…, run(), write_report() (+2 more)

### Community 48 - "Compare & Verify Scripts"
Cohesion: 0.22
Nodes (7): argparse, Paired current/frozen lexical pipeline evaluation in separate processes., main(), Standalone audit verifier, run by an auditor independently of the web…, Read-only live Slack acceptance checks; never edits or deletes workspace data.…, subprocess, sys

### Community 49 - "Slack Event Tests"
Cohesion: 0.42
Nodes (11): event(), parametrize, receiver(), signed(), test_deleted_reply_after_edit_routes_correctly_across_restart(), test_duplicate_event_different_body_cannot_mutate_original(), test_events_edits_reply_delete_root_delete_and_revocation(), test_malformed_signed_event_is_safe_and_does_not_poison_dedup() (+3 more)

### Community 50 - "Drive Sim Tests"
Cohesion: 0.33
Nodes (9): itertools, Member 3: Drive change tracking and the handoff 5.4 cases beyond single…, setup(), test_acl_hint_covers_every_allowed_user_in_the_extended_estate(), test_domain_share_uses_the_drive_account_domain_not_the_employee_flag(), test_limited_access_folder_denies_contents_to_parent_only_access(), test_move_out_of_shared_folder_is_an_acl_change_and_sync_recomputes_the_hint(), test_removing_either_shared_drive_or_direct_access_path() (+1 more)

### Community 51 - "Benchmarks"
Cohesion: 0.27
Nodes (8): platform, resource, main(), markdown(), percentile(), Path, Measure local index search on a deterministic synthetic Company A estate. This…, run()

### Community 52 - "Evidence Passages"
Cohesion: 0.28
Nodes (7): passage_score(), Version-bound complete passages, bounded context, and actor-scoped citation…, Bounded term frequency + title coverage + exact identifiers; no corpus…, relevance(), _stem(), tokenize(), copy

### Community 53 - "History"
Cohesion: 0.33
Nodes (8): _answer_delivery(), HistoryUnavailable, list_history(), LookupError, Replay questions from successful deliveries, never return stored answer text.…, replay(), own_history(), test_preview_delivery_cannot_resurrect_withheld_answer()

### Community 54 - "Lexical Index"
Cohesion: 0.31
Nodes (3): Entry, Index, test_index_upsert_uses_snapshot_and_removes_old_postings()

### Community 56 - "Dependencies"
Cohesion: 0.42
Nodes (7): starlette, cryptography, fastapi, httpx, pydantic, pytest, uvicorn

### Community 57 - "Brief Acceptance Tests"
Cohesion: 0.28
Nodes (7): extended_runbook(), Regressions discovered while checking the complete challenge brief., test_denied_intermediate_stops_link_traversal(), test_final_preview_permission_check_is_audited(), test_missed_update_late_runbook_steps_survive_context_and_answer_caps(), test_model_cannot_drop_late_steps_from_requested_procedure(), test_three_link_hops_stitch_all_four_platforms()

### Community 58 - "Browser Tests"
Cohesion: 0.25
Nodes (4): ref_node_assert, ref_node_module, { chromium }, errors

### Community 60 - "Test Fixtures"
Cohesion: 0.38
Nodes (5): pytest, ask(), brain(), fresh_audit(), fixture

### Community 61 - "Judging Demo"
Cohesion: 0.38
Nodes (5): main(), markdown(), Execute all five brief scenarios in an isolated fictional company and save…, run(), tempfile

### Community 62 - "Demo Login"
Cohesion: 0.40
Nodes (6): login(), _sign(), verify(), current_user(), test_demo_credentials_cannot_access_live_sources(), test_demo_controls_are_off_outside_demo_mode()

### Community 63 - "Connector check()"
Cohesion: 0.33
Nodes (5): Exception, Platform-specific rule evaluation. Return (decision, reason_code, reason,…, Public entry point. Enforces R1 and R3; subclasses implement _check., R12: bounded, type-prefixed error text for the audit log., safe_error()

### Community 65 - "Evaluation Cases"
Cohesion: 0.50
Nodes (3): case(), Hand-curated expectations based on app/sources/world.py, not model outputs.…, Additional held-out wording and adversarial probes for credentialed runs.

### Community 66 - "Slack Maintenance Worker"
Cohesion: 0.50
Nodes (3): One serialized maintenance scheduler for live Slack and the shared syncer. Use…, logging, threading

### Community 67 - "Release-time Revocation Tests"
Cohesion: 0.50
Nodes (3): parametrize, test_change_during_release_fetch_discards_the_answer(), generate()

## Knowledge Gaps
- **17 isolated node(s):** `minio-init.sh script`, `{ chromium }`, `errors`, `Demo personas and source access`, `Extractive offline generation / evidence selector` (+12 more)
  These have ≤1 connection - possible missing edges or undocumented components. (Counts symbols only; 378 node(s) total have ≤1 connection when file, concept and rationale nodes are included.)
- **10 thin communities (<3 nodes) omitted from report** — run `graphify query` to explore isolated nodes.

## Suggested Questions
_Questions this graph is uniquely positioned to answer:_

- **Why does `Five worked examples from the challenge brief` connect `Member 3 Demo Transcript` to `Web UI & Change Log`, `Judging Demo`?**
  _High betweenness centrality (0.137) - this node is a cross-community bridge._
- **Why does `Brain` connect `Brain Ask Pipeline` to `Syncer Apply Logic`, `Integration Tests & Server`, `Config & Env`, `Connector Contract & Confluence`, `Main API Routes`, `Source Errors & Reconcile`, `Slack OAuth Store`, `Change Records`, `Guards, Index & Brain Docs`, `Evidence & Pipeline Tests`, `Evaluation Runner`, `Principals & Contract Suite`, `Lexical Index`, `Simulated World & Slack Edits`, `Evidence Cache`, `Test Fixtures`, `Judging Demo`, `Users & Audit Endpoints`?**
  _High betweenness centrality (0.085) - this node is a cross-community bridge._
- **Why does `SourceUnavailable` connect `Source Errors & Reconcile` to `Slack Runtime Startup`, `Slack Maintenance Worker`, `Live Drive Connector`, `Simulated Slack Connector`, `Connector Contract & Confluence`, `Slack Workspaces`, `Guards, Index & Brain Docs`, `Brain Ask Pipeline`, `Evidence & Pipeline Tests`, `Identity & Slack Metadata`, `Slack Multi-Workspace Tests`, `Principals & Contract Suite`, `Connector ABC & Changes`, `Evidence Serialization & Shutdown`, `Simulated World & Slack Edits`, `Slack Worker Tests`, `Connector check()`?**
  _High betweenness centrality (0.051) - this node is a cross-community bridge._
- **Are the 30 inferred relationships involving `User` (e.g. with `reconstruct()` and `resolve_pseudonym()`) actually correct?**
  _`User` has 30 INFERRED edges - model-reasoned connections that need verification._
- **Are the 10 inferred relationships involving `World` (e.g. with `Brain` and `lifespan()`) actually correct?**
  _`World` has 10 INFERRED edges - model-reasoned connections that need verification._
- **Are the 16 inferred relationships involving `SourceUnavailable` (e.g. with `Brain` and `SlackMaintenance`) actually correct?**
  _`SourceUnavailable` has 16 INFERRED edges - model-reasoned connections that need verification._
- **Are the 20 inferred relationships involving `Decision` (e.g. with `Brain` and `ConfluenceConnector`) actually correct?**
  _`Decision` has 20 INFERRED edges - model-reasoned connections that need verification._