# A07 audit search latency (synthetic)

- Date (UTC): 2026-10-12T11:00:53+00:00
- Commit: `8c75bf1`
- Machine: macOS-27.0-arm64-arm-64bit-Mach-O / arm / Python 3.13.15
- Audit rows: 100,005 (5,017 synthetic requests, filled via `audit.log_many` in 31.6 s)
- Path: POST /api/compliance/requests (TestClient, in-process) -> audit_policy.reconstruct -> audit.search
- Target: p95 <= 2000 ms over 100,000 events via compliance API
- Result: worst p95 950.47 ms, **PASS**

| Search | Stories returned | Runs | p50 ms | p95 ms | max ms |
|---|---|---|---|---|---|
| by user | 26 | 50 | 82.07 | 84.59 | 88.08 |
| by container | 339 | 50 | 910.07 | 950.47 | 1031.24 |
| by platform | 117 | 50 | 320.1 | 343.27 | 346.72 |
| by decision | 90 | 50 | 249.63 | 256.99 | 264.4 |
| by time range (10% of log) | 25 | 50 | 86.95 | 89.53 | 90.75 |
| user + platform + decision | 266 | 50 | 720.34 | 736.93 | 759.48 |

Reproduce: `python scripts/bench_audit_search.py`. Each search returns at most 500 matching rows (the `audit.search` default limit) grouped into request stories, and is itself audited as `audit_accessed`.
