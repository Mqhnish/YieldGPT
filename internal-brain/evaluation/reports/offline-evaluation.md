# Company A stub evaluation (current)

Generated: 2026-09-29T11:49:35.998091+00:00

These are measured results on fictional fixtures. The provider mode is recorded above. They do not establish production authorization, semantic entailment, or live-model quality.

- Cases passed: **65/65**
- Required citation obligations met: **56/56** (100.0%)
- Unauthorized citations: **0**
- Unauthorized model-context sources: **0**
- Forbidden citations (including time exclusions/poisoned content): **0**
- Forbidden model-context sources: **0**
- No-answer cases correct: **16/16**

| Category | Passed | Total |
|---|---:|---:|
| cross_source | 5 | 5 |
| exact_identifier | 10 | 10 |
| grounding | 28 | 28 |
| no_evidence | 5 | 5 |
| paraphrase | 22 | 22 |
| security | 17 | 17 |
| time | 6 | 6 |

Grounding decision accuracy: 28/28; false accepts: 0; false rejects: 0.

Model measurements (each attempt, token counts, configured price estimates) and separate retrieval/authorization/generation phases are in the JSON report. Unknown prices and failed-call usage remain null. Phase timings overlap and must not be added together. Baseline phase metrics are unavailable; its total elapsed time is measured.


## Individual results

| Case | Result | Failure details |
|---|---|---|
| exact-migration-epic | PASS | — |
| exact-migration-blocker | PASS | — |
| exact-pool-ticket | PASS | — |
| exact-payment-incident | PASS | — |
| exact-expiry-alert | PASS | — |
| exact-renewal-failure | PASS | — |
| exact-auth-adr | PASS | — |
| exact-runbook | PASS | — |
| exact-drive-postmortem | PASS | — |
| exact-security-issue | PASS | — |
| migration-progress | PASS | — |
| migration-cutover-date | PASS | — |
| migration-delay | PASS | — |
| migration-night-work | PASS | — |
| migration-pool | PASS | — |
| migration-sequence | PASS | — |
| migration-lag-threshold | PASS | — |
| auth-scalability | PASS | — |
| auth-refresh | PASS | — |
| auth-owner | PASS | — |
| auth-decision | PASS | — |
| payments-root-cause | PASS | — |
| payments-duration | PASS | — |
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
| time-no-recent-auth | PASS | — |
| time-auth-last-sprint | PASS | — |
| time-vendor-week | PASS | — |
| time-kickoff-month | PASS | — |
| time-old-incident | PASS | — |
| missing-unicorn | PASS | — |
| missing-cafeteria | PASS | — |
| missing-identifier | PASS | — |
| missing-cfo-salary | PASS | — |
| missing-approval | PASS | — |
| security-contractor-breach | PASS | — |
| security-contractor-jira | PASS | — |
| security-issue-level-denial | PASS | — |
| security-inherited-page-denial | PASS | — |
| security-named-page-allow | PASS | — |
| security-inherited-page-allow | PASS | — |
| security-admin-no-payment | PASS | — |
| security-compliance-no-evidence | PASS | — |
| security-private-leads-allow | PASS | — |
| security-private-leads-deny | PASS | — |
| security-private-oncall-allow | PASS | — |
| security-poisoned-notes | PASS | — |
| security-external-shared-guide | PASS | — |
| security-external-internal-drive | PASS | — |
| security-engineer-report | PASS | — |
| security-vulnerability-list | PASS | — |
| security-engineer-no-vulns | PASS | — |

## Measurement limits

Source recall counts one obligation per `expected_all` source and one obligation for an `expected_any` group. Extra citations are not automatically incorrect, so this is not citation precision. All citations and assembled context are independently checked against the current connector permissions. Phrase checks cover specific fixture facts; they are not a general factuality judge. Static evaluation complements the separate revocation, fail-closed, grounding, and contract tests.
