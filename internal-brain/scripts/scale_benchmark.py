"""Scale benchmark on the brief-sized synthetic Company A.

  python scripts/scale_benchmark.py                 # full size (see app/seeding/scale.py DEFAULTS)
  python scripts/scale_benchmark.py --scale 0.1     # 10% for a quick run
  python scripts/scale_benchmark.py --seed 7 --out data/bench.json --matrix data/matrix.csv

Reports: estate size, ingestion time per platform, question latency percentiles per
persona, permission checks per question, and a permission matrix (persona x document
-> expected decision) for retrieval/answer evaluation.

Confluence + Jira run through the REAL HTTP connectors against the fake site (fixture
mode), so ingestion includes the HTTP layer, parsing and pagination. The network itself
is in-process, so add your real API latency on top: this measures our code, not Atlassian.
"""
import argparse
import csv
import json
import os
import pathlib
import platform as pyplatform
import statistics
import sys
import tempfile
import time

sys.path.insert(0, ".")
os.environ.setdefault("IB_AUDIT_DB", os.path.join(tempfile.mkdtemp(), "bench_audit.db"))
os.environ.setdefault("IB_ANCHOR_PATH", os.path.join(tempfile.mkdtemp(), "bench_anchors.jsonl"))
os.environ.setdefault("IB_ATLASSIAN_MODE", "fixture")

from app import audit  # noqa: E402
from app.brain import Brain  # noqa: E402
from app.identity import USERS  # noqa: E402
from app.seeding.scale import DEFAULTS, generate, summary  # noqa: E402
from app.sources.registry import build_connectors  # noqa: E402

QUESTIONS = [
    "What's the status of the database migration project and were there any blockers raised in Slack last week?",
    "What was the root cause of the payment outage last quarter, and what follow-up tickets were created?",
    "What's the latest runbook for the payment-service incident?",
    "Show me the security incident report from the Q3 breach",
    "Which settlement batch incidents happened recently and who owns the fix?",
]


def pct(xs, p):
    xs = sorted(xs)
    return round(xs[min(len(xs) - 1, int(p / 100 * len(xs)))], 1) if xs else None


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--seed", type=int, default=7)
    ap.add_argument("--scale", type=float, default=1.0)
    ap.add_argument("--out", default="data/bench.json")
    ap.add_argument("--matrix", default="data/permission_matrix.csv")
    ap.add_argument("--matrix-docs", type=int, default=3000, help="documents sampled into the matrix")
    a = ap.parse_args()

    sizes = {k: max(1, int(v * a.scale)) for k, v in DEFAULTS.items()}
    sizes["workspaces"] = DEFAULTS["workspaces"]
    t = time.perf_counter()
    world = generate(a.seed, **sizes)
    gen_s = time.perf_counter() - t

    audit.init()
    t = time.perf_counter()
    brain = Brain(world=world)   # full crawl of all four platforms
    ingest_s = time.perf_counter() - t
    per_platform = {p: st.upserts for p, st in ((p, brain.syncer.state(p)) for p in brain.connectors)}

    lat, checks = {}, []
    for u in sorted(USERS):
        for q in QUESTIONS:
            t = time.perf_counter()
            r = brain.ask(USERS[u], q)
            lat.setdefault(u, []).append((time.perf_counter() - t) * 1000)
            checks.append(len(audit.search(query_id=r["query_id"], event="authz_decision", limit=1_000_000)))
    all_lat = [x for v in lat.values() for x in v]

    # permission matrix: what each persona SHOULD be able to see (simulator ground truth)
    sim = build_connectors(world, atlassian_mode="sim")
    docs = [(p, nid) for p, c in sim.items() for nid in sorted(c._ids())]
    step = max(1, len(docs) // a.matrix_docs)
    sample = docs[::step][: a.matrix_docs]
    pathlib.Path(a.matrix).parent.mkdir(parents=True, exist_ok=True)
    allowed = 0
    with open(a.matrix, "w", newline="") as f:
        wr = csv.writer(f)
        wr.writerow(["platform", "doc_id"] + sorted(USERS))
        for p, nid in sample:
            row = [sim[p].check(USERS[u], nid).decision.value for u in sorted(USERS)]
            allowed += row.count("allowed")
            wr.writerow([p, nid] + row)

    result = {
        "seed": a.seed, "scale": a.scale, "estate": summary(world),
        "hardware": {"python": pyplatform.python_version(), "machine": pyplatform.machine(), "cpus": os.cpu_count()},
        "generate_s": round(gen_s, 2), "ingest_s": round(ingest_s, 2), "indexed_docs": len(brain.index),
        "ingested_per_platform": per_platform,
        "question_latency_ms": {"p50": pct(all_lat, 50), "p95": pct(all_lat, 95), "max": round(max(all_lat), 1),
                                "per_persona_p50": {u: pct(v, 50) for u, v in lat.items()}},
        "authz_decisions_per_question": {"mean": round(statistics.mean(checks), 1), "max": max(checks)},
        "permission_matrix": {"file": a.matrix, "docs": len(sample), "personas": len(USERS),
                              "allowed_share": round(allowed / (len(sample) * len(USERS)), 3)},
        "note": "In-process fake network. Add real API latency per HTTP call for live estimates.",
    }
    pathlib.Path(a.out).parent.mkdir(parents=True, exist_ok=True)
    pathlib.Path(a.out).write_text(json.dumps(result, indent=2))
    print(json.dumps(result, indent=2))


if __name__ == "__main__":
    main()
