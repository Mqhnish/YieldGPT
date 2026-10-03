# Integrated changes against supplied Member 3 project

Base: `Tencent---YieldGPT-main.zip`; SHA-256 `d3c05cb39591331f3067136477f66fc938ed42e3ba49e836071ec5b8e9efe184`.

Use the full ZIP for the complete runnable project. The companion text patch targets the `internal-brain/` folder from the supplied archive; check it on an integration branch before applying it to newer teammate changes. Binary screenshots are supplied in the full ZIP. Never overwrite real `.env` files or runtime databases.

Verified locally: 326 automated tests passed, 4 live S3 tests skipped; 65/65 offline question cases; 28/28 grounding cases. Real model/Slack runs remain NOT RUN with placeholder credentials. Exact mandatory Tencent service minima still need organizer confirmation.

| Status | File |
|---|---|
| modified | `.env.example` |
| modified | `README.md` |
| modified | `app/audit.py` |
| modified | `app/brain.py` |
| modified | `app/config.py` |
| added | `app/env.py` |
| added | `app/history.py` |
| modified | `app/identity.py` |
| modified | `app/llm.py` |
| modified | `app/main.py` |
| added | `app/metrics.py` |
| modified | `app/reliability.py` |
| modified | `app/server.py` |
| added | `app/slack_oauth.py` |
| modified | `app/slack_runtime.py` |
| modified | `app/sources/slack.py` |
| modified | `app/sources/slack_live.py` |
| added | `app/sources/slack_multi.py` |
| modified | `app/sources/world.py` |
| modified | `app/static/app.js` |
| modified | `app/static/index.html` |
| modified | `deploy/Dockerfile` |
| modified | `deploy/requirements.in` |
| modified | `docs/BRIEF_REVIEW.md` |
| modified | `docs/EVALUATION.md` |
| modified | `docs/EVIDENCE_PACK.md` |
| modified | `docs/HANDOFF_MEMBER2.md` |
| modified | `docs/HANDOFF_member1_to_member3.md` |
| added | `docs/INTEGRATION_REVIEW.md` |
| modified | `docs/MEMBER3.md` |
| modified | `docs/SLACK_MEMBER2.md` |
| added | `docs/TENCENT_REQUIREMENTS.md` |
| modified | `docs/WORKED_EXAMPLES.md` |
| added | `docs/demo-transcript-integrated.md` |
| modified | `docs/demo-transcript-member3.md` |
| added | `docs/screenshots/integrated-history.png` |
| added | `evaluation/baseline_member1/brain.py` |
| added | `evaluation/baseline_member1/grounding.py` |
| added | `evaluation/baseline_member1/index.py` |
| added | `evaluation/baseline_member1/llm.py` |
| added | `evaluation/baseline_member1/planner.py` |
| added | `evaluation/baseline_member1/provenance.json` |
| modified | `evaluation/cases.py` |
| added | `evaluation/grounding_cases.py` |
| added | `evaluation/live_cases.py` |
| added | `evaluation/reports/baseline.json` |
| added | `evaluation/reports/baseline.md` |
| added | `evaluation/reports/browser-review.md` |
| added | `evaluation/reports/comparison.json` |
| added | `evaluation/reports/comparison.md` |
| added | `evaluation/reports/current.json` |
| added | `evaluation/reports/current.md` |
| modified | `evaluation/reports/judging-scenarios.json` |
| added | `evaluation/reports/live-model.json` |
| added | `evaluation/reports/live-model.md` |
| added | `evaluation/reports/live-slack.json` |
| modified | `evaluation/reports/offline-evaluation.json` |
| modified | `evaluation/reports/offline-evaluation.md` |
| modified | `evaluation/reports/synthetic-benchmark.json` |
| modified | `evaluation/reports/synthetic-benchmark.md` |
| added | `evaluation/reports/test-results.txt` |
| added | `examples/slack-live-checks.example.json` |
| added | `examples/slack-workspaces.example.json` |
| modified | `requirements-lock.txt` |
| modified | `requirements.txt` |
| modified | `scripts/benchmark.py` |
| added | `scripts/compare.py` |
| modified | `scripts/demo_member3.py` |
| modified | `scripts/evaluate.py` |
| modified | `scripts/judging_demo.py` |
| added | `scripts/verify_live_slack.py` |
| modified | `tests/conftest.py` |
| modified | `tests/contract/specs.py` |
| added | `tests/contract/test_slack_lifecycle.py` |
| modified | `tests/test_brief_acceptance.py` |
| added | `tests/test_integration_completion.py` |
| modified | `tests/test_member1_handoff.py` |
| modified | `tests/test_member2_http.py` |
| modified | `tests/test_member2_pipeline.py` |
| modified | `tests/test_member3_audit.py` |
| modified | `tests/test_member3_ops.py` |
| modified | `tests/test_scenarios.py` |
| modified | `tests/test_security.py` |
| modified | `tests/test_slack_member2.py` |
