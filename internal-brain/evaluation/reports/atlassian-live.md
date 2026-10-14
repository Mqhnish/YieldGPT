# Atlassian lifecycle probe (live)

- Date (UTC): 2026-10-13T02:16:52+00:00
- Commit: `8cc20bd7335596a6d1da2ccc6faf35e5be3fa795`
- Mode: **live** (real Atlassian Cloud site, Standard trial)
- Personas: viewer `ravi`, insider `asha`; space `ENG`, project `PAY`
- Result: **ALL PASS** (17/17 steps)

Every step goes through the app's real pipeline (`Brain.ask`, live permission checks). Retrievability times include an immediate poll, so they measure pipeline visibility, not the 5-minute production poll interval.

| Platform | Step | Mode | Result | Seconds | Detail |
|---|---|---|---|---:|---|
| confluence | create: retrievable by viewer | live | PASS | 16.038 | write 1.55s, then 3 poll+ask round(s) |
| confluence | edit: new version served, old text not served | live | PASS | 4.175 | 1 poll+ask round(s); old version or text served: False |
| confluence | revoke: viewer denied on next query (no reindex) | live | PASS | 1.556 | revoke write 1.41s, next query 0.15s, check=confluence_read_denied |
| confluence | revoke: denial holds within 5 s of the revoke | live | PASS | 4.153 | 3 denied queries in a row; allowed again after a denial: 0 time(s) |
| confluence | revoke: denial identical to a nonexistent document | live | PASS | 0.0 |  |
| confluence | revoke: insider still served | live | PASS | 2.74 |  |
| confluence | delete: not served on next query (no reindex) | live | PASS | 0.582 | delete write 0.31s, next query 0.28s |
| confluence | delete: removed from index by reconciliation, still not served | live | PASS | 0.67 | 1 poll round(s) |
| jira | preflight: integration account has the Jira permissions it needs | live | PASS | 0.0 |  |
| jira | create: retrievable by viewer | live | PASS | 9.37 | write 0.88s, then 2 poll+ask round(s) |
| jira | edit: new version served, old text not served | live | PASS | 2.739 | 1 poll+ask round(s); old version or text served: False |
| jira | revoke: viewer denied on next query (no reindex) | live | PASS | 0.555 | revoke write 0.35s, next query 0.21s, check=jira_browse_denied |
| jira | revoke: denial holds within 5 s of the revoke | live | PASS | 2.915 | 3 denied queries in a row; allowed again after a denial: 0 time(s) |
| jira | revoke: denial identical to a nonexistent document | live | PASS | 0.0 |  |
| jira | revoke: insider still served | live | PASS | 2.434 |  |
| jira | delete: not served on next query (no reindex) | live | PASS | 1.005 | delete write 0.85s, next query 0.15s |
| jira | delete: removed from index by reconciliation, still not served | live | PASS | 0.764 | 1 poll round(s) |

Redacted: no API token, email, accountId or site name appears in this report.
