# YieldGPT

Entry for the **Aspire FinTech track**, AI CAN DO IT Tencent Cloud Hackathon Singapore 2026.

> YieldGPT: a context-aware enterprise knowledge system with RBAC, security logging and audit trail.

It answers natural-language questions across **Confluence, Jira, Slack and Google Drive**, while every
piece of content respects the source platform's own permissions, and every retrieval and answer is
recorded in a tamper-evident, queryable audit trail.

This repo runs fully offline: the four platforms are simulated (`app/sources/world.py`) with realistic,
fictional Company A data, and the LLM has an offline stand-in until Hunyuan keys are added.

## Quick start

```bash
pip install -r requirements.txt
uvicorn app.main:app --reload        # open http://localhost:8000
python -m pytest -q                  # 90 tests: scenarios, security, connector contract, handoff
python -m pytest tests/contract -q   # just the connector contract every adapter must pass
```

Demo users (password `demo`):

| User | Who | Sees |
|---|---|---|
| `jdoe` | Backend engineer | Eng docs, MIG + PAY Jira (not security-level issues), channels she's in |
| `ravi` | SRE, payments on-call | Payment gateway space, private #payments-oncall and #mig-leads |
| `asha` | Security engineer | Security space, SEC project, security-level issues, #sec-incidents |
| `kim` | External contractor | Only the shared vendor channel and externally shared Drive folder |
| `priya` | Compliance officer | Can query the audit trail |
| `dana` | Platform admin | Demo controls + audit metadata only. Admin grants no source access and no audit content |

## Architecture

```
            +------------------------- TRUST BOUNDARY: YieldGPT ---------------------------+
 user --SSO-->  Identity (user, groups)                                                           |
            |       |                                                                             |
            |   question --> input guard --> planner --> fan-out search (unified index)           |
            |                                                  |                                  |
            |                                   prefilter on ACL hint (fast, may be stale)        |
            |                                                  |                                  |
            |                           link expansion (Jira -> Slack/Confluence/Drive)           |
            |                                                  |                                  |
            |   +---- LIVE native authz per doc  <----------------------------+                   |
            |   |     (Confluence space+page | Jira role+security level |    |                   |
            |   |      Slack membership | Drive folder-chain shares)     connectors ---> platform |
            |   |                                                              |     APIs         |
            |   +---- read-through freshness (newer version? use + reindex) --+                   |
            |                                                  |                                  |
            |                           poison scan --> rank + context budget                    |
            |                                                  |                                  |
            |  - - - - - - - - - - - - TRUST BOUNDARY: LLM (untrusted) - - - - - - - - - - - - -  |
            |                  LLM sees ONLY permitted, fresh, scanned chunks                     |
            |  - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - -  |
            |                                                  |                                  |
            |                grounding check --> output redaction --> answer + citations          |
            |                                                                                     |
            |   every step --> hash-chained audit log --> anchors --> external WORM storage       |
            +-------------------------------------------------------------------------------------+

 platforms --webhooks (signed)--> sync --> index        poller every 5 min (backstop) --> index
```

**Trust boundaries**
1. *Platforms to Brain*: webhooks must carry a valid signature. Content from platforms is **untrusted data**
   (it can contain injected instructions), so it's scanned before reaching the model.
2. *Brain to LLM*: the LLM is treated as untrusted. It never sees unauthorised content, and its output is not
   trusted until the grounding check passes.
3. *Brain to audit store*: the app can append but anchors live outside its control, so even the app itself
   can't silently rewrite history.

## How each scenario is solved

| # | Scenario | Mechanism | Code | Test |
|---|---|---|---|---|
| 1 | Unified query | Planner picks platforms, per-platform search, blended ranking, link expansion stitches Jira to Slack/Confluence/Drive, citations with URLs | `planner.py`, `brain.py` | `test_s1_*` |
| 2 | Freshness | Webhooks (seconds) + polling backstop (5 min) + read-through version check at query time, so a retrieved doc is never older than the source | `sync.py`, `brain._authorize_and_refresh` | `test_s2_*` |
| 3 | Negative cases | Prefilter + live native checks. Fully denied queries return the exact same text as "no matches", no citations, no hint | `connectors.py`, `grounding.py` | `test_s3_*` |
| 4 | Live revocation | Authorization is re-checked against the platform at query time, not trusted from the index | `connectors.check` | `test_s4_*` |
| 5 | Audit inquiry | Denormalised, hash-chained log; NL question to filters; reconstructs question, per-doc decisions and answer | `audit.py` | `test_s5_*` |

**LLM safety**: system prompt requires per-sentence citations, then `grounding.py` independently drops any claim
that cites nothing, cites a source not provided, or doesn't overlap with its cited source. Retrieved content is
scanned for injection before the model sees it.

**Security logging**: denials, injection attempts, poisoned content, rejected webhooks, app-permission failures,
and a *probing* alert when a user racks up many denials in 10 minutes.

## Key design trade-offs

- **Don't flatten permissions.** The index stores a coarse `acl_hint` for speed, but the decision always comes from
  each platform's native rules (`check()`). Flattening would lose things like Confluence restriction inheritance
  and Jira issue security levels.
- **Two-stage authz.** Prefilter keeps cost down; live check guarantees correctness. A stale hint that is *too
  permissive* is caught by the live check. A stale hint that is *too restrictive* (access granted after sync)
  hides the doc until the next sync. That is fail-closed, which is the right direction.
- **Live checks cost API calls.** In production, cache permission results with a short TTL (e.g. 60s) and
  invalidate on permission-change webhooks. The TTL is the explicit revocation window.
- **Freshness vs cost.** Webhooks for speed, polling for reliability, read-through for correctness on retrieved
  docs. Worst-case staleness equals the poll interval, well inside the 1-hour requirement.
- **Neutral refusals over helpful ones.** Saying "you don't have access to X" is friendlier but confirms X exists.
  We log the denial and say nothing.
- **Slack threads, not messages, are the unit.** Replies lose meaning without their root.
- **Time windows apply to Slack only.** "Last week" narrows conversations, but a year-old runbook is still the
  current runbook.

## Project layout

```
app/
  sources/base.py         THE connector contract (rules R1..R10)
  sources/{confluence,jira,slack,gdrive}.py   one adapter per platform, one owner each
  sources/world.py        simulated platforms with native permission models, change feed, outages
  sync_state.py           sync bookkeeping (cursors, change records, tombstones)
  audit_policy.py         who can read the audit trail, and how much
  identity.py             users, groups, tokens
  index.py                unified search index (TF-IDF now, vector DB later)
  sync.py                 webhooks + polling
  planner.py              platform routing + time windows
  brain.py                the end-to-end pipeline
  llm.py                  Hunyuan (OpenAI-compatible) or offline stub
  grounding.py            claim-level citation enforcement
  guard.py                injection detection + redaction
  audit.py                hash chain, anchors, queries, NL parser
  main.py                 FastAPI routes
  static/index.html       demo UI (ask, demo controls, audit console)
tests/                    scenario + security tests
```

## Plugging in real services

```bash
export IB_LLM_PROVIDER=openai_compatible
export IB_LLM_BASE_URL=...      # Hunyuan endpoint from your Tencent Cloud console
export IB_LLM_API_KEY=...
export IB_LLM_MODEL=...
```

Replacing a simulated platform means implementing the connector contract in `app/sources/base.py`
(`start_cursor`, `list_page`, `changes_since`, `fetch`, `acl_hint`, `_check`) against the real API and
passing `tests/contract`. Sync, retrieval and authorization only ever call those methods.

Team handoff notes live in `docs/`.

## Roadmap

1. Hunyuan for answers, planning (function calling) and audit NL queries
2. Embeddings + Tencent Cloud VectorDB, ACL hint as a metadata filter
3. One real connector (Slack or Confluence have free tiers) to prove the pattern beyond simulation
4. Permission cache with TTL + permission-change webhooks
5. Agent actions: "request access" routed to the resource owner, never auto-granted
6. Persistent index and DB (Postgres), rate limiting, real SSO
