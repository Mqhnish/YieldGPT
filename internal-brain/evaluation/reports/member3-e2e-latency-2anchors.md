# End-to-end latency (fixture, stub model)

- Date (UTC): 2026-10-12T11:31:36+00:00
- Commit: `d4d7b35`
- Machine: macOS-27.0-arm64-arm-64bit-Mach-O / arm64 / Python 3.13.15
- Path: TestClient(app.server:app), in-process ASGI with AuditedDelivery
- Checkpoint store: `multi(s3_object_lock,s3_object_lock)`
- Requests: 20 warm-up (discarded) + 120 measured, 12 persona/question pairs cycled; 80 citation previews

## Headline

| Measure | n | p50 ms | p95 ms | max ms | Target |
|---|---|---|---|---|---|
| P07/P08 end to end (client) | 120 | 32.5 | 47.8 | 75.8 | p50 <= 4000, p95 <= 8000 |
| P09 authorization + read | 120 | 6.4 | 13.3 | 17.7 | p95 <= 2000 |
| P12 audit/release (release authz + checkpoint + delivery) | 120 | 13.6 | 24.5 | 34.9 | p95 <= 500 |
| P13 citation preview (client) | 80 | 14.8 | 23.5 | 26.6 | p95 <= 2000 |

Pass: P07 PASS, P09 PASS, P12 PASS, P13 PASS

## Pipeline phases (query_performance audit events)

| Measure | n | p50 ms | p95 ms | max ms | Target |
|---|---|---|---|---|---|
| retrieval_ms | 120 | 0.1 | 2.2 | 3.5 |  |
| authorization_and_read_ms | 120 | 6.4 | 13.3 | 17.7 |  |
| generation_and_grounding_ms | 120 | 1.5 | 7.8 | 9.1 |  |
| release_authorization_ms | 120 | 3.1 | 10.6 | 13.3 |  |
| checkpoint_and_delivery_ms | 120 | 9.9 | 16.5 | 28.8 |  |
| total_ms | 120 | 20.1 | 32.0 | 39.4 |  |

## End to end by outcome

| Measure | n | p50 ms | p95 ms | max ms | Target |
|---|---|---|---|---|---|
| answered | 80 | 36.1 | 49.5 | 68.4 |  |
| no_answer | 40 | 22.5 | 36.7 | 75.8 |  |

## End to end by cited source mix

| Measure | n | p50 ms | p95 ms | max ms | Target |
|---|---|---|---|---|---|
| confluence+gdrive+jira | 10 | 41.9 | 63.1 | 68.4 |  |
| confluence+gdrive+jira+slack | 30 | 38.7 | 44.1 | 47.7 |  |
| confluence+jira | 10 | 31.5 | 39.7 | 43.5 |  |
| gdrive+jira+slack | 10 | 35.6 | 47.7 | 52.1 |  |
| gdrive+slack | 10 | 27.3 | 31.7 | 34.6 |  |
| jira | 10 | 38.5 | 51.9 | 53.9 |  |
| none | 40 | 22.5 | 36.7 | 75.8 |  |

Stub model, so generation time is near zero; real-model latency (P10) is measured separately by Member 2. Reproduce: `python scripts/bench_e2e.py`.
