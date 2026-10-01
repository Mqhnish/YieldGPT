# Measured before/after comparison

Frozen original Member 1 lexical pipeline vs current pipeline, both rerun on identical current fixtures and expectations with offline generators. Controlled reconstruction, not a historical live-model measurement.

| Metric | Before | After |
|---|---:|---:|
| passed | 50 | 65 |
| total | 65 | 65 |
| source_recall | 0.8571428571428571 | 1.0 |
| unauthorized_citations | 0 | 0 |
| unauthorized_context_sources | 0 | 0 |
| no_answer_correct | 13 | 16 |
| no_answer_cases | 16 | 16 |
| grounding_accuracy | 0.5357142857142857 | 1.0 |
| grounding_false_accepts | 13 | 0 |

Improved cases: exact-migration-epic, exact-migration-blocker, exact-pool-ticket, exact-payment-incident, exact-runbook, exact-drive-postmortem, migration-progress, migration-sequence, auth-decision, payments-duration, time-no-recent-auth, time-old-incident, missing-approval, security-inherited-page-allow, security-external-shared-guide

Regressed cases: none

Token costs are unknown offline. Full per-case evidence and current stage timings are in current.json. Grounding is measured separately on 28 labeled edge cases.
