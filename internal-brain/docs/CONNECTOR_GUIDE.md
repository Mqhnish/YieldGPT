# Building a real connector (Slack: Member 2, Drive: Member 3)

Confluence and Jira already follow this pattern. Copy it and your connector works three ways:
offline tests, offline demo, and live.

**Build it in CodeBuddy and screenshot the chats.** The handbook makes CodeBuddy/WorkBuddy usage
mandatory with at least 3 screenshots as proof; without them the project isn't scored.

## The pattern

| Piece | Atlassian example | What you write |
|---|---|---|
| HTTP client with fail-closed errors | `app/sources/atlassian_client.py` | reuse its error mapping; Slack returns `{"ok": false, "error": ...}` with HTTP 200, so map `ok=false` too |
| Real connector | `confluence_cloud.py`, `jira_cloud.py` | implement the contract in `app/sources/base.py` (R1..R13) |
| Change polling (if the API has no change feed) | `cloud_polling.py` | Slack: Events API + `conversations.history` with `oldest`. Drive: `changes.list` has a real change feed, so you probably don't need this |
| Fake server from the simulator | `fake_atlassian.py` | same JSON shapes as the real API, built live from `World` |
| Registry switch | `registry.py` | add an `IB_SLACK_MODE` / `IB_DRIVE_MODE` like `IB_ATLASSIAN_MODE` |
| Contract tests | `tests/contract/` | add `(spec, "fixture")` cases for your platform in `CASES` |
| Seeder (optional) | `app/seeding/atlassian_seed.py` | fill a free workspace / Drive with the demo data |

## The permission check is the whole point

Never decide access from the bot's view. Ask the platform about the **asker**:

- **Slack**: the asker can read a thread if they are a member of the conversation:
  `conversations.members` (paginate) or check membership from the user's side. Public-channel access
  depends on the token type and scopes (see the plan's platform notes): decide and document which you support.
  Treat DMs and private channels as membership-only. Unknown, errors and rate limits mean `unavailable`.
- **Drive**: the asker can read a file if a permission on the file (or inherited from a folder) matches
  their email, a group they're in, their domain, or "anyone". `permissions.list` on the file. Limited-access
  folders can show metadata but hide contents: handle them or explicitly declare them out of scope.
  "Domain" sharing needs a Google Workspace domain; on personal accounts, test user/anyone shares.

## Done when

1. `python -m pytest tests/contract -q` passes for your platform in `sim` **and** `fixture`.
2. Revocation without an event is caught (contract `test_R2_revocation_without_event`).
3. An outage gives `unavailable`, never an allow (`test_R1_outage_fails_closed`).
4. Errors never contain your token (copy `tests/test_atlassian_http.py`).
5. A live check against your real workspace passes (copy `scripts/atlassian_live_check.py`).
