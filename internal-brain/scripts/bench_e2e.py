#!/usr/bin/env python3
"""P07 to P09, P12, P13: end-to-end latency through app.server:app.

Runs warmed /api/ask requests (in-process TestClient, full ASGI stack including
AuditedDelivery) for the demo personas, then opens one citation preview per answered
question. Phase times come from the audit trail of each request:
  - pipeline phases: the query_performance event (retrieval, authorization/read,
    generation + grounding, release authorization)
  - checkpoint + delivery: response_delivered.ts - request_received.ts - pipeline total
  - audit/release phase (P12): release authorization + checkpoint + delivery
Writes evaluation/reports/member3-e2e-latency.{json,md}.

    python scripts/bench_e2e.py [--requests 120] [--warmup 20]

Label: fixture (demo world, no real company data), stub model. Model latency (P10) is not measured here.
"""
import argparse
import itertools
import json
import os
import platform
import statistics
import subprocess
import sys
import tempfile
import time
from collections import defaultdict
from datetime import datetime, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

# (persona, question): answerable, no-answer, permission-denied and blocked cases across platforms.
QUESTIONS = [
    ("jdoe", "What's the status of the database migration project and were there any blockers raised in Slack last week?"),
    ("jdoe", "What's the payment gateway architecture?"),
    ("jdoe", "Show me all security vulnerabilities"),
    ("ravi", "What was the root cause of the payment outage last quarter, and what follow-up tickets were created?"),
    ("ravi", "What's the latest runbook for the payment-service incident?"),
    ("asha", "Show me the Q3 breach incident report"),
    ("asha", "Show me all security vulnerabilities"),
    ("kim", "vendor payouts API integration notes"),
    ("kim", "Show me the Q3 breach incident report"),
    ("kim", "What's the status of MIG-1 migration epic in Jira?"),
    ("priya", "What's the status of the database migration project?"),
    ("dana", "Show me the unicorn migration to mars report"),
]


def stats(xs):
    xs = [x for x in xs if x is not None]
    if len(xs) < 2:
        return {"n": len(xs)}
    q = statistics.quantiles(xs, n=100, method="inclusive")
    return {"n": len(xs), "p50_ms": round(q[49], 1), "p95_ms": round(q[94], 1), "max_ms": round(max(xs), 1)}


def git_sha():
    return subprocess.run(["git", "rev-parse", "--short", "HEAD"], cwd=ROOT, capture_output=True, text=True).stdout.strip()


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument("--requests", type=int, default=120)
    ap.add_argument("--warmup", type=int, default=20)
    ap.add_argument("--out", default=str(ROOT / "evaluation" / "reports" / "member3-e2e-latency"))
    args = ap.parse_args()

    tmp = tempfile.mkdtemp(prefix="ib-e2e-")
    os.environ.update(IB_DATA_DIR=tmp, IB_AUDIT_DB=f"{tmp}/audit.db", IB_ANCHOR_PATH=f"{tmp}/anchors.jsonl",
                      IB_ENV_FILE=f"{tmp}/.env", IB_LLM_PROVIDER="stub")
    from fastapi.testclient import TestClient
    from app import audit, checkpoints, server

    asks, previews = [], []
    with TestClient(server.app) as c:
        tokens = {u: c.post("/api/login", json={"username": u, "password": "demo"}).json()["token"]
                  for u in {p for p, _ in QUESTIONS}}
        for i, (user, q) in enumerate(itertools.islice(itertools.cycle(QUESTIONS), args.warmup + args.requests)):
            hdr = {"Authorization": "Bearer " + tokens[user]}
            s = time.perf_counter()
            r = c.post("/api/ask", json={"question": q}, headers=hdr)
            client_ms = (time.perf_counter() - s) * 1000
            if i < args.warmup:
                continue
            r.raise_for_status()
            body = r.json()
            asks.append({"user": user, "status": body.get("status"), "rid": r.headers["x-request-id"],
                         "client_ms": client_ms, "platforms": sorted({x["platform"] for x in body["citations"]})})
            if body["citations"]:
                s = time.perf_counter()
                e = c.get(f"/api/evidence/{body['query_id']}/{body['citations'][0]['ref']}", headers=hdr)
                previews.append({"status": e.status_code, "client_ms": (time.perf_counter() - s) * 1000})

    for a in asks:
        ev = {e["event"]: e for e in audit.search(request_id=a["rid"], limit=10_000)}
        perf = ev["query_performance"]["detail"]["phases_ms"]
        server_ms = (ev["response_delivered"]["ts"] - ev["request_received"]["ts"]) * 1000
        a.update(perf, server_ms=server_ms, checkpoint_and_delivery_ms=server_ms - perf["total_ms"])
        a["audit_release_ms"] = a.get("release_authorization_ms", 0) + a["checkpoint_and_delivery_ms"]

    col = lambda k, rows=asks: stats([a.get(k) for a in rows])  # noqa: E731
    by_status = defaultdict(list)
    for a in asks:
        by_status[a["status"]].append(a)
    by_mix = defaultdict(list)
    for a in asks:
        by_mix["+".join(a["platforms"]) or "none"].append(a)
    report = {
        "metrics": "P07 P08 P09 P12 P13", "label": "fixture, stub model",
        "date_utc": datetime.now(timezone.utc).isoformat(timespec="seconds"), "commit": git_sha(),
        "machine": f"{platform.platform()} / {platform.machine()} / Python {platform.python_version()}",
        "path": "TestClient(app.server:app), in-process ASGI with AuditedDelivery",
        "checkpoint_store": checkpoints.from_env(audit.ANCHOR_PATH).kind,
        "warmup": args.warmup, "measured_requests": len(asks), "citation_previews": len(previews),
        "P07_P08_end_to_end_client": col("client_ms"),
        "end_to_end_by_status": {k: col("client_ms", v) for k, v in sorted(by_status.items())},
        "end_to_end_by_source_mix": {k: col("client_ms", v) for k, v in sorted(by_mix.items())},
        "phases": {k: col(k) for k in ("retrieval_ms", "authorization_and_read_ms", "generation_and_grounding_ms",
                                       "release_authorization_ms", "checkpoint_and_delivery_ms", "total_ms")},
        "P09_authorization_and_read": col("authorization_and_read_ms"),
        "P12_audit_release": col("audit_release_ms"),
        "P13_citation_preview": stats([p["client_ms"] for p in previews]),
        "preview_status_codes": sorted({p["status"] for p in previews}),
    }
    targets = {"P07_P08_end_to_end_client": [("p50_ms", 4000), ("p95_ms", 8000)],
               "P09_authorization_and_read": [("p95_ms", 2000)], "P12_audit_release": [("p95_ms", 500)],
               "P13_citation_preview": [("p95_ms", 2000)]}
    report["pass"] = {k: all(report[k].get(f, 1e9) <= lim for f, lim in v) for k, v in targets.items()}
    Path(args.out + ".json").write_text(json.dumps(report, indent=2) + "\n")

    def row(name, s, target=""):
        return f"| {name} | {s.get('n')} | {s.get('p50_ms', '-')} | {s.get('p95_ms', '-')} | {s.get('max_ms', '-')} | {target} |"
    hdr = ["| Measure | n | p50 ms | p95 ms | max ms | Target |", "|---|---|---|---|---|---|"]
    md = [f"# End-to-end latency ({report['label']})", "",
          f"- Date (UTC): {report['date_utc']}", f"- Commit: `{report['commit']}`", f"- Machine: {report['machine']}",
          f"- Path: {report['path']}", f"- Checkpoint store: `{report['checkpoint_store']}`",
          f"- Requests: {args.warmup} warm-up (discarded) + {len(asks)} measured, {len(QUESTIONS)} persona/question pairs "
          f"cycled; {len(previews)} citation previews", "",
          "## Headline", "", *hdr,
          row("P07/P08 end to end (client)", report["P07_P08_end_to_end_client"], "p50 <= 4000, p95 <= 8000"),
          row("P09 authorization + read", report["P09_authorization_and_read"], "p95 <= 2000"),
          row("P12 audit/release (release authz + checkpoint + delivery)", report["P12_audit_release"], "p95 <= 500"),
          row("P13 citation preview (client)", report["P13_citation_preview"], "p95 <= 2000"), "",
          "Pass: " + ", ".join(f"{k.split('_')[0]} {'PASS' if v else 'FAIL'}" for k, v in report["pass"].items()), "",
          "## Pipeline phases (query_performance audit events)", "", *hdr,
          *[row(k, v) for k, v in report["phases"].items()], "",
          "## End to end by outcome", "", *hdr, *[row(k, v) for k, v in report["end_to_end_by_status"].items()], "",
          "## End to end by cited source mix", "", *hdr,
          *[row(k, v) for k, v in report["end_to_end_by_source_mix"].items()], "",
          "Stub model, so generation time is near zero; real-model latency (P10) is measured separately by Member 2. "
          "Reproduce: `python scripts/bench_e2e.py`."]
    Path(args.out + ".md").write_text("\n".join(md) + "\n")
    print(json.dumps(report["pass"]))
    return 0 if all(report["pass"].values()) else 1


if __name__ == "__main__":
    sys.exit(main())
