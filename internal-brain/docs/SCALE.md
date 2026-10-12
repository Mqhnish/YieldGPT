# Scale mode and benchmark

Owner: Member 1 (generator + matrix). Benchmark execution and retrieval evaluation: Member 2.

## The estate

`app/seeding/scale.py` generates a reproducible Company A at the size the brief describes. The hand-written
demo company is kept inside it, so the scenario questions still have their answers, hidden in a large haystack.

| | Brief | Generated (seed 7) |
|---|---|---|
| Confluence spaces / pages | 50+ / 12,000+ | 55 / 12,506 |
| Jira projects / issues | 30+ / not given | 35 / 6,408 (our choice) |
| Slack workspaces / channels / threads | multiple / 200+ / not given | 5 / 226 / 8,807 (our choice) |
| Drive folders / files | shared + personal / not given | 123 / 3,005 (our choice) |

Permissions vary on purpose: all-employee spaces, team spaces, two-team spaces, single-user page
restrictions, group-restricted subtrees, 5% of issues behind a security level, 35% private channels,
a few vendor-shared channels, personal files, and a few "anyone with the link" files. Every page body
is distinct (generated from team-specific vocabulary), not one sentence copied 12,000 times.

## Benchmark

```bash
python scripts/scale_benchmark.py              # full size
python scripts/scale_benchmark.py --scale 0.1  # quick run
```

Writes `data/bench.json` and `data/permission_matrix.csv` (persona x 3,000 sampled documents ->
expected decision, the ground truth for evaluating that retrieval never leaks).

### Result (10 Oct 2026, seed 7, full size, fixture mode)

Machine: Mohnish's MacBook Pro, Apple M5 (10 cores), 16 GB RAM, macOS 27.0, Python 3.14.7. Commit `46fbf72`
on branch `mohnish/atlassian-proof`. Every number below is **synthetic data over an in-process fake network**.

| Measure | Value |
|---|---|
| Documents ingested | 30,726 (12,506 pages, 6,408 issues, 8,807 Slack threads, 3,005 Drive files) |
| Estate generation | 0.19 s |
| Full ingestion (all 4 platforms, Confluence + Jira through the HTTP connectors) | 4.4 s |
| Question latency p50 / p95 / max (30 questions: 6 personas x 5 questions, whole pipeline incl. audit) | 468 / 1,307 / 1,513 ms |
| Permission decisions recorded per question (mean / max) | 3,012 / 7,761 |

Before this branch the same run measured **3,347 / 11,879 / 12,159 ms**. Two fixes, no permission check removed or relaxed:

1. The audit trail wrote every per-document decision in its own sqlite transaction, followed by a probing-detection
   scan. A broad question decides thousands of candidates. Each pipeline phase now writes its rows in one transaction
   (`audit.log_many`), same rows, same order, same sealing and hash chain (`tests/test_audit_batching.py`).
2. `index.search` re-tokenized every candidate's text on every query. Terms are now cached at upsert, with identical
   scores (`tests/test_index_cached_terms.py`).

The decision counts were previously reported as "max 500" because the benchmark counted them with the audit
search's default 500-row limit. They are now counted in full.

**Local retrieval (metric P04)** is measured separately by `scripts/benchmark.py --size full` (19,700 objects,
index search only, 40 warmed samples): p50 / p95 **4.5 / 262 ms** (target p95 <= 500 ms, met; it was 769 ms on
this machine before the index fix), build 0.76 s, peak process memory 239 MiB, expected document in top 10: 8/8.
Report: `evaluation/reports/synthetic-benchmark.md`.

**What this does and doesn't show.** The network is in-process (fixture mode), so these numbers measure
our code: crawling, parsing, indexing, permission fan-out, the audit trail. They do not include Atlassian's
API latency or rate limits. Against a live site, add per-call latency: a question makes about a dozen
Atlassian calls, parallel and batched (see `docs/ATLASSIAN_SETUP.md`). Synthetic scale proves behaviour
on a benchmark, not live SaaS throughput at that scale.
