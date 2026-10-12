# Confluence + Jira connectors: modes and live setup

Owner: Member 1.

## What exists

| Piece | File |
|---|---|
| Confluence Cloud connector (real REST) | `app/sources/confluence_cloud.py` |
| Jira Cloud connector (real REST v3) | `app/sources/jira_cloud.py` |
| Shared HTTP client, fail-closed error mapping | `app/sources/atlassian_client.py` |
| Change polling + deletion reconciliation | `app/sources/cloud_polling.py` |
| Storage-format / ADF to text | `app/sources/textconv.py` |
| URL to uid (cross-platform links) | `app/sources/links.py` |
| Fake Atlassian site for offline runs | `app/sources/fake_atlassian.py` |
| Live read-only conformance check | `scripts/atlassian_live_check.py` |
| Seed a real site with the demo company | `scripts/seed_atlassian.py` (`app/seeding/atlassian_seed.py`) |
| Brief-sized synthetic estate + benchmark | `app/seeding/scale.py`, `scripts/scale_benchmark.py` |

## Three modes (`IB_ATLASSIAN_MODE`)

| Mode | What runs | Use for |
|---|---|---|
| `fixture` (**default**) | Real HTTP connectors talking to a fake site built from the demo company | Tests, offline demo |
| `live` | Real HTTP connectors talking to a real Atlassian Cloud site | Live demo segment |
| `sim` | Old in-process simulator, no HTTP | Comparison only |

The same contract suite runs against `sim` and `fixture` (`python -m pytest tests/contract -q`).
All 5 scenario tests from the brief run through `fixture` by default.

## How each hard requirement is handled

| Requirement | How |
|---|---|
| Don't flatten permissions | The permission decision is Atlassian's own. Confluence: `POST /wiki/rest/api/content/{id}/permission/check` for the asker's accountId (space permissions + inherited restrictions evaluated by Confluence). Jira: `POST /rest/api/3/permissions/check` with `BROWSE_PROJECTS` on the issue |
| Revocation takes effect immediately | Checked live on every question and again before release. Nothing is cached |
| Freshness | Polls `lastmodified` (CQL) / `updated` (JQL) every 5 min with a 3-minute overlap window, because both APIs only have minute precision. Duplicates are removed by (id, version) |
| Deletions | Search APIs never return deleted items, so a full id listing runs every `IB_RECONCILE_EVERY_S` (default 600s) and missing ids become `delete` changes. Deleted items are never *served* in between, because live checks and fresh fetches treat 404 as gone |
| Fail closed | 401, 403, 429, 5xx, timeouts and network errors all give `unavailable` = not shown. An ambiguous response is never an allow |
| No credential leaks | Error text is built from status codes only, never response bodies or headers (tested) |
| Cross-platform links | Confluence `<a href>` / `ri:url` and Jira issue links + remote links are resolved to uids (`jira:PAY-101`, `slack:...`, `gdrive:...`) |
| Credentials stay on-site | Pagination links come from server responses. Any link to another host (or plain http) is refused before a request is made, so the API token can't be sent elsewhere |
| Restricted Jira comments | Comments with `visibility` (limited to a role/group) have narrower access than their issue, so they are **never indexed**. Public comments are |
| No silent truncation | A `nextPageToken` always means "more pages". Reconciliation holds back any run that would delete >20% of an estate (listing truncated or bot lost access), keeps edits flowing, and marks sync health `degraded` until someone checks. `IB_ALLOW_MASS_DELETE=1` confirms a real bulk delete |
| Speed | Permission checks for one question run in parallel under one shared deadline. Jira checks every issue in **one** bulk call. With 250ms latency, a question went from 3.8s to 1.5s of Atlassian time |

## Known limitations (be honest about these in the demo)

1. **Permission *changes* aren't detected by polling.** Restriction and permission-scheme edits don't
   bump `lastmodified` / `updated`. That's safe (the live check decides) but the prefilter hint can be stale.
2. **Prefilter is weak.** Confluence uses page restrictions or "anyone". Jira is always "anyone".
   Correctness is unaffected, but more documents reach the (slower) live check.
3. **Two Jira edits in the same millisecond** share `updated`, so the second may only arrive via webhook
   or read-through. The version string includes a content hash so re-fetches still detect it.
4. **Deletions during downtime.** After a restart, the first reconciliation only rebuilds the baseline.
   A full re-crawl catches anything deleted while the app was down.
5. **Webhooks not wired for Atlassian yet.** Polling + read-through only.
6. **Fake site JSON shapes follow the public docs.** They are confirmed only once the live check below passes.
7. **Pages only.** Confluence blog posts, comments and attachments aren't indexed. Jira attachments aren't either.
8. **Restricted Jira comments are skipped entirely**, even for users who could see them. Safe, but those users get less context.
9. **Code blocks lose their line breaks** when converted to text.
10. **Jira checks don't report the issue version** (the bulk permission API doesn't return one). An edit landing
    in the milliseconds between the pipeline's read and its after-read check is caught by the release
    re-fetch fingerprint, not by the check itself. Confluence checks do report the page version.
11. **Two sources of group truth.** The prefilter uses groups from our identity directory; the live check uses
    Atlassian's own groups. If they disagree, the worst case is a page wrongly filtered out (fail closed),
    never one wrongly shown. In production both come from the same IdP via SCIM.

## Live setup (for the demo)

### 1. Plan: you need Standard, not Free

On the Free plans, Confluence has no space permissions or page restrictions, and Jira has no
customisable roles, permission schemes or issue security. Everyone can see everything, so there
is nothing to enforce. Start a **Standard trial** for both Jira and Confluence on one site
(check the trial length when you sign up).

### 2. Integration account

- Create a dedicated account, e.g. `brain-bot@...`. Don't use a personal account.
- Make it an admin (it must be allowed to check *other users'* permissions:
  Confluence admin for the content permission check, "Administer Jira" for the bulk permission check).
  Confirm this during step 5. If checks return 403, this is why.
- Set its profile timezone to **UTC** (JQL/CQL dates use the API user's timezone).
- Create an API token at id.atlassian.com under Security, API tokens. Treat it like a password.

### 3. Invite the personas

Invite 3 or 4 teammates as the personas (engineer, SRE, security engineer, compliance). Leave the
contractor persona **without** an Atlassian account. Find each accountId (profile URL, or
`GET /rest/api/3/user/search?query=email`) and write `accounts.json` (gitignored):

```json
{
  "jdoe":  {"confluence": "557058:xxxx", "jira": "557058:xxxx"},
  "ravi":  {"confluence": "557058:wwww", "jira": "557058:wwww"},
  "asha":  {"confluence": "557058:yyyy", "jira": "557058:yyyy"},
  "priya": {"confluence": "557058:zzzz", "jira": "557058:zzzz"},
  "kim":   {}
}
```

### 4. Seed the demo company (automatic)

```bash
export IB_ATLASSIAN_SITE=https://yourteam.atlassian.net
export IB_ATLASSIAN_EMAIL=brain-bot@...
export IB_ATLASSIAN_API_TOKEN=...            # never commit
export IB_ACCOUNT_MAP=accounts.json
python scripts/seed_atlassian.py
```

Creates the groups (and adds the personas), the spaces `ENG`, `PAYMENTGATEWAY`, `SECURITY` with read
grants, every page (parents first, with the real links), page restrictions, projects `MIG`, `PAY`, `SEC`
if missing, every issue with its status, links and remote links. Real ids differ from demo ids
(`MIG-7` becomes `MIG-2`); all text and links are rewritten. It writes `seed_manifest.json` (demo id to
real id) and `expectations.json`. **Safe to re-run**: it finds what exists instead of duplicating.

It then prints the **manual steps** (admin screens, once):
- remove default space permissions so only the intended groups can view each space
- Jira permission schemes: who has *Browse Projects* in `MIG`, `PAY`, `SEC`
- issue security scheme with level `security-only` (group `security`) on the projects

Org-wide permission policy is deliberately left to a human: automating it against a site we don't fully
control is how you lock yourself out. Then:

```bash
python scripts/seed_atlassian.py --apply-security      # sets the security level on the right issue
```

Tested end to end offline (`tests/test_atlassian_seed.py`): seeding an empty site, doing the manual steps,
re-running, then checking all 84 persona x document expectations against the real connectors. Skipping
the manual steps produces 26 mismatches, which is the point: a misconfigured site is caught, and it
fails safe (unconfigured means denied).

### 5. Run the live conformance check (read-only, changes nothing)

```bash
export IB_ATLASSIAN_MODE=live
python scripts/atlassian_live_check.py expectations.json
```

It must print `ALL PASS` before the live demo. **Specifically confirm the Jira security-level issue**
(`PAY-110` in the demo, its real key is in `seed_manifest.json`). If the bulk permission check lets a
user browse an issue their security level hides, don't demo Jira live: switch `JiraCloudConnector._check`
to also compare the issue's security level against the user's membership of that level, and re-run.

Note for the audit demo: the brief's query says `'payment-gateway'`; on the real site that space is
`PAYMENTGATEWAY`. Audit filters ignore case and `-`/`_`, so the brief's exact sentence still works.

### 6. Run the app live

Same env vars, then `python -m uvicorn app.server:app` (the team entrypoint). Slack and Drive stay simulated unless Members 2 and 3 have
wired theirs. Say so on the demo screen.

## If you can't get a Standard trial

Stay on `fixture`. It's still the real connector code (HTTP, pagination, parsing, error handling), and
only the network is fake. In the demo, say: "Confluence and Jira connectors are real REST integrations,
running against a recorded Atlassian site for determinism. Here's the one-line switch to live."
