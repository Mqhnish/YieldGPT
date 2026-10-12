# End-to-end latency (fixture, stub model)

- Date (UTC): 2026-10-12T11:02:47+00:00
- Commit: `8c75bf1`
- Machine: macOS-27.0-arm64-arm-64bit-Mach-O / arm64 / Python 3.13.15
- Path: TestClient(app.server:app), in-process ASGI with AuditedDelivery
- Checkpoint store: `local_file`
- Requests: 20 warm-up (discarded) + 120 measured, 12 persona/question pairs cycled; 80 citation previews

## Headline

| Measure | n | p50 ms | p95 ms | max ms | Target |
|---|---|---|---|---|---|
| P07/P08 end to end (client) | 120 | 19.2 | 27.0 | 40.0 | p50 <= 4000, p95 <= 8000 |
| P09 authorization + read | 120 | 4.1 | 7.7 | 8.2 | p95 <= 2000 |
| P12 audit/release (release authz + checkpoint + delivery) | 120 | 6.7 | 9.4 | 24.2 | p95 <= 500 |
| P13 citation preview (client) | 80 | 8.4 | 9.6 | 9.9 | p95 <= 2000 |

Pass: P07 PASS, P09 PASS, P12 PASS, P13 PASS

## Pipeline phases (query_performance audit events)

| Measure | n | p50 ms | p95 ms | max ms | Target |
|---|---|---|---|---|---|
| retrieval_ms | 120 | 0.1 | 2.0 | 2.7 |  |
| authorization_and_read_ms | 120 | 4.1 | 7.7 | 8.2 |  |
| generation_and_grounding_ms | 120 | 1.4 | 1.8 | 2.4 |  |
| release_authorization_ms | 120 | 2.9 | 5.0 | 5.4 |  |
| checkpoint_and_delivery_ms | 120 | 4.1 | 5.0 | 19.6 |  |
| total_ms | 120 | 13.8 | 20.2 | 22.4 |  |

## End to end by outcome

| Measure | n | p50 ms | p95 ms | max ms | Target |
|---|---|---|---|---|---|
| answered | 80 | 23.2 | 27.2 | 40.0 |  |
| no_answer | 40 | 14.0 | 17.4 | 17.9 |  |

## End to end by cited source mix

| Measure | n | p50 ms | p95 ms | max ms | Target |
|---|---|---|---|---|---|
| confluence+gdrive+jira | 10 | 25.8 | 27.5 | 28.1 |  |
| confluence+gdrive+jira+slack | 30 | 23.1 | 27.0 | 27.2 |  |
| confluence+jira | 10 | 19.9 | 32.0 | 40.0 |  |
| gdrive+jira+slack | 10 | 23.4 | 25.0 | 25.1 |  |
| gdrive+slack | 10 | 15.9 | 17.8 | 18.1 |  |
| jira | 10 | 24.4 | 27.9 | 28.4 |  |
| none | 40 | 14.0 | 17.4 | 17.9 |  |

Stub model, so generation time is near zero; real-model latency (P10) is measured separately by Member 2. Reproduce: `python scripts/bench_e2e.py`.
