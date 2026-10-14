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
6. **Fake site JSON shapes follow the public docs.** Confirmed on a real site for every endpoint the connectors use
   (live check 84/84, 13 Oct 2026; lifecycle probe 21/21, 14 Oct 2026). Endpoints only the seeder uses can still differ.
7. **Pages only.** Confluence blog posts, comments and attachments aren't indexed. Jira attachments aren't either.
8. **Restricted Jira comments are skipped entirely**, even for users who could see them. Safe, but those users get less context.
9. **Code blocks lose their line breaks** when converted to text.
10. **Jira checks don't report the issue version** (the bulk permission API doesn't return one). An edit landing
    in the milliseconds between the pipeline's read and its after-read check is caught by the release
    re-fetch fingerprint, not by the check itself. Confluence checks do report the page version.
11. **Two sources of group truth.** The prefilter uses groups from our identity directory; the live check uses
    Atlassian's own groups. If they disagree, the worst case is a page wrongly filtered out (fail closed),
    never one wrongly shown. In production both come from the same IdP via SCIM.
12. **Jira's permission engine settles after admin changes.** Right after permission-scheme edits, and for invited
    accounts that hadn't logged in yet, the same bulk check gave different answers seconds apart (always toward
    "denied" in what we saw). The pipeline never retries a denial to get an allow. A short stale "allowed" after a
    revoke is stopped by the release re-check (tested); the lifecycle probe measures how long a revoke takes to hold.
13. **Seeded issue statuses.** The seeder only moves issues to their demo status if the site's workflow offers that
    transition. On the default workflow several stay "To Do". Permissions are unaffected.

## Live setup (for the demo)

### 1. Plan: you need Standard, not Free

On the Free plans, Confluence has no space permissions or page restrictions, and Jira has no
customisable roles, permission schemes or issue security. Everyone can see everything, so there
is nothing to enforce. Start a **Standard trial** for both Jira and Confluence on one site
(check the trial length when you sign up).

### 2. Integration account

- Create a dedicated account, e.g. `brain-bot@...`. Don't use a personal account. (For a hackathon trial the site
  creator's own admin account works, as long as it is not also a persona.)
- Make it an admin (it must be allowed to check *other users'* permissions:
  Confluence admin for the content permission check, "Administer Jira" for the bulk permission check).
  Confirm this during step 5. If checks return 403, this is why.
- Set its profile timezone to **UTC** (JQL/CQL dates use the API user's timezone).
- Create an API token at id.atlassian.com under Security, API tokens. Treat it like a password.

### 3. Invite the personas

Invite 3 or 4 teammates as the personas (engineer, SRE, security engineer, compliance). Leave the
contractor persona **without** an Atlassian account. A second address per person (e.g. a personal gmail) can cover
a fourth persona. Then:

- Every persona account must **accept the invite and log in once** (Jira and Confluence). Before that, Jira's bulk
  permission check answered inconsistently for them.
- **No persona account may hold an admin role** (org, site, user access or app admin). Leave "Administrator access"
  unticked when inviting.
- `python scripts/write_account_map.py jdoe=<email> ravi=<email> asha=<email> priya=<email>` looks up the accountIds
  and writes `accounts.json` without printing them. A persona left out (dana, kim) has **no** Atlassian account in
  live mode; its demo placeholder id is never sent to Atlassian.

`accounts.json` (gitignored) looks like:

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

What the manual steps looked like on a real Standard site (13 Oct 2026):

- **Confluence uses space roles** ("roles-only mode"), which refuses the API grants. For each space: Space settings,
  Manage access, add the group(s) with role **Viewer**, remove "All Confluence users" (it was Collaborator).
- **Jira**: copy "Default Permission Scheme" once per project (MIG, PAY, SEC). In each: Browse Projects = the groups
  plus **Project lead**, remove "Any logged in user" and the add-ons role; Set Issue Security and **Delete Issues**
  include **Project lead** (the probe needs both). Associate each scheme with its project.
- **Issue security scheme** with level `security-only`: members group `security` **and Project lead**. Without the
  Project lead entry the integration account can't see PAY-110, so even asha gets "not found". Attach it to PAY.
- The seeder creates projects with the integration account as project lead, which is why "Project lead" works.

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

It must print `ALL PASS` before the live demo. Add `--report evaluation/reports/atlassian-live-check.md` to save a
dated, redacted copy.

**Jira security level, confirmed live (13 Oct 2026):** the bulk permission check does exclude issues hidden by an
issue security level. PAY-110 (real key PAY-4) was denied to ravi, who can browse PAY, and allowed to asha. No
security-level fallback is needed in `JiraCloudConnector._check_batch`. Result: 84/84.

### 5b. Lifecycle probe (WRITES to the site, run it yourself)

```bash
IB_ATLASSIAN_MODE=live IB_ACCOUNT_MAP=accounts.json python scripts/atlassian_lifecycle_probe.py --mode live --project PAY
```

Creates one page in ENG and one issue in PAY, then proves through the real pipeline: retrievable, edit served,
revoke denied on the next query (page restriction / `security-only`), denial identical to "doesn't exist", insider
still served, delete never served again. Timed; deletes what it created (the page goes to the trash, the issue is
deleted permanently). It checks the integration account's Jira permissions first and creates nothing if one is
missing. Use PAY: the security level is only attached there. Report: `evaluation/reports/atlassian-live.md`.
Result on 14 Oct 2026: 21/21, including the inherited page restriction and a Jira status change and comment.

Note for the audit demo: the brief's query says `'payment-gateway'`; on the real site that space is
`PAYMENTGATEWAY`. Audit filters ignore case and `-`/`_`, so the brief's exact sentence still works.

### 6. Run the app live

Same env vars, then `python -m uvicorn app.server:app` (the team entrypoint). Slack and Drive stay simulated unless Members 2 and 3 have
wired theirs. Say so on the demo screen.

## If you can't get a Standard trial

Stay on `fixture`. It's still the real connector code (HTTP, pagination, parsing, error handling), and
only the network is fake. In the demo, say: "Confluence and Jira connectors are real REST integrations,
running against a recorded Atlassian site for determinism. Here's the one-line switch to live."
