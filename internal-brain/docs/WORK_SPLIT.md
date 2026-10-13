# Final-week work split (12 to 16 Oct 2026)

Three people, three coding agents, one repo. Each piece owns a set of files. If two pieces never edit
the same file, their PRs merge cleanly in any order. The rules at the bottom keep it that way.

| Piece | Owner | Branch prefix | Main goal |
|---|---|---|---|
| A | Mohnish (Member 1) | `mohnish/` | Live Confluence + Jira proof, permissions, sync, scale |
| B | Imaad (Member 2) | `imaad/` | Real model, answer quality evaluation, live Slack, employee UI, demo media |
| C | Punya (Member 3) | `punya/` | Audit, WORM checkpoints, server, live Drive, deployment + live URL, load tests |

## Before anyone starts

1. Mohnish's PR from `mohnish/atlassian-proof` touches `app/brain.py`, `app/index.py` and `app/audit.py`
   (performance only, explained in the PR). **Merge it into `main` first**, then everyone branches from the new `main`.
2. Everyone: `git pull`, `cd internal-brain`, set up the venv, run both suites (commands below). Expected: all pass,
   only the 4 S3 live tests skipped in fixture mode.
3. Live Atlassian personas are real accounts: **ravi = Punya (NTU email), asha = Imaad (NTU email)**, jdoe = Punya's
   gmail, priya = Imaad's gmail. Accept every Atlassian invite email you got. Never give your persona accounts admin rights.

## File ownership

Only the owner edits these. Paths are relative to `internal-brain/`.

**A, Mohnish:** `app/identity.py`, `app/sources/base.py`, `app/sources/registry.py`, `app/sources/{confluence,confluence_cloud,jira,jira_cloud,atlassian_client,cloud_polling,fake_atlassian,links,textconv,sim,world}.py`,
`app/sync.py`, `app/sync_state.py`, `app/seeding/*`, `scripts/{seed_atlassian,atlassian_live_check,atlassian_lifecycle_probe,scale_benchmark,write_account_map,show_index}.py`,
`docs/{ATLASSIAN_SETUP,SCALE,CONNECTOR_GUIDE,WORK_SPLIT}.md`, `tests/contract/*`, `tests/conftest.py`,
`tests/test_atlassian_*.py`, `tests/test_scale_and_groups.py`, `tests/test_lifecycle_probe.py`, `tests/test_write_account_map.py`,
`evaluation/reports/atlassian-*`.

**B, Imaad:** `app/{brain,grounding,evidence,llm,planner,guard,index,metrics}.py`, `app/sources/slack*.py`,
`app/{slack_oauth,slack_runtime,slack_worker}.py`, `app/static/{index.html,app.js,styles.css}`, any new vector search module,
`scripts/{evaluate,compare,judging_demo,benchmark,verify_live_slack}.py`, `evaluation/` (except `atlassian-*` reports),
`docs/{SLACK_MEMBER2,EVALUATION,WORKED_EXAMPLES}.md`, repo-root `TRIAL_QUESTION_BANK.md`, tests for these files.

**C, Punya:** `app/{audit,audit_policy,checkpoints,server,main,reliability,history}.py`, `app/sources/{gdrive,gdrive_live}.py`,
`app/static/{console.html,compliance.html}`, `deploy/*`, `requirements*.txt` and lock files, `scripts/{verify_audit,demo_member3,reset_demo}.py`,
`docs/{MEMBER3,TENCENT_REQUIREMENTS,EVIDENCE_PACK}.md`, `tests/test_member3_*.py`, tests for these files.

**Shared, append only:**
- `app/config.py`, `.env.example`: add your settings in a block headed `# --- Member N: <topic> ---`. Don't edit other blocks.
- `README.md`: edit only your own section. Mohnish updates the test count line at the end.
- Repo-root `SUBMISSION_SUCCESS_METRICS.md`: edit only the baseline cells of your own metric rows (list below).
- New dependency: Punya owns the lock file. Add the package to `requirements.txt` in your PR and say so; Punya regenerates the lock.

## Frozen interfaces (change only with the owner's OK)

- Connector contract in `app/sources/base.py`: `check`, `check_many`, `fetch`, `list_page`, `changes_since`, `acl_hint`, `PermissionResult`.
- Audit API: `audit.log`, `audit.log_many`, `audit.search`, `audit.reconstruct`, `audit.verify_report`.
- `Brain(world, sync_store, *, connectors, index, event_sink)`, the dict `Brain.ask` returns, `Brain.evidence`.
- HTTP routes the UI calls (`app/server.py` / `app/main.py`). Add routes freely; don't rename or reshape existing ones.

## Rules for every agent

1. Work on your own branch, small PRs into `main`, never push to `main`. Rebase on `main` every morning.
2. Run both suites before every commit, from `internal-brain/`:
   `python -m pytest -q` and `IB_ATLASSIAN_MODE=sim python -m pytest -q`. Add a test for every bug fix.
3. If your task needs a change in another piece's file: keep it under about 20 lines, explain why in the PR,
   and tag the owner. Bigger than that: ask the owner to do it.
4. Never print, log or commit secrets. They live in `internal-brain/.env` (gitignored).
5. Never fabricate numbers. Every number in a doc comes from a dated run, with the commit SHA and a label:
   `live`, `fixture`, `mock` or `synthetic`.
6. Never use em dashes in anything you write.
7. Code freeze **15 Oct 18:00 SGT**. After that only fixes, docs and reports. Submission due **16 Oct**.

## Metric ownership (from `SUBMISSION_SUCCESS_METRICS.md`)

| Owner | Metrics |
|---|---|
| A, Mohnish | G14 + L05/L06 (Confluence, Jira), G03/G04/G06 for Atlassian, P01, P04, F04/F05/F08/F09 for Atlassian, G12 final test run |
| B, Imaad | G11, G13, L01, L02, Q01 to Q18, L03, L04, L08 (only if Tencent VectorDB is required), P10, P11, U01 to U07 |
| C, Punya | G09, G10, G15, A01 to A09, L07, P07 to P09, P12 to P15, F09 for Drive, live URL |

## Submission tasks (handbook)

- **Everyone:** CodeBuddy / WorkBuddy is mandatory. Each of us takes at least one screenshot of a real CodeBuddy or
  WorkBuddy chat about this project (we need at least 3). Without them the project is not scored.
- **Imaad:** cover image 16:9 (380x216), title, blurb under 10 words, 5 to 8 minute demo video.
- **Punya:** architecture / trust-boundary diagram, live URL.
- **Mohnish:** description with business value, final GitHub source check, final test run.

---

## Prompt for Imaad's agent (Piece B)

> You're helping Imaad (Member 2) finish YieldGPT for the AI CAN DO IT Tencent Cloud Hackathon (Aspire FinTech
> track, "YieldGPT"), due 16 Oct 2026. Repo: github.com/Imaad001M/Tencent---YieldGPT. The team's code is
> in `internal-brain/`; the repo-root `app/` is an old copy, never edit it. Read `internal-brain/README.md`,
> `internal-brain/docs/WORK_SPLIT.md` (file ownership and rules, follow them exactly), repo-root
> `SUBMISSION_SUCCESS_METRICS.md` and `TRIAL_QUESTION_BANK.md` first.
>
> Scope: only the files listed for Piece B in WORK_SPLIT.md. Don't edit Piece A or C files except as the rules allow.
> Work on branch `imaad/final`, small commits, PR into `main`. Never use em dashes. Never commit secrets.
>
> 1. Baseline: `cd internal-brain`, venv, `pip install -r requirements.txt`, run `python -m pytest -q` and
>    `IB_ATLASSIAN_MODE=sim python -m pytest -q`. Fix anything broken in your files first.
> 2. Unmerged work: branch `origin/member2_UI` is a flat upload (files at repo root, 6 commits behind main) with
>    `vector_db.py`, `setup_vector_db.py`, `VECTOR_SEARCH.md`, `UI_WORKFLOW.md`, a newer `index.html`/`app.js` and
>    tests. Diff it against `internal-brain/` and port anything still valuable into the right paths inside
>    `internal-brain/` (UI into `app/static/`, vector search as a new module next to `app/index.py`). Don't merge
>    that branch as is. Vector search must never weaken permissions: candidates still go through the live
>    permission checks in `brain.py`, and no top-k cutoff may happen before authorization.
> 3. Real model (G13, L01, L02, P10): wire Tencent Hunyuan through the existing OpenAI-compatible adapter
>    (`app/llm.py`, `IB_LLM_*` settings). Ask Imaad to put the key in `.env`, never in chat. Run
>    `scripts/evaluate.py --mode live` and save the reports. Zero offline-stub generations in the live report.
> 4. Quality (Q01 to Q18, G11): turn the 160-question `TRIAL_QUESTION_BANK.md` into a frozen, versioned trial set and
>    an evaluation run with per-slice results (platform, persona, case type). Record what needs human scoring;
>    don't invent rubric scores.
> 5. Live Slack (L03, L04): follow `docs/SLACK_MEMBER2.md` with at least 2 real workspaces, run
>    `scripts/verify_live_slack.py`, save a redacted report. Give Imaad click-by-click steps for anything in a browser.
> 6. UI (U01 to U07): all 5 brief scenarios in 6 minutes or less, Lighthouse accessibility 95+, keyboard use,
>    390 / 768 / 1440 px layouts, every product reference says YieldGPT.
> 7. Media: cover image 16:9 (380x216), title, blurb under 10 words, a 5 to 8 minute demo video script.
> 8. Update only your README section and your metric rows, with dated, labelled numbers. Run both suites, open a PR,
>    and list anything only Imaad can do.

## Prompt for Punya's agent (Piece C)

> You're helping Punya (Member 3) finish YieldGPT for the AI CAN DO IT Tencent Cloud Hackathon (Aspire FinTech
> track, "YieldGPT"), due 16 Oct 2026. Repo: github.com/Imaad001M/Tencent---YieldGPT. The team's code is
> in `internal-brain/`; the repo-root `app/` is an old copy, never edit it. Read `internal-brain/README.md`,
> `internal-brain/docs/WORK_SPLIT.md` (file ownership and rules, follow them exactly), `internal-brain/docs/MEMBER3.md`
> and repo-root `SUBMISSION_SUCCESS_METRICS.md` first.
>
> Scope: only the files listed for Piece C in WORK_SPLIT.md. Don't edit Piece A or B files except as the rules allow.
> Work on branch `punya/final`, small commits, PR into `main`. Never use em dashes. Never commit secrets.
>
> 1. Baseline: `cd internal-brain`, venv, `pip install -r requirements.txt`, run `python -m pytest -q` and
>    `IB_ATLASSIAN_MODE=sim python -m pytest -q`. Fix anything broken in your files first.
> 2. Probing-alert bug (audit): `audit.log`/`audit.log_many` raise `probing_suspected` after 5 denied rows in
>    10 minutes, but `brain.py` writes a denied `authz_decision` row for every candidate a user can't see. At scale,
>    one normal question fires the alert. Reproduce with `app/seeding/scale.py` (`generate(7, pages=1250, issues=640,
>    threads=880, files=300, channels=22)`, jdoe asks "What's the latest runbook for the payment-service incident?").
>    Fix it so routine broad searches don't alert but targeted repeated attempts on restricted docs do. Keep one
>    audit row per decision (A02). Add tests.
> 3. WORM checkpoints (A09, G12): run the 4 skipped S3 Object Lock tests against `deploy/docker-compose.yml`
>    (MinIO) and, if possible, a real Tencent COS / S3 endpoint. Save the run output. Show 2 independent anchors.
> 4. Live Drive (L07): follow `docs/MEMBER3.md#live-drive` with a real Google account: shared and personal drive,
>    folder inheritance, file share, external share, edit, delete, revoke. Redacted, dated report. Click-by-click
>    steps for Punya for anything in a browser or Google Cloud console.
> 5. End to end and load (P07 to P09, P12 to P15, A07): measure end-to-end latency through `app.server:app` with at
>    least 100 warmed requests (p50/p95/max per phase), a 25-user 5-minute load test with zero leaks or audit gaps,
>    and audit search latency over 100,000 events. Label everything synthetic/fixture unless it is live.
> 6. Tencent (G15) and deployment: record the organizer's answer on mandatory Tencent services in
>    `docs/TENCENT_REQUIREMENTS.md` (ask Punya to get it; never invent it). Deploy to Tencent Cloud for a live URL,
>    demo mode with no real company data, secrets from the environment only.
> 7. Architecture / trust-boundary diagram for the submission (question to answer, every permission check,
>    the LLM as untrusted, audit + checkpoints).
> 8. Update only your README section and your metric rows, with dated, labelled numbers. Run both suites, open a PR,
>    and list anything only Punya can do.
