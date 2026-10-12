# Atlassian lifecycle probe (fixture)

- Date (UTC): 2026-10-09T21:51:08+00:00
- Commit: `b683447500933f035390713b43b79cf867a586af`
- Mode: **fixture** (real HTTP connectors against the in-process fake site, not live evidence)
- Personas: viewer `ravi`, insider `asha`; space `eng`, project `MIG`
- Result: **ALL PASS** (14/14 steps)

Every step goes through the app's real pipeline (`Brain.ask`, live permission checks). Retrievability times include an immediate poll, so they measure pipeline visibility, not the 5-minute production poll interval.

| Platform | Step | Mode | Result | Seconds | Detail |
|---|---|---|---|---:|---|
| confluence | create: retrievable by viewer | fixture | PASS | 0.012 | write 0.00s, then 1 poll+ask round(s) |
| confluence | edit: new version served, old text not served | fixture | PASS | 0.006 | 1 poll+ask round(s); old version or text served: False |
| confluence | revoke: viewer denied on next query (no reindex) | fixture | PASS | 0.004 | revoke write 0.00s, next query 0.00s, check=confluence_read_denied |
| confluence | revoke: denial identical to a nonexistent document | fixture | PASS | 0.0 |  |
| confluence | revoke: insider still served | fixture | PASS | 0.0 |  |
| confluence | delete: not served on next query (no reindex) | fixture | PASS | 0.004 | delete write 0.00s, next query 0.00s |
| confluence | delete: removed from index by reconciliation, still not served | fixture | PASS | 0.0 | 1 poll round(s) |
| jira | create: retrievable by viewer | fixture | PASS | 0.006 | write 0.00s, then 1 poll+ask round(s) |
| jira | edit: new version served, old text not served | fixture | PASS | 0.006 | 1 poll+ask round(s); old version or text served: False |
| jira | revoke: viewer denied on next query (no reindex) | fixture | PASS | 0.005 | revoke write 0.00s, next query 0.00s, check=jira_browse_denied |
| jira | revoke: denial identical to a nonexistent document | fixture | PASS | 0.0 |  |
| jira | revoke: insider still served | fixture | PASS | 0.0 |  |
| jira | delete: not served on next query (no reindex) | fixture | PASS | 0.004 | delete write 0.00s, next query 0.00s |
| jira | delete: removed from index by reconciliation, still not served | fixture | PASS | 0.0 | 1 poll round(s) |

Redacted: no API token, email, accountId or site name appears in this report.
