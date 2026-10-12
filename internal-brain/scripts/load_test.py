#!/usr/bin/env python3
"""P14 / P15: concurrent demo load against a local uvicorn running app.server:app.

--users threads (personas assigned round robin) loop for --seconds over real HTTP:
ask a random question; after an answer, sometimes open their own citation preview, and
sometimes try another user's citation preview (must be 404: no cross-user cache hits).
After the run the server is stopped and every result is checked:
  - permission leaks: every citation re-checked with that connector's check() for the
    asking persona, and the server's audit must hold live + release "allowed" decisions for it
  - audit gaps: every 200 answer has answer_returned (release record) and response_delivered
    rows, a checkpoint at or past its release row, and the whole chain verifies
  - cross-user cache: other users' evidence must never return 200; query ids never repeat
Writes evaluation/reports/member3-load-test.{json,md}. Checkpoint store comes from the
IB_CHECKPOINT_* env (local file if unset).

    python scripts/load_test.py [--users 25] [--seconds 300]

Label: fixture (demo world), stub model.
"""
import argparse
import json
import os
import platform
import random
import socket
import subprocess
import sys
import tempfile
import threading
import time
from collections import Counter
from datetime import datetime, timezone
from pathlib import Path

import httpx

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(ROOT / "scripts"))
from bench_e2e import QUESTIONS, git_sha, stats  # noqa: E402

PERSONAS = ["jdoe", "ravi", "asha", "kim", "priya", "dana"]


def free_port():
    with socket.socket() as s:
        s.bind(("127.0.0.1", 0))
        return s.getsockname()[1]


def worker(base, token, user, deadline, results, shared, lock, rng):
    hdr = {"Authorization": "Bearer " + token}
    with httpx.Client(base_url=base, headers=hdr, timeout=30) as c:
        while time.time() < deadline:
            q = rng.choice(QUESTIONS)[1]
            s = time.perf_counter()
            try:
                r = c.post("/api/ask", json={"question": q})
                body = r.json() if r.status_code == 200 else {}
            except Exception as e:  # noqa: BLE001
                results.append({"kind": "ask", "user": user, "status": type(e).__name__, "ms": None})
                continue
            rec = {"kind": "ask", "user": user, "status": r.status_code, "ms": (time.perf_counter() - s) * 1000,
                   "rid": r.headers.get("x-request-id"), "qid": body.get("query_id"),
                   "citations": [{"uid": x["uid"], "platform": x["platform"], "ref": x["ref"]}
                                 for x in body.get("citations", [])]}
            results.append(rec)
            if not rec["citations"]:
                continue
            with lock:
                shared.append((user, rec["qid"], rec["citations"][0]["ref"]))
                others = [x for x in shared[-200:] if x[0] != user]
            if rng.random() < 0.3:
                s = time.perf_counter()
                e = c.get(f"/api/evidence/{rec['qid']}/{rec['citations'][0]['ref']}")
                results.append({"kind": "own_evidence", "user": user, "status": e.status_code,
                                "ms": (time.perf_counter() - s) * 1000})
            if others and rng.random() < 0.2:
                owner, qid, ref = rng.choice(others)
                e = c.get(f"/api/evidence/{qid}/{ref}")
                results.append({"kind": "cross_user_evidence", "user": user, "owner": owner, "status": e.status_code})


def check(asks, db, cp_env):
    """Runs after the server stopped, against the server's own audit DB and checkpoint store.
    One SQL pass over plaintext columns (stage is unsealed); nothing is decrypted."""
    os.environ["IB_AUDIT_DB"] = db
    os.environ.update(cp_env)
    import sqlite3
    from app import audit
    from app.identity import USERS
    from app.sources.registry import build_connectors
    from app.sources.world import World

    released, delivered, stages = {}, set(), {}
    with sqlite3.connect(db) as c:
        for rid_, actor, event, qid, req, uid, dec, stage in c.execute(
                "SELECT id, actor, event, query_id, request_id, doc_uid, decision, json_extract(detail, '$.stage') "
                "FROM audit_log WHERE event IN ('answer_returned', 'response_delivered', 'authz_decision')"):
            if event == "answer_returned":
                released.setdefault(qid, (rid_, actor))
            elif event == "response_delivered":
                delivered.add(req)
            else:
                stages.setdefault((qid, uid), set()).add((stage, dec))
    anchors = audit._store().checkpoints()
    top_anchor = max((int(a["row_id"]) for a in anchors), default=0)
    connectors, checked, leaks, gaps = build_connectors(World()), {}, [], []
    for a in (x for x in asks if x["status"] == 200):
        rel = released.get(a["qid"])
        if not rel or a["rid"] not in delivered or rel[1] != a["user"]:
            gaps.append({"qid": a["qid"], "problem": "missing release or delivery record"})
        elif rel[0] > top_anchor:
            gaps.append({"qid": a["qid"], "problem": "release row not covered by a checkpoint"})
        for cit in a["citations"]:
            key = (a["user"], cit["uid"])
            if key not in checked:  # world is static during the run, so one check per (user, doc)
                native = cit["uid"].split(":", 1)[1]
                checked[key] = connectors[cit["platform"]].check(USERS[a["user"]], native).allowed
            if not checked[key]:
                leaks.append({"user": a["user"], "uid": cit["uid"], "by": "connector.check"})
            st = stages.get((a["qid"], cit["uid"]), set())
            if ("live", "allowed") not in st or ("release", "allowed") not in st or ("release", "denied") in st:
                leaks.append({"user": a["user"], "uid": cit["uid"], "by": "audit decisions", "stages": sorted(map(str, st))})
    return leaks, gaps, audit.verify_report(), len(anchors)


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument("--users", type=int, default=25)
    ap.add_argument("--seconds", type=int, default=300)
    ap.add_argument("--out", default=str(ROOT / "evaluation" / "reports" / "member3-load-test"))
    args = ap.parse_args()

    tmp = tempfile.mkdtemp(prefix="ib-load-")
    db = f"{tmp}/audit.db"
    cp_env = {k: v for k, v in os.environ.items() if k.startswith("IB_CHECKPOINT_")}
    env = {**os.environ, "IB_DATA_DIR": tmp, "IB_AUDIT_DB": db, "IB_ANCHOR_PATH": f"{tmp}/anchors.jsonl",
           "IB_ENV_FILE": f"{tmp}/.env", "IB_LLM_PROVIDER": "stub"}
    os.environ.update({k: env[k] for k in ("IB_DATA_DIR", "IB_ANCHOR_PATH", "IB_ENV_FILE", "IB_LLM_PROVIDER")})
    port = free_port()
    base = f"http://127.0.0.1:{port}"
    server = subprocess.Popen([sys.executable, "-m", "uvicorn", "app.server:app", "--port", str(port),
                               "--log-level", "warning"], cwd=ROOT, env=env)
    try:
        for _ in range(100):
            try:
                if httpx.get(base + "/api/health", timeout=1).status_code == 200:
                    break
            except httpx.HTTPError:
                pass
            time.sleep(0.2)
        tokens = {u: httpx.post(base + "/api/login", json={"username": u, "password": "demo"}).json()["token"]
                  for u in PERSONAS}
        results, shared, lock = [], [], threading.Lock()
        started = time.time()
        deadline = started + args.seconds
        threads = [threading.Thread(target=worker, args=(base, tokens[PERSONAS[i % len(PERSONAS)]],
                                                         PERSONAS[i % len(PERSONAS)], deadline, results, shared,
                                                         lock, random.Random(i)))
                   for i in range(args.users)]
        for t in threads:
            t.start()
        for t in threads:
            t.join()
        duration = time.time() - started
    finally:
        server.terminate()
        server.wait(timeout=30)

    asks = [r for r in results if r["kind"] == "ask"]
    own = [r for r in results if r["kind"] == "own_evidence"]
    cross = [r for r in results if r["kind"] == "cross_user_evidence"]
    ok = [a for a in asks if a["status"] == 200]
    leaks, gaps, verify, n_anchors = check(asks, db, cp_env)
    qids = [a["qid"] for a in ok]
    report = {
        "metrics": "P14 P15", "label": "fixture, stub model",
        "date_utc": datetime.now(timezone.utc).isoformat(timespec="seconds"), "commit": git_sha(),
        "machine": f"{platform.platform()} / {platform.machine()} / {os.cpu_count()} CPUs / Python {platform.python_version()}",
        "server": "uvicorn app.server:app, 1 process, 127.0.0.1 (real HTTP)",
        "checkpoint_store": verify["checkpoint_store"], "users": args.users, "personas": PERSONAS,
        "duration_s": round(duration, 1),
        "requests": {"ask": len(asks), "own_evidence": len(own), "cross_user_evidence": len(cross)},
        "ask_status_codes": dict(Counter(str(a["status"]) for a in asks)),
        "ask_success_rate": round(len(ok) / len(asks), 5) if asks else 0,
        "own_evidence_success_rate": round(sum(r["status"] == 200 for r in own) / len(own), 5) if own else None,
        "completed_answers_per_s": round(len(ok) / duration, 2),
        "answers_with_citations_per_s": round(sum(bool(a["citations"]) for a in ok) / duration, 2),
        "ask_latency": stats([a["ms"] for a in ok]),
        "permission_leaks": len(leaks), "leak_examples": leaks[:5],
        "audit_gaps": len(gaps), "gap_examples": gaps[:5],
        "cross_user_cache_hits": sum(r["status"] == 200 for r in cross),
        "duplicate_query_ids": len(qids) - len(set(qids)),
        "checkpoints_written": n_anchors,
        "audit_verify": {k: verify[k] for k in ("status", "rows", "verified_through", "uncheckpointed_rows",
                                                 "assurance", "problem")},
    }
    report["pass"] = {
        "P14 success >= 99%": report["ask_success_rate"] >= 0.99,
        "P14 zero leaks": report["permission_leaks"] == 0,
        "P14 zero audit gaps": report["audit_gaps"] == 0 and verify["status"] == "verified",
        "P14 zero cross-user cache hits": report["cross_user_cache_hits"] == 0 and report["duplicate_query_ids"] == 0,
        "P15 >= 5 answers/s": report["completed_answers_per_s"] >= 5,
    }
    Path(args.out + ".json").write_text(json.dumps(report, indent=2) + "\n")
    lat = report["ask_latency"]
    md = [f"# Load test, {args.users} users for {args.seconds} s ({report['label']})", "",
          f"- Date (UTC): {report['date_utc']}", f"- Commit: `{report['commit']}`", f"- Machine: {report['machine']}",
          f"- Server: {report['server']}", f"- Checkpoint store: `{report['checkpoint_store']}`",
          f"- Personas (round robin over threads): {', '.join(PERSONAS)}; questions drawn at random from "
          f"{len(QUESTIONS)} (answered, no-answer and denied cases)", "",
          "| Measure | Result |", "|---|---|",
          f"| Duration | {report['duration_s']} s |",
          f"| Ask requests | {len(asks)} (status codes {report['ask_status_codes']}) |",
          f"| Ask success rate | {report['ask_success_rate']:.2%} |",
          f"| Completed answers / s (P15) | {report['completed_answers_per_s']} |",
          f"| Answers with citations / s | {report['answers_with_citations_per_s']} |",
          f"| Ask latency under load p50 / p95 / max ms | {lat.get('p50_ms')} / {lat.get('p95_ms')} / {lat.get('max_ms')} |",
          f"| Own citation previews | {len(own)}, success {report['own_evidence_success_rate']:.2%} |",
          f"| Permission leaks (connector check() + audit decisions per citation) | {report['permission_leaks']} |",
          f"| Audit gaps (release + delivery record + checkpoint per answer) | {report['audit_gaps']} |",
          f"| Cross-user evidence attempts / hits | {len(cross)} / {report['cross_user_cache_hits']} |",
          f"| Duplicate query ids | {report['duplicate_query_ids']} |",
          f"| Checkpoints written | {n_anchors} |",
          f"| Audit chain after run | {verify['status']}, {verify['rows']} rows, assurance {verify['assurance']} |", "",
          "Pass: " + ", ".join(f"{k} {'PASS' if v else 'FAIL'}" for k, v in report["pass"].items()), "",
          "Reproduce: `python scripts/load_test.py` (set IB_CHECKPOINT_* to use the MinIO store)."]
    Path(args.out + ".md").write_text("\n".join(md) + "\n")
    print(json.dumps(report["pass"]))
    return 0 if all(report["pass"].values()) else 1


if __name__ == "__main__":
    sys.exit(main())
