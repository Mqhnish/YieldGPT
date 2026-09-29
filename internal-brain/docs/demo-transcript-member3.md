# Member 3 demonstration transcript

Generated 2026-09-29 05:14:01 +08 by `scripts/demo_member3.py` on isolated data. Checkpoint store: `s3_object_lock` (assurance `independent_worm`).

Result: all scenes behaved as expected.

## 1. An employee asks a cross-platform question

- `jdoe` asks: “What's the status of the database migration project and were there any blockers raised in Slack last week?”
- HTTP 200, request `9583f230b06a452c`, query `58fa69f2f5da`
- Cited: `jira:MIG-1`, `gdrive:DRV-2`, `slack:db-migration/2001`, `jira:MIG-7`
- The response left the server only after this request's audit rows were covered by a committed checkpoint.

## 2. A contractor asks for restricted material

- `kim` receives: “I couldn't find information you have access to that answers this. Try rephrasing, or ask the owner of the relevant space, project or channel.” with 0 citations and no hidden titles.

## 3. Compliance reconstructs the request (priya, full audit scope)

- Question: “What's the status of the database migration project and were there any blockers raised in Slack last week?”
- Release `released`, terminal `answer_returned`, delivery `delivered`, generation `extractive`
- Versions actually sent to the model: `jira:MIG-1@1790457241.690402`, `gdrive:DRV-2@1790111641.690402`, `slack:db-migration/2001@7fa290e71cf4f35312e204ab9225db3c728e7357b8493b9108e97d6636c46801`, `jira:MIG-7@1790284441.690402`
- Permitted but not sent: none
- Decisions: live:allowed ×8, live:denied ×1, release:allowed ×8

## 4. The platform admin cannot read what was asked (dana, metadata scope)

- Request reconstruction: HTTP 403
- Metadata view of the same request: `{'id': 31, 'ts': 1790630041.783563, 'event': 'query_received', 'severity': 'info', 'platform': '', 'decision': '', 'actor': 'user-765af3bc1d'}`
- Question text visible anywhere in the admin view: False

## 5. The verifier checks the chain against the protected checkpoints

- Status **verified**, 42 rows, verified through row 40, 2 uncheckpointed
- Checkpoint store `s3_object_lock`, assurance `independent_worm`
- Sealed text: {'sealed': 28, 'ok': 28, 'redacted': 0, 'unchecked': 0}

## 6. Tampering is detected (on copies of the audit database)

- Edit a row and recompute every hash: **failed**: chain rewritten (anchor mismatch) at row 20
- Delete the checkpointed tail: **failed**: log truncated (anchored row missing) at row 38

## 7. The checkpoint store is unreachable

- A new answer is withheld: HTTP 503 “The answer could not be recorded securely, so it was not released. Please try again.”
- Verifier: **unverifiable**: checkpoint store unreachable (CheckpointError)

## 8. Restart recovery

- 1 interrupted request(s) given an explicit terminal record: terminal `request_abandoned`, delivery `abandoned`, request `demo-crash`
