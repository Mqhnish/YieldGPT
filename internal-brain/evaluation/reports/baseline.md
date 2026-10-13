# Company A stub evaluation (frozen_member1_lexical)

Generated: 2026-10-13T18:57:05.838762+00:00

These are measured results on fictional fixtures. The provider mode is recorded above. They do not establish production authorization, semantic entailment, or live-model quality.

- Cases passed: **50/65**
- Required citation obligations met: **48/56** (85.7%)
- Unauthorized citations: **0**
- Unauthorized model-context sources: **0**
- Forbidden citations (including time exclusions/poisoned content): **2**
- Forbidden model-context sources: **2**
- No-answer cases correct: **13/16**

| Category | Passed | Total |
|---|---:|---:|
| cross_source | 5 | 5 |
| exact_identifier | 4 | 10 |
| grounding | 15 | 28 |
| no_evidence | 4 | 5 |
| paraphrase | 18 | 22 |
| security | 15 | 17 |
| time | 4 | 6 |

Grounding decision accuracy: 15/28; false accepts: 13; false rejects: 0.

Model measurements (each attempt, token counts, configured price estimates) and separate retrieval/authorization/generation phases are in the JSON report. Unknown prices and failed-call usage remain null. Phase timings overlap and must not be added together. Baseline phase metrics are unavailable; its total elapsed time is measured.


## Individual results

| Case | Result | Failure details |
|---|---|---|
| exact-migration-epic | FAIL | missing fact: 70% |
| exact-migration-blocker | FAIL | missing citation jira:MIG-7; unexpected abstention; missing fact: 40 seconds / 40s |
| exact-pool-ticket | FAIL | missing citation jira:MIG-9; unexpected abstention; missing fact: 40 per pod |
| exact-payment-incident | FAIL | missing fact: expired |
| exact-expiry-alert | PASS | — |
| exact-renewal-failure | PASS | — |
| exact-auth-adr | PASS | — |
| exact-runbook | FAIL | missing citation confluence:CONF-101; unexpected abstention |
| exact-drive-postmortem | FAIL | missing citation gdrive:DRV-1; unexpected abstention; missing fact: 47 minutes |
| exact-security-issue | PASS | — |
| migration-progress | FAIL | missing fact: 70% |
| migration-cutover-date | PASS | — |
| migration-delay | PASS | — |
| migration-night-work | PASS | — |
| migration-pool | PASS | — |
| migration-sequence | FAIL | missing citation gdrive:DRV-2; missing fact: freeze schema; missing fact: switch read traffic |
| migration-lag-threshold | PASS | — |
| auth-scalability | PASS | — |
| auth-refresh | PASS | — |
| auth-owner | PASS | — |
| auth-decision | FAIL | missing citation confluence:CONF-102; unexpected abstention; missing fact: short-lived JWT / token-exchange |
| payments-root-cause | PASS | — |
| payments-duration | FAIL | missing fact: 47 minutes |
| payments-protocol | PASS | — |
| payments-oncall-cadence | PASS | — |
| payments-renewal | PASS | — |
| vendor-sandbox | PASS | — |
| vendor-guide-location | PASS | — |
| security-accounts | PASS | — |
| security-response | PASS | — |
| security-remediation | PASS | — |
| security-evidence | PASS | — |
| cross-migration | PASS | — |
| cross-payment | PASS | — |
| cross-auth | PASS | — |
| cross-cutover-checklist | PASS | — |
| cross-security | PASS | — |
| time-recent-blocker | PASS | — |
| time-no-recent-auth | FAIL | forbidden citation slack:T0COMPANYA/auth-design/1001; forbidden model context slack:T0COMPANYA/auth-design/1001; expected neutral no-answer with no citations |
| time-auth-last-sprint | PASS | — |
| time-vendor-week | PASS | — |
| time-kickoff-month | PASS | — |
| time-old-incident | FAIL | forbidden citation slack:T0COMPANYA/payments-oncall/3001; forbidden model context slack:T0COMPANYA/payments-oncall/3001; expected neutral no-answer with no citations |
| missing-unicorn | PASS | — |
| missing-cafeteria | PASS | — |
| missing-identifier | PASS | — |
| missing-cfo-salary | PASS | — |
| missing-approval | FAIL | expected neutral no-answer with no citations |
| security-contractor-breach | PASS | — |
| security-contractor-jira | PASS | — |
| security-issue-level-denial | PASS | — |
| security-inherited-page-denial | PASS | — |
| security-named-page-allow | PASS | — |
| security-inherited-page-allow | FAIL | missing citation confluence:CONF-105; unexpected abstention |
| security-admin-no-payment | PASS | — |
| security-compliance-no-evidence | PASS | — |
| security-private-leads-allow | PASS | — |
| security-private-leads-deny | PASS | — |
| security-private-oncall-allow | PASS | — |
| security-poisoned-notes | PASS | — |
| security-external-shared-guide | FAIL | missing citation gdrive:DRV-3; unexpected abstention |
| security-external-internal-drive | PASS | — |
| security-engineer-report | PASS | — |
| security-vulnerability-list | PASS | — |
| security-engineer-no-vulns | PASS | — |

## Measurement limits

Source recall counts one obligation per `expected_all` source and one obligation for an `expected_any` group. Extra citations are not automatically incorrect, so this is not citation precision. All citations and assembled context are independently checked against the current connector permissions. Phrase checks cover specific fixture facts; they are not a general factuality judge. Static evaluation complements the separate revocation, fail-closed, grounding, and contract tests.
