# Handoff: Member 1 (permissions + sync) to Member 3 (audit + reliability)

**Version 2**, 28 Sep 2026. Supersedes v1 (see changelog at the end).
**From:** Member 1. **To:** Member 3. **cc:** Member 2 (sections 4 and 7 affect Slack).

---

## 0. Summary

| # | You asked for | Status | Where | What you need to do |
|---|---|---|---|---|
| 1 | Permission decision records | **Delivered** | `app/brain.py` `_record()` | Consume schema `authz_decision/1` (section 2) |
| 2 | Final recheck before release | **Delivered** | `app/brain.py` `ask()`, `_release_check()` | Decide on a delivery event (section 3.4) |
| 3 | Audit access rules | **Proposal, needs your sign-off** | `app/audit_policy.py` | Approve or change, and answer 4 questions (section 4.3) |
| 4 | Drive connector rules + tests | **Delivered** | `app/sources/base.py`, `tests/contract/` | Implement 5 Drive cases (section 5.4) |
| 5 | Sync bookkeeping | **Delivered** (reference storage) | `app/sync_state.py`, `app/sync.py` | Own durable storage (section 6.4) |

**How to verify all of it:**

```bash
pip install -r requirements.txt
python -m pytest -q                              # 95 tests
python -m pytest tests/contract -q               # connector contract only (48)
python -m pytest tests/test_member1_handoff.py -q  # this handoff only
```

**Proposed sign-off date for section 4:** Wed 30 Sep, the end of the "agree interfaces"
phase in our plan. If I don't hear back by then, I'll build on the defaults in 4.3.

---

## 1. Shared definitions

- **Request / query_id.** One user question. Every audit event for that question shares a 12-hex `query_id`.
- **Document uid.** `<platform>:<native_id>`, e.g. `confluence:CONF-103`, `slack:T0COMPANYA/db-migration/2001`.
- **Considered document.** Any document that scored above the relevance cut-off, or that was linked
  from one that did. **Every considered document gets a decision record.** Documents below the
  cut-off are never fetched, checked or shown, so they are not logged.
- **Decision.** `allowed`, `denied` or `unavailable`. `unavailable` means "we couldn't find out"
  (platform down, timeout, unknown permission state). It is **always treated as denied** for release.

---

## 2. Permission decision records

### 2.1 Schema `authz_decision/1`

One audit event per **(query, document, stage)**.

| Field | Stored as | Meaning |
|---|---|---|
| `actor` | column | asker's username |
| `query_id` | column | request id |
| `doc_uid`, `platform`, `container` | columns | which document, where |
| `decision` | column | `allowed` / `denied` / `unavailable` |
| `schema` | detail | `"authz_decision/1"`. Bumped on any breaking change |
| `stage` | detail | see 2.2 |
| `reason_code` | detail | stable machine code, see 2.3 |
| `reason` | detail | human explanation. **Audit only, never shown to the asker** |
| `checked_at` | detail | when the platform answered |
| `platform_account` | detail | which platform identity was evaluated, e.g. `atl-557058:jdoe`. Empty at prefilter |
| `resource_version` | detail | doc version at check time |
| `title` | detail | doc title. **Sensitive**: full-audit scope only |

### 2.2 Stages

| Stage | When | Can produce |
|---|---|---|
| `prefilter` | index lookup, using the ACL snapshot from last sync | `denied` only (speed optimisation, never grants) |
| `live` | platform's own rules, checked now | all three |
| `fetch` | content fetch failed after a live allow | `unavailable` |
| `release` | final recheck after the answer is generated (section 3) | all three |

A document can have several records in one request (e.g. `live: allowed`, then `release: denied`).

### 2.3 Reason codes (complete list today)

| Code | Decision | Platform | Meaning |
|---|---|---|---|
| `space_view_and_restrictions_ok` | allowed | Confluence | space view + all page restrictions pass |
| `space_view_missing` | denied | Confluence | no view permission on the space |
| `page_restricted` | denied | Confluence | restriction on the page itself |
| `ancestor_restricted` | denied | Confluence | restriction inherited from a parent page |
| `browse_via_project_role` | allowed | Jira | Browse Projects via a role |
| `browse_project_missing` | denied | Jira | no Browse Projects |
| `issue_security_level` | denied | Jira | not in the issue's security level |
| `unknown_security_level` | unavailable | Jira | security level can't be resolved |
| `channel_member` | allowed | Slack | member of the conversation |
| `not_in_channel` / `not_in_private_channel` | denied | Slack | not a member |
| `shared` | allowed | Drive | shared via user / group / domain / anyone |
| `not_shared` | denied | Drive | no matching share |
| `no_linked_account` | denied | any | user has no account on that platform |
| `not_found` | denied | any | resource doesn't exist (treated like any denial) |
| `timeout` | unavailable | any | check exceeded `CHECK_TIMEOUT_S` |
| `source_error` | unavailable | any | platform error |
| `prefilter_acl_hint` | denied | any | not in ACL snapshot at last sync |
| `fetch_failed` | unavailable | any | content couldn't be fetched |

New codes may be **added** without a schema bump. Renaming or removing a code requires `authz_decision/2`.

### 2.4 Real sample (from the test estate)

```json
{
  "actor": "jdoe", "event": "authz_decision", "query_id": "55811e13e964",
  "platform": "slack", "container": "mig-leads", "doc_uid": "slack:T0COMPANYA/mig-leads/2101",
  "decision": "denied",
  "detail": {
    "schema": "authz_decision/1", "stage": "prefilter",
    "reason_code": "prefilter_acl_hint", "reason": "not in document ACL hint at last sync",
    "checked_at": 1790613455.54, "platform_account": "",
    "resource_version": "1790354255.539321:1", "title": "#mig-leads thread by @ravi"
  }
}
```

### 2.5 "Allowed" vs "actually used"

An `allowed` record means a doc *could* be used. What the model *actually saw* is a separate event,
`context_assembled/1`, listing `{uid, version}` per generation attempt:

```json
{"event": "context_assembled", "query_id": "55811e13e964",
 "detail": {"schema": "context_assembled/1", "attempt": 1,
            "context": [{"uid": "jira:MIG-1", "version": "1790440655.539321"},
                        {"uid": "slack:T0COMPANYA/db-migration/2001", "version": "1790268455.539321:2"}]}}
```

Allowed but not in context happens when a doc is cut for context size, or quarantined for
containing injected instructions (`poisoned_content_quarantined`).

**Tested guarantee:** no denied or unavailable document's text reaches the model
(`test_denied_content_never_reaches_the_model` captures the real model input).

---

## 3. Final recheck before release

### 3.1 Flow

```
generate answer (attempt 1)
  -> recheck EVERY doc in context (not just cited ones: uncited context still shapes wording)
       all allowed?  -> release           release = "released"
       any revoked?  -> log answer_discarded (revoked uids + discarded draft)
                     -> remove revoked docs, regenerate (attempt 2), recheck again
                          all allowed?  -> release       release = "released_after_rebuild"
                          any revoked?  -> neutral reply  release = "withheld"
injection in question -> no generation                    release = "blocked"
```

Each recheck writes a `stage: release` decision record. `unavailable` counts as revoked.

### 3.2 Terminal event `answer_returned/1`

```json
{"event": "answer_returned", "query_id": "55811e13e964",
 "detail": {"schema": "answer_returned/1", "release": "released",
            "answer": "...", "cited": ["jira:MIG-1", "..."], "context": ["jira:MIG-1", "..."],
            "grounding": {"kept": 6, "dropped": 0, "no_answer": false}, "redactions": 0}}
```

`answer_discarded/1` carries `attempt`, `revoked` (list of uids) and `discarded_answer`
(the draft that was never shown). The draft may contain now-restricted content, so it is **full-audit scope only**.

### 3.3 Reconstruction

`audit.reconstruct(query_id=...)` returns per request: `question`, `decisions`, `context_sent`,
`discarded`, `release`, `answer`, `cited`. Tested in
`test_revocation_during_generation_discards_and_rebuilds` and `test_repeated_revocation_withholds_answer`.

### 3.4 Your decision: delivery event

`answer_returned` is written **just before** the HTTP response is sent. A small window remains
between the release recheck and delivery (milliseconds), and there is no record of whether the client
actually received the response. **Proposed default:** you add a `response_delivered` event in the route
(or `response_failed` on error), keyed by `query_id`. That's your layer, so it's your call.

---

## 4. Audit access rules (PROPOSAL)

### 4.1 Roles

| Right | Demo user | Can see |
|---|---|---|
| `audit` | priya (compliance) | Everything: questions, answers, discarded drafts, all decisions and reasons, context versions, request reconstruction |
| `audit_meta` | dana (platform admin) | Event type, time, severity, platform, decision outcome, chain verification. Actors shown as stable pseudonyms (`user-3f2a...`). No question/answer text, doc ids, titles, containers or reasons. No reconstruction |
| neither | everyone else | Nothing. Attempts logged as `audit_access_denied` |

### 4.2 Principles

1. **Operating the system is not reading what people asked.** `admin` grants no source access and no audit content.
2. **Audit records can reveal restricted content** (titles, drafts), so full access is limited to people accountable for it.
3. **Reading the audit trail is itself audited** (`audit_accessed`: viewer, scope, filters, result count).
4. **Pseudonyms are stable and keyed** (HMAC with `IB_AUDIT_PSEUDONYM_KEY`, separate from the session key), so admins can spot one noisy account without learning who it is.
5. **One enforcement point.** Every audit read path goes through `app/audit_policy.py`. If you add a new read path (export, UI), route it through there too.
6. **Sync bookkeeping is operational**, so admins can see it (`/api/sync/state`, `/api/sync/changes`). It holds resource ids and versions only, never titles or content.

### 4.3 Open questions, with the defaults I'll use if there's no reply

| Question | Default |
|---|---|
| Can compliance turn a pseudonym back into a username? | Yes, compliance only, and the lookup is itself audited |
| How long are question/answer text and drafts kept? | 90 days for text, then redacted; decision metadata kept for the demo's lifetime |
| Can users see their own history? | Not for the hackathon. If added later, re-check current access before showing any old citation |
| Separate "security reviewer" role for alerts only? | No, alerts stay in `audit_meta` scope |

---

## 5. Connector contract (your Drive adapter)

### 5.1 The rules

Defined at the top of `app/sources/base.py`. In short:

| Rule | Must |
|---|---|
| R1 | `check()` never raises. Errors, timeouts and unknown states give `unavailable` (fail closed) |
| R2 | Check the **asker's** rights with the platform's own rules, live. The bot being able to read proves nothing |
| R3 | No linked account gives `denied` / `no_linked_account` (handled by the base class) |
| R4 | Missing resource gives `denied` / `not_found` |
| R5 | `acl_hint()` includes everyone `check()` would allow (may include more) |
| R6 | `fetch()` returns `None` only for deleted content. **Raise `SourceUnavailable` on outage** |
| R7 | `list_page()` covers everything with no duplicates. `changes_since()` is ordered and replayable |
| R8 | `start_cursor()` is taken before the crawl |
| R9 | `SourceDoc` has uid `<platform>:<id>`, a version that changes with content, and an https url |
| R10 | `reason_code` is stable. `reason` is audit-only |
| R11 | Checks slower than `CHECK_TIMEOUT_S` give `unavailable` / `timeout` (base class). No retries inside `_check` |
| R12 | Error text is truncated. Never put tokens or keys in exception messages |
| R13 | `ping()` raises `SourceUnavailable` when the platform is down |

### 5.2 Methods you implement

| Method | Real Drive API equivalent |
|---|---|
| `start_cursor()` | `changes.getStartPageToken` |
| `list_page(token, size)` | `files.list` with `pageToken` |
| `changes_since(cursor)` | `changes.list` (kinds: `upsert` / `acl` / `delete`) |
| `fetch(id)` | `files.get` + export. `None` if trashed/deleted |
| `acl_hint(id)` | `permissions.list`, flattened to principals |
| `_check(user, account, id)` | the asker's effective access. Return `(Decision, reason_code, reason, version)` |

The base class already handles errors, timeouts and unlinked accounts. Don't duplicate that.

### 5.3 Tests

Two tiers:

1. **Contract suite (now):** `tests/contract/test_contract.py`, 12 tests parametrised over every
   connector, using **only public connector methods**. Your cases go in `tests/contract/specs.py`
   (matrix, revoke, edit, deletable, inventory).
2. **Live conformance (later):** the same suite pointed at a real test tenant, with `inventory` and the
   matrix read from a fixture manifest instead of the simulator. Build this once you have a Drive test
   account. I'll do the same for Atlassian.

### 5.4 Drive cases you still need to add

Each one becomes a matrix row or an `extra` case:

| Case | Expected |
|---|---|
| Limited-access folder | file metadata may be visible, contents `denied` |
| Domain share | employee `allowed`, contractor `denied` |
| Shared drive membership vs direct file share | both paths `allowed`, removal of either handled |
| File moved out of a shared folder | change kind `acl`, access recalculated |
| Trashed file | `fetch()` is `None`, change kind `delete` |

### 5.5 Change control

Don't edit `base.py` or `test_contract.py` alone. Propose the change, all three of us agree, then bump
the rule list. Adding cases to **your own** spec needs no approval.

---

## 6. Sync bookkeeping

### 6.1 Per platform: `PlatformSyncState`

```json
{"platform": "confluence", "cursor": "0", "initial_load_complete": true,
 "last_attempt": 1790613455.54, "last_success": 1790613455.54, "last_error": "",
 "consecutive_failures": 0, "upserts": 6, "deletes": 0,
 "seconds_since_success": 0, "overdue": false, "health": "ok"}
```

`health` is `ok`, `stale` (no success in 2x the poll interval) or `failing` (last attempt failed).

### 6.2 Per change: `ChangeRecord`

```json
{"platform": "jira", "native_id": "SEC-4", "kind": "upsert", "via": "crawl",
 "source_at": 0.0, "applied_at": 1790613455.54, "version": "1790181455.539321",
 "outcome": "indexed", "error": ""}
```

`via` is `crawl`, `poll`, `webhook` or `read_through`. `outcome` is `indexed`, `removed` or `failed`.
Deletions stay as tombstones: `store.tombstone(platform, native_id)`.

### 6.3 Guarantees (all tested)

- **Change events are hints.** Every change, including a "delete", triggers a fresh fetch. A doc is
  removed only when the platform confirms it's gone. A forged, replayed or out-of-order webhook can't
  remove a live doc.
- **The cursor advances only after a whole page is applied.** On failure it stays put, and the page is
  replayed next time (safe, because applying is idempotent).
- **An outage never deletes anything.** It's recorded as a failure, and health goes to `failing`.
- **A failed webhook** is recorded as `failed`, and the next poll recovers it.
- **Edits made during the first crawl** are replayed, not lost.
- **A failed first crawl is retried** before any incremental sync runs on top of it.
- **State survives restart** (`SqliteSyncStateStore`).

### 6.4 Your storage: what a replacement must guarantee

`SqliteSyncStateStore` is a working reference. Harden or replace it, as long as you implement the
`SyncStateStore` protocol and keep these properties:

1. `put(state)` is atomic (a crash never leaves half a state row).
2. `record(change)` is append-only and ordered.
3. Safe with more than one worker (single writer, or row-level locking on the platform row).
4. The change log has a retention policy (it currently grows forever).

### 6.5 Freshness numbers for the demo

Report **measured** freshness as `applied_at - source_at` from `ChangeRecord`, split by `via`.
Don't report the poll interval setting as if it were a measurement.

---

## 7. Known limitations (honest list)

| Limitation | Owner |
|---|---|
| All four platforms are still simulated. Real Confluence + Jira are my next task | Member 1 |
| Audit rows are written one at a time with no per-request transaction. A crash mid-request leaves a story with no terminal event | Member 3 |
| Small window between release recheck and delivery (section 3.4) | Member 3 |
| A stale ACL snapshot that's *too restrictive* hides a newly shared doc until next sync. This is deliberate: it fails closed | Member 1 |
| A retried first crawl doesn't purge docs deleted between attempts. The next poll or a rebuild fixes it | Member 1 |
| Titles of denied docs and discarded drafts are in the audit log. They're sensitive and need the retention rule in 4.3 | Member 3 |
| Webhook auth is a shared header, not each platform's own signature scheme | Member 3 (routes) + each connector owner |
| Pseudonym and session keys have dev defaults. They **must** be set in any real deployment | Member 3 (deployment) |
| Demo controls (`/api/sim`) can change source permissions. Off unless `IB_DEMO_MODE=1`. Must be off in production | Member 3 (deployment) |

---

## 8. Files touched by Member 1

```
app/sources/base.py           contract R1..R13, PermissionResult, SourceDoc, Change, ChangePage
app/sources/sim.py            simulator plumbing (not used by real connectors)
app/sources/confluence.py     Member 1
app/sources/jira.py           Member 1
app/sources/slack.py          moved, owner Member 2
app/sources/gdrive.py         moved, owner Member 3
app/sources/registry.py       build_connectors()
app/sources/world.py          change feed, change kinds, deletes, outages
app/identity.py               per-platform accounts, admin / auditor split
app/sync.py                   connector-only sync, fetch-on-notify, crawl retry
app/sync_state.py             bookkeeping store (protocol + 2 implementations)
app/brain.py                  decision records, context versions, release recheck, schema versions
app/audit_policy.py           audit access policy
app/audit.py                  reconstruct() returns context, discards, release outcome
app/main.py                   audit routes via policy, sync routes, demo-mode gate
tests/contract/               connector contract suite
tests/test_member1_handoff.py handoff tests
```

---

## Changelog

**v2 (this version)**
- Separated delivered items from the one proposal (section 4) and added defaults with a sign-off date
- Added schema versions (`authz_decision/1` etc.) to every record you consume
- Added the complete reason-code list, real sample records, and a definition of "considered document"
- **Fixed:** delete webhooks were trusted blindly. Now every change is confirmed by fetching
- **Fixed:** a failed first crawl could be followed by incremental sync on a half-built index
- **Fixed:** demo controls were always on. Now gated behind `IB_DEMO_MODE`
- **Fixed:** the contract suite called a simulator-only method, so real connectors couldn't run it
- Documented R11 to R13 (timeout, safe error text, `ping`)
- Added a known-limitations table with owners, and storage requirements for your durable store

**v1** initial handoff.
