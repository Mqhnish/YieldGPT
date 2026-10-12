# Load test, 25 users for 300 s (fixture, stub model)

- Date (UTC): 2026-10-12T11:28:37+00:00
- Commit: `f12a7e4`
- Machine: macOS-27.0-arm64-arm-64bit-Mach-O / arm64 / 15 CPUs / Python 3.13.15
- Server: uvicorn app.server:app, 1 process, 127.0.0.1 (real HTTP)
- Checkpoint store: `s3_object_lock`
- Personas (round robin over threads): jdoe, ravi, asha, kim, priya, dana; questions drawn at random from 12 (answered, no-answer and denied cases)

| Measure | Result |
|---|---|
| Duration | 300.7 s |
| Ask requests | 19223 (status codes {'200': 19223}) |
| Ask success rate | 100.00% |
| Completed answers / s (P15) | 63.93 |
| Answers with citations / s | 31.24 |
| Ask latency under load p50 / p95 / max ms | 234.4 / 1099.8 / 4573.1 |
| Own citation previews | 2808, success 100.00% |
| Permission leaks (connector check() + audit decisions per citation) | 0 |
| Audit gaps (release + delivery record + checkpoint per answer) | 0 |
| Cross-user evidence attempts / hits | 1937 / 0 |
| Duplicate query ids | 0 |
| Checkpoints written | 39489 |
| Audit chain after run | verified, 348936 rows, assurance independent_worm |

Pass: P14 success >= 99% PASS, P14 zero leaks PASS, P14 zero audit gaps PASS, P14 zero cross-user cache hits PASS, P15 >= 5 answers/s PASS

Reproduce: `python scripts/load_test.py` (set IB_CHECKPOINT_* to use the MinIO store).
