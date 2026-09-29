#!/usr/bin/env python3
"""Measure local index search on a deterministic synthetic Company A estate.

This is NOT an end-to-end latency or SaaS-permission benchmark. Run --size small
for a smoke check and --size full for the 19,700-object retrieval workload.
"""
from __future__ import annotations

import argparse
from collections import Counter
from datetime import datetime, timezone
import hashlib
import json
import math
import os
from pathlib import Path
import platform
import sys
import tempfile
import time

try:
    import resource
except ImportError:  # Windows: retrieval timing still works; RSS is unavailable.
    resource = None

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))


def percentile(values: list[float], probability: float) -> float:
    return sorted(values)[max(0, math.ceil(probability * len(values)) - 1)]


def run(size: str, rounds: int, top_k: int, scratch: Path) -> dict:
    os.environ["IB_LLM_PROVIDER"] = "stub"
    os.environ["IB_AUDIT_DB"] = str(scratch / "audit.db")
    os.environ["IB_ANCHOR_PATH"] = str(scratch / "anchors.jsonl")
    os.environ["IB_SYNC_DB"] = str(scratch / "sync.db")
    from app.index import Index
    from evaluation.synthetic import PLATFORMS, PRINCIPALS, make_corpus, queries

    implementation = hashlib.sha256((ROOT / "app" / "index.py").read_bytes()).hexdigest()
    index = Index()
    counts = Counter()
    containers = {p: set() for p in PLATFORMS}
    tenants = {p: set() for p in PLATFORMS}
    words, eligible = 0, 0
    digest = hashlib.sha256()
    started = time.perf_counter()
    for doc, hint in make_corpus(size):
        index.upsert(doc, hint)
        counts[doc.platform] += 1
        containers[doc.platform].add(doc.container)
        tenants[doc.platform].add(doc.tenant)
        eligible += bool(hint & PRINCIPALS)
        words += len(doc.text.split())
        digest.update(json.dumps([doc.uid, doc.title, doc.text, sorted(hint)], separators=(",", ":")).encode())
    build_seconds = time.perf_counter() - started
    questions = queries()

    def retrieve(question: str):
        # This simple hint predicate is explicitly NOT a live authorization gate.
        return [entry.doc.uid for _, entry in index.search(question, PLATFORMS)
                if entry.acl_hint & PRINCIPALS][:top_k]

    for q in questions:
        retrieve(q["question"])
    timings = []
    outcomes = []
    for repeat in range(rounds):
        for q in questions:
            began = time.perf_counter()
            found = retrieve(q["question"])
            elapsed = (time.perf_counter() - began) * 1000
            timings.append(elapsed)
            if repeat == 0:
                outcomes.append({**q, "passed": q["expected_uid"] in found, "top_uids": found})
    peak_mib = None
    if resource is not None:
        rss = resource.getrusage(resource.RUSAGE_SELF).ru_maxrss
        # macOS reports bytes; Linux reports kibibytes.
        peak_mib = round(rss / (1024 * 1024 if sys.platform == "darwin" else 1024), 1)
    return {"schema": "internal-brain.retrieval-benchmark/1", "generated_at": datetime.now(timezone.utc).isoformat(),
            "mode": "synthetic local index only; no model, connector, live gate or audit cost",
            "size": size, "seed": 20260928, "corpus_sha256": digest.hexdigest(),
            "index_sha256_at_start": implementation,
            "environment": {"python": platform.python_version(), "system": platform.system(), "machine": platform.machine()},
            "corpus": {"objects": sum(counts.values()), "by_platform": dict(counts),
                       "containers": {p: len(c) for p, c in containers.items()},
                       "tenants": {p: len(t) for p, t in tenants.items()},
                       "eligible_by_synthetic_hint": eligible, "mean_words": round(words / sum(counts.values()), 1)},
            "measurements": {"build_seconds": round(build_seconds, 3), "search_samples": len(timings),
                             "search_p50_ms": round(percentile(timings, .50), 3),
                             "search_p95_ms": round(percentile(timings, .95), 3),
                             "search_max_ms": round(max(timings), 3), "process_peak_rss_mib": peak_mib},
            "quality": {"queries": len(outcomes), "passed": sum(o["passed"] for o in outcomes), "top_k": top_k,
                        "recall_at_k": sum(o["passed"] for o in outcomes) / len(outcomes)},
            "queries": outcomes}


def markdown(report: dict) -> str:
    corpus, measurements, quality = report["corpus"], report["measurements"], report["quality"]
    memory = (f"{measurements['process_peak_rss_mib']} MiB" if measurements["process_peak_rss_mib"] is not None
              else "unavailable on this platform")
    return "\n".join([
        "# Synthetic retrieval benchmark", "", f"Generated: {report['generated_at']}", "",
        "This measures local retrieval on generated documents. It excludes authorization checks, API calls, "
        "answer generation, audit persistence, ingestion networking and concurrency. Do not present it as production latency.", "",
        f"- Size: **{corpus['objects']:,} source objects** ({report['size']})",
        f"- Corpus SHA-256: `{report['corpus_sha256']}`",
        f"- Mean document length: {corpus['mean_words']} words",
        f"- Build time: {measurements['build_seconds']} seconds",
        f"- Search p50 / p95: {measurements['search_p50_ms']} / {measurements['search_p95_ms']} ms "
        f"over {measurements['search_samples']} warmed samples",
        f"- Process peak resident memory: {memory} (whole process, not index-only)",
        f"- Expected document found in top {quality['top_k']}: {quality['passed']}/{quality['queries']}", "",
        "| Platform | Objects | Containers | Tenants |", "|---|---:|---:|---:|",
        *[f"| {p} | {n:,} | {corpus['containers'][p]} | {corpus['tenants'][p]} |" for p, n in corpus["by_platform"].items()], "",
        "The corpus contains repeated operational topics, variable sentence lengths, parent references, hierarchical "
        "Drive container tags, multiple Slack workspaces, and varied ACL hints. These hints are workload metadata; "
        "they do not exercise native Confluence/Jira/Slack/Drive access rules. Eight hand-written target documents "
        "measure retrieval sanity, not a representative production relevance distribution.", "",
        "| Query | Expected source found |", "|---|---|",
        *[f"| {q['question']} | {'PASS' if q['passed'] else 'FAIL'} |" for q in report["queries"]], "",
    ])


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--size", choices=["small", "full"], default="full")
    parser.add_argument("--rounds", type=int, default=5)
    parser.add_argument("--top-k", type=int, default=10)
    parser.add_argument("--json", dest="json_path")
    parser.add_argument("--markdown")
    args = parser.parse_args()
    if args.rounds < 1 or args.top_k < 1:
        parser.error("--rounds and --top-k must be positive")
    with tempfile.TemporaryDirectory(prefix="internal-brain-benchmark-") as tmp:
        report = run(args.size, args.rounds, args.top_k, Path(tmp))
    for destination, contents in ((args.json_path, json.dumps(report, indent=2) + "\n"),
                                  (args.markdown, markdown(report))):
        if destination:
            path = Path(destination)
            path.parent.mkdir(parents=True, exist_ok=True)
            path.write_text(contents, encoding="utf-8")
    print(json.dumps({k: report[k] for k in ("corpus", "measurements", "quality")}, indent=2))
    return 0 if report["quality"]["passed"] == report["quality"]["queries"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
