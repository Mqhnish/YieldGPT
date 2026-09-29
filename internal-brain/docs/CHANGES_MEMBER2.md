# Member 2 change manifest

Base archive SHA-256: `f9fcb048b23fd9bef65130b1c2373d03b87cedc8fb6f6baa48a72dcbd7cb0304`

The protected Member 1 interfaces and non-Slack adapters listed below are byte-identical to the supplied archive. The original UI is preserved byte-identically at `app/static/console.html`. No baseline source files were removed.

## Protected, unchanged files

- `app/sources/base.py`
- `app/identity.py`
- `app/audit.py`
- `app/audit_policy.py`
- `app/sync.py`
- `app/sync_state.py`
- `app/sources/confluence.py`
- `app/sources/jira.py`
- `app/sources/gdrive.py`

## Modified existing files

- `README.md`
- `app/brain.py`
- `app/config.py`
- `app/grounding.py`
- `app/index.py`
- `app/llm.py`
- `app/main.py`
- `app/planner.py`
- `app/sources/slack.py`
- `app/sources/world.py`
- `app/static/index.html`
- `requirements.txt`
- `tests/conftest.py`
- `tests/test_member1_handoff.py`

## Added files

- `.env.example`
- `.gitignore`
- `app/evidence.py`
- `app/slack_runtime.py`
- `app/slack_worker.py`
- `app/sources/slack_content.py`
- `app/sources/slack_events.py`
- `app/sources/slack_live.py`
- `app/static/app.js`
- `app/static/console.html`
- `app/static/styles.css`
- `docs/BRIEF_REVIEW.md`
- `docs/EVALUATION.md`
- `docs/HANDOFF_MEMBER2.md`
- `docs/SLACK_MEMBER2.md`
- `docs/WORKED_EXAMPLES.md`
- `docs/screenshots/employee-answer-desktop.png`
- `docs/screenshots/employee-answer-evidence.png`
- `docs/screenshots/employee-answer-mobile.png`
- `docs/screenshots/employee-workspace-desktop.png`
- `evaluation/__init__.py`
- `evaluation/cases.py`
- `evaluation/reports/judging-scenarios.json`
- `evaluation/reports/offline-evaluation.json`
- `evaluation/reports/offline-evaluation.md`
- `evaluation/reports/synthetic-benchmark.json`
- `evaluation/reports/synthetic-benchmark.md`
- `evaluation/synthetic.py`
- `examples/slack-config.example.json`
- `requirements-lock.txt`
- `scripts/benchmark.py`
- `scripts/evaluate.py`
- `scripts/judging_demo.py`
- `tests/browser/README.md`
- `tests/browser/employee-ui.mjs`
- `tests/test_brief_acceptance.py`
- `tests/test_evaluation_data.py`
- `tests/test_member2_http.py`
- `tests/test_member2_pipeline.py`
- `tests/test_member2_review.py`
- `tests/test_slack_member2.py`
- `tests/test_slack_runtime.py`
- `tests/test_slack_worker.py`
- `docs/CHANGES_MEMBER2.md`

The full ZIP includes screenshots. The text patch omits PNG binaries; use the ZIP for those. Runtime databases, API keys, dependency environments and browser caches are excluded.
