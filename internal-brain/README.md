# YieldGPT: integrated team delivery

This project integrates Member 2’s retrieval and answer checks with the supplied **Tencent---YieldGPT-main.zip**, including Member 3’s encrypted audit log, protected checkpoint adapter, compliance console and delivery controls. The previous project is preserved separately.

The default is a local Company A demonstration: Confluence, Jira, Slack and Drive fixtures with different native permission rules. A model can select evidence passages; the server reconstructs the factual text and citations from authorized source snapshots. Real credentials are intentionally placeholders.

## Run locally

Python 3.11+; this delivery was tested with Python 3.14.

```sh
python3 -m venv .venv
source .venv/bin/activate
python -m pip install -r requirements-lock.txt
cp .env.example .env
python -m uvicorn app.server:app --host 127.0.0.1 --port 8000 --workers 1 --no-access-log
```

Open http://127.0.0.1:8000. On Windows use `.venv\Scripts\activate`. Choose a demo persona; passwords are `demo`. `.env` loads automatically, and exported variables take precedence. Never commit real `.env` files. Use `IB_ENV_FILE` to select another settings file.

**Always use `app.server:app`.** Direct `app.main` startup is rejected. Questions, citation previews and replayed answers pass through Member 3’s checkpoint-before-release middleware. A checkpoint failure returns a generic 503 and withholds the answer.

| Account | Role | Source access example |
|---|---|---|
| jdoe | Backend engineer | Engineering documentation and team conversations |
| ravi | Payments on-call | Payments runbooks and private on-call conversations |
| asha | Security engineer | Restricted security reports |
| kim | Contractor | Vendor-shared material only |
| priya | Compliance officer | Audit content; no automatic access to source documents |
| dana | Platform administrator | Operations and audit metadata; no automatic source access |

Ask about migration progress and Slack blockers, payment-outage follow-up tickets, or ADR-17. Open a citation. Use **Previous questions** to rerun a prior question with current permissions and current content. The history list exposes timestamps and query IDs, never old answers or source titles. It survives server restart and is separate from the five-minute citation-preview cache. Audit-content retention limits replay availability.

Operations are at `/console`; the integrated compliance screen is `/compliance`. `python scripts/show_index.py [uid]` lists what the index holds (or prints a document's text) on isolated data.

## Verification and measured results

```sh
python -m pytest -q
python scripts/compare.py
python scripts/evaluate.py --json evaluation/reports/offline-evaluation.json --markdown evaluation/reports/offline-evaluation.md
python scripts/benchmark.py --size full --json evaluation/reports/synthetic-benchmark.json --markdown evaluation/reports/synthetic-benchmark.md
python scripts/judging_demo.py --markdown docs/WORKED_EXAMPLES.md --json evaluation/reports/judging-scenarios.json
```

The controlled comparison runs the original Member 1 lexical pipeline and the current pipeline on the **same** current fixtures and 65 question expectations. It measures **50/65 → 65/65** passing questions and **85.7% → 100%** required-source recall. The separate 28-case grounding category measures **15/28 → 28/28**, with false accepts falling from 13 to zero. Neither pipeline exposed unauthorized citations/context in this fixture set. This is a reconstructed offline comparison, not historical production evidence.

The integrated automated suite passes **441 tests, 5 skipped** (default `fixture` mode, 14 Oct 2026; 439 on the recorded clean-checkout run, plus the live-scenario module tests); the five skips are live S3 Object Lock tests that need an endpoint and passed live on 12 Oct. `IB_ATLASSIAN_MODE=sim python -m pytest -q` runs the same suite against the in-process simulator (428 pass, 18 skip: the S3 checks plus fixture-only checks that drive the HTTP connectors). CI runs both on every PR. Details: [final-test-run.md](evaluation/reports/final-test-run.md).

See [the comparison](evaluation/reports/comparison.md), [current per-case measurements](evaluation/reports/current.json), [integration review](docs/INTEGRATION_REVIEW.md) and [evaluation methods](docs/EVALUATION.md). The 19,700-object synthetic benchmark measures the local index only.

## Approved model and live evaluation

Edit `.env`: set `IB_LLM_PROVIDER=openai_compatible`, `IB_LLM_REQUIRE_LIVE=1`, and replace `IB_LLM_BASE_URL`, `IB_LLM_MODEL`, `IB_LLM_API_KEY` with your approved account settings. The adapter calls `/chat/completions`. HTTPS is required except on localhost. Price settings are optional actual per-million-token rates; missing prices or usage are recorded as unknown, never a fictitious zero cost.

```sh
python scripts/evaluate.py --mode live --json evaluation/reports/live-model.json --markdown evaluation/reports/live-model.md
```

This runs 65 regression cases plus 13 additional paraphrase/adversarial probes, and the grounding category. Answerable cases must actually use the remote model. Offline fallback cannot produce a live pass. Missing credentials return exit code 2 and a **NOT RUN** report. Failed checks return 1. Model HTTP latency, total model elapsed time, retries, token usage and estimated cost are recorded separately from authorization/read and final release checks in the audit and JSON results. Timings are nested and must not be summed.

The current saved live report is **not run**, because credentials remain placeholders. See [Tencent requirements and model setup](docs/TENCENT_REQUIREMENTS.md). Exact organizer service requirements still need confirmation before deployment.

## Confluence and Jira (Member 1)

Confluence and Jira run through **real REST connectors** (`app/sources/confluence_cloud.py`, `jira_cloud.py`) in every mode except `sim`. `IB_ATLASSIAN_MODE` picks where they point:

| Mode | What runs |
|---|---|
| `fixture` (default) | Real HTTP connectors against an in-process fake Atlassian site built from the demo company |
| `live` | Real HTTP connectors against a real Atlassian Cloud site (Standard plan needed for restrictions and issue security) |
| `sim` | The old in-process simulator, no HTTP |

Permission decisions are Atlassian's own: Confluence's content permission check for the asker's accountId, and Jira's bulk `permissions/check` (one call per pipeline phase for every issue in it). Every phase of the pipeline (before read, after read, link hops, release) batches its checks per platform under one shared deadline. Confluence checks also report the page version, so an edit landing between read and recheck is caught. Errors, timeouts and rate limits fail closed; tokens never appear in errors and are never sent off-site. Polling uses an overlap window with dedupe, plus deletion reconciliation that holds back suspicious mass deletes.

**Verified live (13 Oct 2026, real Atlassian Cloud site, Standard trial, four teammates as personas, kim without an account):**

| Check | Result | Report |
|---|---|---|
| Conformance: every persona x every seeded page and issue, decided by Atlassian | **84/84** | [atlassian-live-check.md](evaluation/reports/atlassian-live-check.md) |
| Jira issue security level (demo PAY-110): hidden from ravi who can browse the project, shown to asha | pass, no code workaround needed | same |
| Brief scenarios S1 (unified query), S3 (negative cases), S5 (audit inquiry) asked as each persona | **14/14** | [atlassian-live-scenarios.md](evaluation/reports/atlassian-live-scenarios.md) |
| Lifecycle probe through the real pipeline: create, edit, revoke, delete on Confluence and Jira, plus an inherited page restriction and a Jira status change and comment | **21/21** | [atlassian-live.md](evaluation/reports/atlassian-live.md) |
| New object retrievable (immediate poll) | Confluence 16.9 s, Jira 3.1 s | same |
| Revoked user denied on the very next query, no reindex | Confluence 0.27 s, Jira 0.18 s (query time) | same |
| Denial held (3 in a row) after the platform confirmed the revoke | Confluence 3.2 s, Jira 3.0 s, never re-allowed | same |
| Child page of the restricted page denied from its first query (inherited restriction) | pass | same |
| Denial identical to a document that never existed | pass on both | same |
| Deleted object not served on the next query, then removed from the index | pass on both | same |

These are single dated runs on a small seeded site, not throughput measurements. While permission schemes were being edited, Jira's bulk permission check briefly gave different answers for the same user seconds apart; the pipeline's release re-check stops a short stale "allowed" (tested), and the probe measures how long a revoke takes to hold.

- Live setup, seeding a real site with the demo company, and the read-only conformance check: [docs/ATLASSIAN_SETUP.md](docs/ATLASSIAN_SETUP.md)
- Brief-sized estate (about 30,000 documents) and benchmark: [docs/SCALE.md](docs/SCALE.md)
- Connector pattern for other platforms: [docs/CONNECTOR_GUIDE.md](docs/CONNECTOR_GUIDE.md)

## Slack and team integration

[Slack setup](docs/SLACK_MEMBER2.md) covers multiple workspaces, `TEAM/USER` identities, `TEAM/CHANNEL/THREAD` resource IDs, delegated reads, encrypted OAuth installs, single-use state, refresh rotation, signed events and 15-minute reconciliation. The common contract suite exercises DMs, public-channel scope, edits, deletion and retention on simulated and mocked HTTP implementations. A separate [live verifier](scripts/verify_live_slack.py) records real-workspace checks once configured.

## Audit, checkpoints and load (Member 3)

Every answer is checkpointed to an S3 Object Lock (COMPLIANCE) store before release; set a second store with the `_2` variables and every checkpoint goes to both (`docker compose --profile second-anchor up -d` starts one locally). Default local-file checkpoints are explicitly weaker. Architecture and every permission check: [docs/architecture-trust-boundaries.png](docs/architecture-trust-boundaries.png). Operations: [docs/MEMBER3.md](docs/MEMBER3.md).

Measured 12 Oct 2026 on Apple Silicon macOS (15 CPUs); fixture data and stub model unless stated:

| Check | Result | Report |
|---|---|---|
| Live WORM tests, two local MinIO instances (Object Lock COMPLIANCE) | 18/18 pass; a fully forged anchor 1 still fails verification against anchor 2 | [member3-worm-checkpoints.txt](evaluation/reports/member3-worm-checkpoints.txt) |
| 25 users x 5 min, local uvicorn, MinIO checkpoints | 19,223/19,223 answers, 63.9 answers/s, 0 permission leaks, 0 audit gaps, 0 cross-user evidence hits | [member3-load-test.md](evaluation/reports/member3-load-test.md) |
| End to end, 120 warmed requests, MinIO checkpoints | p50 37.5 ms, p95 50.9 ms; authorization/read p95 17.1 ms; audit/release p95 26.2 ms; citation preview p95 28.2 ms | [member3-e2e-latency-minio.md](evaluation/reports/member3-e2e-latency-minio.md) |
| Compliance search over 100,005 synthetic events | worst p95 950 ms (target 2 s) | [member3-audit-search-latency.md](evaluation/reports/member3-audit-search-latency.md) |

Not yet done: live Google Drive lifecycle (needs a Workspace test domain), a public Tencent-hosted URL, the organizer's written answer on mandatory Tencent services (`docs/TENCENT_REQUIREMENTS.md` says pending), and anchors at two separate providers. Steps: [docs/MEMBER3_SETUP.md](docs/MEMBER3_SETUP.md). Integration history: [docs/HANDOFF_MEMBER2.md](docs/HANDOFF_MEMBER2.md).

## Boundaries

- Production SSO is still a teammate integration. The seeded demo identity directory must be replaced before connecting real employees or sensitive company data.
- Confluence and Jira use real REST connectors, verified on a real Atlassian Cloud site (Standard trial) on 13 and 14 Oct 2026: conformance 84/84, brief scenarios 14/14 and lifecycle 21/21 (see above). Webhooks are not wired for Atlassian (polling plus read-through only), and the live site is a small seeded demo, not a 12,000-page estate; scale numbers come from the synthetic fixture run in [docs/SCALE.md](docs/SCALE.md). Drive is simulated unless `IB_DRIVE_CONFIG` points at a JSON file, which switches on the live Drive API v3 connector (`app/sources/gdrive_live.py`, see [Live Drive](docs/MEMBER3.md#live-drive)); it has only been tested against a fake Drive API. Real Slack/Drive/model/OAuth/WORM deployments have not been verified.
- Conversation allowlists intentionally bound ingestion; multi-workspace support does not grant access to every private channel or DM. Slack itself authorizes every delegated read.
- Search uses controlled lexical expansion and authorized link traversal, without embeddings. Broad queries can require many native permission calls; measure live throughput before scaling.
- Grounding proves exact passage support, not source truth, complete answers, semantic entailment or perfect contradiction handling. Source dates remain visible.
- Revocation takes effect at subsequent checks. Previously delivered text cannot be recalled, and the final distributed check-to-delivery race and timing side channels remain.
- Freshness depends on successful events, polling, reconciliation, API budgets and source availability. There is no unconditional one-hour guarantee during outages.

Security integration note: seeded demo login and demo-token verification are disabled outside demo mode or when live Slack configuration is present. Member 1 must supply the trusted identity provider before real-source employee access or OAuth linking. This guard prevents the public `demo` password from opening real company data.
