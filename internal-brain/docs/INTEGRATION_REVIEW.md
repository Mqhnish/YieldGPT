# Integration review: reported gaps and evidence

This review covers changes on top of the supplied Member 3 project. Credentials remain placeholders at the user's request. “Implemented and tested locally” does not mean a live cloud deployment was verified.

| Reported issue | Resolution / present status |
|---|---|
| No real model connected | Compatible HTTP adapter, automatic `.env`, strict live mode, bounded retries and safe errors implemented. Actual approved-account connection remains NOT RUN. |
| No live paraphrase/adversarial evaluation | Credentialed 78-question run plus 28 grounding decisions implemented. Requires real model selection for answerable cases. Saved report explicitly not run. |
| Tencent requirement unconfirmed | Official sources checked; [requirements record](TENCENT_REQUIREMENTS.md) states what is known and retains exact service minima as a release gate. Cannot invent organizer approval. |
| Model time/cost mixed with authorization | Audit-only model HTTP/elapsed/retry/token/cost measurements; separate retrieval, authorization/read and release timings; per-case JSON evidence. Unknown billing remains null. |
| No before/after | Original Member 1 lexical files frozen with archive/file hashes; controlled paired rerun on identical fixtures. 50/65 → 65/65 cases; source recall 85.7% → 100%. |
| No measured grounding category | 28 labeled accept/reject cases: negation, numbers, dates, uncertainty, contradictory citations, short claims and invented references. 15/28 → 28/28; false accepts 13 → 0. |
| Slack shared contract TODOs | Shared contract includes DMs, public scope, edit/delete and retention. Same lifecycle assertions run on simulated, HTTP-adapter and federated HTTP fixtures. |
| Slack workspace/identity/OAuth gaps | Workspace-scoped fixture IDs; federated connector, independent cursors/signatures, explicit per-workspace identity; AES-GCM installation store, single-use expiring OAuth state, verified delegated identity, rotation and revocation tombstones. Live workspace acceptance remains NOT RUN. |
| Audit bypass / incorrect handoff | Canonical server enforced/documented. Ask, previews and replay checkpoint before releasing content. Member 3's S3 Object Lock implementation preserved and documented accurately. Four live S3 tests require an endpoint. |
| Prior-answer replay missing | Actor-scoped history and fresh question replay API/UI. Current permissions/content rechecked, restart-safe history, retention expiry, withheld-answer exclusion and checkpoint failure covered. |
| Additional integration issue | Missing cryptography dependency added. Missing encryption now refuses audit text rather than silently persisting plaintext. |

## Current evidence

See `evaluation/reports/test-results.txt` for the final automated run, `comparison.md` and `current.json` for paired quality results, `live-model.json` and `live-slack.json` for explicit live status. The current fictional examples are reproducible with `scripts/judging_demo.py`. Browser verification is recorded separately in `evaluation/reports/browser-review.md`.

The protected checkpoint implementation exists; independent WORM behavior was not re-run against a live bucket here. Member 3's supplied reports are historical team evidence and are labeled accordingly. Local tests do not establish a production SLA, exact source truth, absence of every side channel, real model compatibility or successful OAuth installation with Slack.

Production identity/SSO and live non-Slack connectors remain team dependencies. No real credentials, live workspaces, external messages or deployment were created by this integration.

Security integration note: seeded demo login and demo-token verification are disabled outside demo mode or when live Slack configuration is present. Member 1 must supply the trusted identity provider before real-source employee access or OAuth linking. This guard prevents the public `demo` password from opening real company data.
