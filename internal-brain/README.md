# Internal Brain — integrated team delivery

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

The integrated automated suite passes **326 tests**, with four real-S3 checks skipped because no endpoint is configured.

See [the comparison](evaluation/reports/comparison.md), [current per-case measurements](evaluation/reports/current.json), [integration review](docs/INTEGRATION_REVIEW.md) and [evaluation methods](docs/EVALUATION.md). The 19,700-object synthetic benchmark measures the local index only.

## Approved model and live evaluation

Edit `.env`: set `IB_LLM_PROVIDER=openai_compatible`, `IB_LLM_REQUIRE_LIVE=1`, and replace `IB_LLM_BASE_URL`, `IB_LLM_MODEL`, `IB_LLM_API_KEY` with your approved account settings. The adapter calls `/chat/completions`. HTTPS is required except on localhost. Price settings are optional actual per-million-token rates; missing prices or usage are recorded as unknown, never a fictitious zero cost.

```sh
python scripts/evaluate.py --mode live --json evaluation/reports/live-model.json --markdown evaluation/reports/live-model.md
```

This runs 65 regression cases plus 13 additional paraphrase/adversarial probes, and the grounding category. Answerable cases must actually use the remote model. Offline fallback cannot produce a live pass. Missing credentials return exit code 2 and a **NOT RUN** report. Failed checks return 1. Model HTTP latency, total model elapsed time, retries, token usage and estimated cost are recorded separately from authorization/read and final release checks in the audit and JSON results. Timings are nested and must not be summed.

The current saved live report is **not run**, because credentials remain placeholders. See [Tencent requirements and model setup](docs/TENCENT_REQUIREMENTS.md). Exact organizer service requirements still need confirmation before deployment.

## Slack and team integration

[Slack setup](docs/SLACK_MEMBER2.md) covers multiple workspaces, `TEAM/USER` identities, `TEAM/CHANNEL/THREAD` resource IDs, delegated reads, encrypted OAuth installs, single-use state, refresh rotation, signed events and 15-minute reconciliation. The common contract suite exercises DMs, public-channel scope, edits, deletion and retention on simulated and mocked HTTP implementations. A separate [live verifier](scripts/verify_live_slack.py) records real-workspace checks once configured.

Member 3’s independent S3 Object Lock checkpoint implementation is included. Default local checkpoints are explicitly weaker; live WORM tests need a configured service. Read [Member 3 operations](docs/MEMBER3.md) and [the integration handoff](docs/HANDOFF_MEMBER2.md).

## Boundaries

- Production SSO is still a teammate integration. The seeded demo identity directory must be replaced before connecting real employees or sensitive company data.
- Confluence and Jira remain simulated. Drive is simulated unless `IB_DRIVE_CONFIG` points at a JSON file, which switches on the live Drive API v3 connector (`app/sources/gdrive_live.py`, see [Live Drive](docs/MEMBER3.md#live-drive)); it has only been tested against a fake Drive API. Real Slack/Drive/model/OAuth/WORM deployments have not been verified.
- Conversation allowlists intentionally bound ingestion; multi-workspace support does not grant access to every private channel or DM. Slack itself authorizes every delegated read.
- Search uses controlled lexical expansion and authorized link traversal, without embeddings. Broad queries can require many native permission calls; measure live throughput before scaling.
- Grounding proves exact passage support, not source truth, complete answers, semantic entailment or perfect contradiction handling. Source dates remain visible.
- Revocation takes effect at subsequent checks. Previously delivered text cannot be recalled, and the final distributed check-to-delivery race and timing side channels remain.
- Freshness depends on successful events, polling, reconciliation, API budgets and source availability. There is no unconditional one-hour guarantee during outages.

Security integration note: seeded demo login and demo-token verification are disabled outside demo mode or when live Slack configuration is present. Member 1 must supply the trusted identity provider before real-source employee access or OAuth linking. This guard prevents the public `demo` password from opening real company data.
