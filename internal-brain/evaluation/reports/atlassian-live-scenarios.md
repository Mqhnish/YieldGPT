# Brief scenarios on the Atlassian site (live)

- Date (UTC): 2026-10-14T13:10:38+00:00
- Commit: `0db7dc41d12df3e81a64cf73842a3051ff7bfbc8`
- Mode: **live** (Confluence + Jira on a real Atlassian Cloud site); Slack and Drive simulated in both modes
- Result: **ALL PASS** (14/14 checks)

Every check asks the question through the app's real pipeline as that persona. S2 (freshness) and S4 (revocation) need edits on the site and are proven by the lifecycle probe report.

| Scenario | Check | Result | Detail |
|---|---|---|---|
| S1 | jdoe: migration answer cites the Jira epic and the Slack thread | PASS | 4 citations |
| S1 | answer spans 2+ platforms, all citation links https | PASS | gdrive, jira, slack |
| S1 | private channel jdoe is not in is omitted | PASS |  |
| S1 | ravi: outage answer stitches Jira root cause, Drive doc and follow-up tickets | PASS | 6 citations |
| S3 | kim: restricted report answer identical to a nonexistent one | PASS |  |
| S3 | jdoe: no security-level issue, security project or security space page cited | PASS |  |
| S3 | jdoe's denial on the security-level issue (demo PAY-110) is in the audit trail | PASS |  |
| S3 | asha (security group) does get the security-level issue | PASS |  |
| S3 | kim (no Atlassian account) gets no Jira citations | PASS |  |
| S3 | child page of a restricted page is denied (inherited restriction) | PASS | confluence_read_denied |
| S5 | compliance question parsed (user, space, platform) | PASS |  |
| S5 | each matching request has the question, per-document decisions and the answer | PASS | 2 request(s) |
| S5 | matched documents are allowed Confluence pages in that space | PASS |  |
| S5 | 'who retrieved the breach report' names only asha | PASS | asha |

Redacted: no API token, email, accountId or site name appears in this report.
