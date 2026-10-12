# Synthetic retrieval benchmark

Generated: 2026-10-09T21:45:06.621516+00:00

This measures local retrieval on generated documents. It excludes authorization checks, API calls, answer generation, audit persistence, ingestion networking and concurrency. Do not present it as production latency.

- Size: **19,700 source objects** (full)
- Corpus SHA-256: `ab244e27f06b00c2c50f39a96f855a90db2ad8f2b59e1047ebf0f7af91d71a98`
- Mean document length: 85.1 words
- Build time: 0.762 seconds
- Search p50 / p95: 4.491 / 261.634 ms over 40 warmed samples
- Process peak resident memory: 239.4 MiB (whole process, not index-only)
- Expected document found in top 10: 8/8

| Platform | Objects | Containers | Tenants |
|---|---:|---:|---:|
| confluence | 12,500 | 52 | 1 |
| jira | 3,200 | 32 | 1 |
| slack | 2,200 | 220 | 3 |
| gdrive | 1,800 | 150 | 1 |

The corpus contains repeated operational topics, variable sentence lengths, parent references, hierarchical Drive container tags, multiple Slack workspaces, and varied ACL hints. These hints are workload metadata; they do not exercise native Confluence/Jira/Slack/Drive access rules. Eight hand-written target documents measure retrieval sanity, not a representative production relevance distribution.

| Query | Expected source found |
|---|---|
| How does Bluefin recover missing audit events? | PASS |
| What should happen when Juniper replica lag exceeds twelve seconds? | PASS |
| How is Orion preventing duplicate settlement transfers? | PASS |
| Why is the Cedar billing rollback blocked? | PASS |
| What did the Harbor failover discussion say to freeze before moving traffic? | PASS |
| What should the downstream index do when Willow messages expire? | PASS |
| Which checks are required for the Kestrel payout launch? | PASS |
| What information is recorded in Maple support access reviews? | PASS |
