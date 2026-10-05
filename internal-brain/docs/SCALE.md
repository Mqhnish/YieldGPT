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

### Result (1 Oct 2026, seed 7, full size, 2 vCPU cloud container, Python 3.11)

| Measure | Value |
|---|---|
| Documents ingested | 30,726 |
| Full ingestion (all 4 platforms, Confluence + Jira through the HTTP connectors) | 13.9 s |
| Question latency p50 / p95 / max (30 questions: 6 personas x 5 questions) | 191 / 492 / 721 ms |
| Permission decisions recorded per question (mean / max) | 24 / 280 |

**What this does and doesn't show.** The network is in-process (fixture mode), so these numbers measure
our code: crawling, parsing, indexing, permission fan-out, the audit trail. They do not include Atlassian's
API latency or rate limits. Against a live site, add per-call latency: a question makes about a dozen
Atlassian calls, now parallel and batched (see `docs/ATLASSIAN_SETUP.md`). Synthetic scale proves behaviour
on a benchmark, not live SaaS throughput at that scale.

Rerun on the demo machine before quoting these numbers in the submission.
