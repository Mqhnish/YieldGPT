# Atlassian lifecycle probe (live)

- Date (UTC): 2026-10-14T13:32:53+00:00
- Commit: `1ade5eee87b4d3ce667476308fed89fcf54d5817`
- Mode: **live** (real Atlassian Cloud site, Standard trial)
- Personas: viewer `ravi`, insider `asha`; space `ENG`, project `PAY`
- Result: **ALL PASS** (21/21 steps)

Every step goes through the app's real pipeline (`Brain.ask`, live permission checks). Retrievability times include an immediate poll, so they measure pipeline visibility, not the 5-minute production poll interval.

| Platform | Step | Mode | Result | Seconds | Detail |
|---|---|---|---|---:|---|
| confluence | create: retrievable by viewer | live | PASS | 16.875 | write 1.95s, then 3 poll+ask round(s) |
| confluence | edit: new version served, old text not served | live | PASS | 5.079 | 1 poll+ask round(s); old version or text served: False |
| confluence | child page: retrievable by viewer | live | PASS | 13.499 | 2 poll+ask round(s) |
| confluence | revoke: viewer denied on next query (no reindex) | live | PASS | 1.556 | revoke write 1.28s, next query 0.27s, check=confluence_read_denied |
| confluence | revoke: denial holds within 5 s of the revoke | live | PASS | 3.189 | after the platform confirmed (revoke write 1.28s); 3 denied queries in a row; allowed again after a denial: 0 time(s) |
| confluence | revoke: child page denied too (inherited restriction) | live | PASS | 6.468 | first query after the revoke denied: True, check=confluence_read_denied, allowed again after a denial: 0 time(s); seconds since the parent's revoke was confirmed |
| confluence | revoke: insider still served the child page | live | PASS | 4.126 |  |
| confluence | revoke: denial identical to a nonexistent document | live | PASS | 0.0 |  |
| confluence | revoke: insider still served | live | PASS | 3.472 |  |
| confluence | delete: not served on next query (no reindex) | live | PASS | 1.33 | delete write 0.70s, next query 0.62s |
| confluence | delete: removed from index by reconciliation, still not served | live | PASS | 1.129 | 1 poll round(s) |
| jira | preflight: integration account has the Jira permissions it needs | live | PASS | 0.0 |  |
| jira | create: retrievable by viewer | live | PASS | 3.1 | write 0.84s, then 1 poll+ask round(s) |
| jira | edit: new version served, old text not served | live | PASS | 2.672 | 1 poll+ask round(s); old version or text served: False |
| jira | status change and new comment served | live | PASS | 3.795 | new status 'Open', 1 poll+ask round(s) |
| jira | revoke: viewer denied on next query (no reindex) | live | PASS | 0.571 | revoke write 0.40s, next query 0.18s, check=jira_browse_denied |
| jira | revoke: denial holds within 5 s of the revoke | live | PASS | 2.977 | after the platform confirmed (revoke write 0.40s); 3 denied queries in a row; allowed again after a denial: 0 time(s) |
| jira | revoke: denial identical to a nonexistent document | live | PASS | 0.0 |  |
| jira | revoke: insider still served | live | PASS | 2.475 |  |
| jira | delete: not served on next query (no reindex) | live | PASS | 1.063 | delete write 0.87s, next query 0.20s |
| jira | delete: removed from index by reconciliation, still not served | live | PASS | 0.755 | 1 poll round(s) |

Redacted: no API token, email, accountId or site name appears in this report.
