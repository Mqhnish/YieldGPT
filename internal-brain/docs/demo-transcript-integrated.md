# Member 3 demonstration transcript

Generated 2026-09-29 15:46:22 +04 by `scripts/demo_member3.py` on isolated data. Checkpoint store: `local_file` (assurance `local_only`).

Result: all scenes behaved as expected.

## 1. An employee asks a cross-platform question

- `jdoe` asks: “What's the status of the database migration project and were there any blockers raised in Slack last week?”
- HTTP 200, request `d7ff423648a34d03`, query `9ee041640297`
- Cited: `jira:MIG-1`, `gdrive:DRV-2`, `slack:T0COMPANYA/db-migration/2001`, `jira:MIG-7`
- The response left the server only after this request's audit rows were covered by a committed checkpoint.

## 2. A contractor asks for restricted material

- `kim` receives: “I couldn't find information you have access to that answers this. Try rephrasing, or ask the owner of the relevant space, project or channel.” with 0 citations and no hidden titles.

## 3. Compliance reconstructs the request (priya, full audit scope)

- Question: “What's the status of the database migration project and were there any blockers raised in Slack last week?”
- Release `released`, terminal `answer_returned`, delivery `delivered`, generation `extractive`
- Versions actually sent to the model: `jira:MIG-1@1790509581.951827`, `gdrive:DRV-2@1790163981.951827`, `slack:T0COMPANYA/db-migration/2001@ade960ffd429462d7b0131748116b70c727b1d115f1481c3788b6d03f85d8269`, `jira:MIG-7@1790336781.951827`
- Permitted but not sent: none
- Decisions: live:allowed ×8, live:denied ×1, release:allowed ×8

## 4. The platform admin cannot read what was asked (dana, metadata scope)

- Request reconstruction: HTTP 403
- Metadata view of the same request: `{'id': 33, 'ts': 1790682381.999104, 'event': 'query_received', 'severity': 'info', 'platform': '', 'decision': '', 'actor': 'user-0376cc4485'}`
- Question text visible anywhere in the admin view: False

## 5. The verifier checks the chain against the protected checkpoints

- Status **verified**, 46 rows, verified through row 42, 4 uncheckpointed
- Checkpoint store `local_file`, assurance `local_only`
- Sealed text: {'sealed': 28, 'ok': 28, 'redacted': 0, 'unchecked': 0}

## 6. Tampering is detected (on copies of the audit database)

- Edit a row and recompute every hash: **failed**: chain rewritten (anchor mismatch) at row 20
- Delete the checkpointed tail: **failed**: log truncated (anchored row missing) at row 40

## 7. The checkpoint store is unreachable

- A new answer is withheld: HTTP 503 “The answer could not be recorded securely, so it was not released. Please try again.”
- Verifier: **unverifiable**: checkpoint store unreachable (CheckpointError)

## 8. Restart recovery

- 1 interrupted request(s) given an explicit terminal record: terminal `request_abandoned`, delivery `abandoned`, request `demo-crash`
