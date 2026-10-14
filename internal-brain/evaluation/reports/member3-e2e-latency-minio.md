# End-to-end latency (fixture, stub model)

- Date (UTC): 2026-10-12T11:04:30+00:00
- Commit: `8c75bf1`
- Machine: macOS-27.0-arm64-arm-64bit-Mach-O / arm64 / Python 3.13.15
- Path: TestClient(app.server:app), in-process ASGI with AuditedDelivery
- Checkpoint store: `s3_object_lock`
- Requests: 20 warm-up (discarded) + 120 measured, 12 persona/question pairs cycled; 80 citation previews

## Headline

| Measure | n | p50 ms | p95 ms | max ms | Target |
|---|---|---|---|---|---|
| P07/P08 end to end (client) | 120 | 37.5 | 50.9 | 58.6 | p50 <= 4000, p95 <= 8000 |
| P09 authorization + read | 120 | 6.4 | 17.1 | 18.9 | p95 <= 2000 |
| P12 audit/release (release authz + checkpoint + delivery) | 120 | 15.5 | 26.2 | 34.2 | p95 <= 500 |
| P13 citation preview (client) | 80 | 17.0 | 28.2 | 32.2 | p95 <= 2000 |

Pass: P07 PASS, P09 PASS, P12 PASS, P13 PASS

## Pipeline phases (query_performance audit events)

| Measure | n | p50 ms | p95 ms | max ms | Target |
|---|---|---|---|---|---|
| retrieval_ms | 120 | 0.1 | 2.4 | 3.6 |  |
| authorization_and_read_ms | 120 | 6.4 | 17.1 | 18.9 |  |
| generation_and_grounding_ms | 120 | 1.6 | 8.7 | 10.3 |  |
| release_authorization_ms | 120 | 3.1 | 12.6 | 14.7 |  |
| checkpoint_and_delivery_ms | 120 | 11.9 | 18.8 | 22.3 |  |
| total_ms | 120 | 23.5 | 36.2 | 42.4 |  |

## End to end by outcome

| Measure | n | p50 ms | p95 ms | max ms | Target |
|---|---|---|---|---|---|
| answered | 80 | 41.8 | 51.9 | 58.6 |  |
| no_answer | 40 | 26.0 | 35.4 | 37.9 |  |

## End to end by cited source mix

| Measure | n | p50 ms | p95 ms | max ms | Target |
|---|---|---|---|---|---|
| confluence+gdrive+jira | 10 | 48.5 | 55.7 | 56.0 |  |
| confluence+gdrive+jira+slack | 30 | 44.5 | 51.4 | 58.6 |  |
| confluence+jira | 10 | 37.7 | 44.2 | 44.9 |  |
| gdrive+jira+slack | 10 | 41.4 | 47.0 | 47.4 |  |
| gdrive+slack | 10 | 32.4 | 38.1 | 39.7 |  |
| jira | 10 | 44.0 | 48.8 | 48.9 |  |
| none | 40 | 26.0 | 35.4 | 37.9 |  |

Stub model, so generation time is near zero; real-model latency (P10) is measured separately by Member 2. Reproduce: `python scripts/bench_e2e.py`.
