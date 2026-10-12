#!/usr/bin/env python3
"""A07: compliance audit search latency over a synthetic audit log.

Fills a fresh temp audit DB with --events rows through audit.log_many (one batch per
synthetic request: query_received, per-candidate authz_decision rows, context_assembled,
answer_returned), then times compliance searches through the compliance API
(POST /api/compliance/requests as the compliance persona, which goes through
audit_policy.reconstruct). Writes evaluation/reports/member3-audit-search-latency.{json,md}.

    python scripts/bench_audit_search.py [--events 100000] [--runs 50]

Label: synthetic (generated events, not real company data).
"""
import argparse
import json
import os
import platform
import random
import statistics
import subprocess
import sys
import tempfile
import time
from datetime import datetime, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

PLATFORMS = {"confluence": ["payment-gateway", "eng-handbook", "risk-ops", "hr-policies", "finance-close"],
             "jira": ["PAY", "SEC", "RISK", "DATA", "OPS"],
             "slack": ["#incidents", "#payments-eng", "#data-platform", "#general", "#leadership"],
             "gdrive": ["Finance Shared", "Board Pack", "Eng Specs", "HR", "Personal"]}


def pct(xs, p):
    return round(statistics.quantiles(xs, n=100, method="inclusive")[p - 1], 2)


def fill(audit, actors, n_events, rng):
    """One log_many batch per synthetic request until n_events rows exist."""
    written, q = 0, 0
    while written < n_events:
        q += 1
        actor, qid, rid = rng.choice(actors), f"q{q:06d}", f"r{q:06d}"
        base = {"query_id": qid, "request_id": rid}
        rows = [(actor, "query_received", {**base, "question": f"synthetic question {q}"})]
        for i in range(rng.randint(10, 24)):
            plat = rng.choice(list(PLATFORMS))
            cont = rng.choice(PLATFORMS[plat])
            denied = rng.random() < 0.35
            rows.append((actor, "authz_decision", {
                **base, "platform": plat, "container": cont, "doc_uid": f"{plat}:{cont}-{rng.randint(1, 4000)}",
                "decision": "denied" if denied else "allowed", "severity": "warning" if denied else "info",
                "schema": "authz_decision/1", "stage": rng.choice(["prefilter", "live", "release"]),
                "reason_code": "not_member" if denied else "member", "reason": "synthetic", "title": f"doc {i}"}))
        rows.append((actor, "context_assembled", {**base, "attempt": 1, "context": []}))
        rows.append((actor, "answer_returned", {**base, "answer": f"synthetic answer {q}"}))
        rows = rows[:n_events - written]
        audit.log_many(rows)
        written += len(rows)
    return q


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument("--events", type=int, default=100_000)
    ap.add_argument("--runs", type=int, default=50)
    ap.add_argument("--out", default=str(ROOT / "evaluation" / "reports" / "member3-audit-search-latency"))
    args = ap.parse_args()

    tmp = tempfile.mkdtemp(prefix="ib-a07-")
    os.environ.update(IB_DATA_DIR=tmp, IB_AUDIT_DB=f"{tmp}/audit.db", IB_ANCHOR_PATH=f"{tmp}/anchors.jsonl",
                      IB_ENV_FILE=f"{tmp}/.env", IB_LLM_PROVIDER="stub")
    from fastapi.testclient import TestClient
    from app import audit, server
    from app.identity import USERS

    audit.init()
    rng = random.Random(7)
    actors = sorted(u for u in USERS if USERS[u].kind == "employee")
    t0 = time.time()
    requests = fill(audit, actors, args.events, rng)
    fill_s, t1 = time.time() - t0, time.time()
    rows = audit.head()[0]

    mid = t0 + (t1 - t0) / 2
    span = (t1 - t0) * 0.05
    searches = {"by user": {"actor": "jdoe"},
                "by container": {"container": "payment-gateway"},
                "by platform": {"platform": "jira"},
                "by decision": {"decision": "denied"},
                "by time range (10% of log)": {"since": mid - span, "until": mid + span},
                "user + platform + decision": {"actor": "jdoe", "platform": "jira", "decision": "denied"}}
    results = {}
    with TestClient(server.app) as c:
        token = c.post("/api/login", json={"username": "priya", "password": "demo"}).json()["token"]
        hdr = {"Authorization": "Bearer " + token}
        for name, body in searches.items():
            r = c.post("/api/compliance/requests", json=body, headers=hdr)
            r.raise_for_status()  # warm-up, also proves the route answers
            stories = len(r.json()["results"])
            ms = []
            for _ in range(args.runs):
                s = time.perf_counter()
                c.post("/api/compliance/requests", json=body, headers=hdr).raise_for_status()
                ms.append((time.perf_counter() - s) * 1000)
            results[name] = {"filters": body, "stories_returned": stories, "runs": args.runs,
                             "p50_ms": pct(ms, 50), "p95_ms": pct(ms, 95), "max_ms": round(max(ms), 2)}

    sha = subprocess.run(["git", "rev-parse", "--short", "HEAD"], cwd=ROOT, capture_output=True, text=True).stdout.strip()
    report = {"metric": "A07", "label": "synthetic", "date_utc": datetime.now(timezone.utc).isoformat(timespec="seconds"),
              "commit": sha, "target": "p95 <= 2000 ms over 100,000 events via compliance API",
              "path": "POST /api/compliance/requests (TestClient, in-process) -> audit_policy.reconstruct -> audit.search",
              "audit_rows": rows, "synthetic_requests": requests, "fill_seconds": round(fill_s, 1),
              "machine": f"{platform.platform()} / {platform.processor() or platform.machine()} / Python {platform.python_version()}",
              "searches": results,
              "worst_p95_ms": max(r["p95_ms"] for r in results.values())}
    report["pass"] = report["worst_p95_ms"] <= 2000 and rows >= 100_000
    Path(args.out + ".json").write_text(json.dumps(report, indent=2) + "\n")

    md = [f"# A07 audit search latency ({report['label']})", "",
          f"- Date (UTC): {report['date_utc']}", f"- Commit: `{sha}`", f"- Machine: {report['machine']}",
          f"- Audit rows: {rows:,} ({requests:,} synthetic requests, filled via `audit.log_many` in {report['fill_seconds']} s)",
          f"- Path: {report['path']}", f"- Target: {report['target']}",
          f"- Result: worst p95 {report['worst_p95_ms']} ms, **{'PASS' if report['pass'] else 'FAIL'}**", "",
          "| Search | Stories returned | Runs | p50 ms | p95 ms | max ms |", "|---|---|---|---|---|---|"]
    md += [f"| {k} | {v['stories_returned']} | {v['runs']} | {v['p50_ms']} | {v['p95_ms']} | {v['max_ms']} |"
           for k, v in results.items()]
    md += ["", "Reproduce: `python scripts/bench_audit_search.py`. Each search returns at most 500 matching rows "
               "(the `audit.search` default limit) grouped into request stories, and is itself audited as `audit_accessed`."]
    Path(args.out + ".md").write_text("\n".join(md) + "\n")
    print(json.dumps({k: report[k] for k in ("audit_rows", "worst_p95_ms", "pass")}))
    return 0 if report["pass"] else 1


if __name__ == "__main__":
    sys.exit(main())
