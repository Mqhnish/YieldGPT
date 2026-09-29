#!/usr/bin/env python3
"""Run reproducible offline evidence-quality checks, with isolated persistence.

Usage: python scripts/evaluate.py --json reports/evaluation.json --markdown reports/evaluation.md
Returns 1 if any assertion fails, 2 for setup failure, and 0 only when all pass.
"""
from __future__ import annotations

import argparse
from datetime import datetime, timezone
import hashlib
import json
import os
from pathlib import Path
import sys
import tempfile
import time

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))


def write_report(path: str | None, text: str) -> None:
    if path:
        target = Path(path)
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_text(text, encoding="utf-8")


def markdown(report: dict) -> str:
    summary = report["summary"]
    lines = ["# Company A offline evaluation", "", f"Generated: {report['generated_at']}", "",
             "These are measured results on fictional fixtures with the offline extractive provider. "
             "They do not establish production authorization, semantic entailment, or live-model quality.", "",
             f"- Cases passed: **{summary['passed']}/{summary['total']}**",
             f"- Required citation obligations met: **{summary['source_obligations_met']}/{summary['source_obligations']}** "
             f"({summary['source_recall']:.1%})",
             f"- Unauthorized citations: **{summary['unauthorized_citations']}**",
             f"- Unauthorized model-context sources: **{summary['unauthorized_context_sources']}**",
             f"- Forbidden citations (including time exclusions/poisoned content): **{summary['forbidden_citations']}**",
             f"- Forbidden model-context sources: **{summary['forbidden_context_sources']}**",
             f"- No-answer cases correct: **{summary['no_answer_correct']}/{summary['no_answer_cases']}**",
             "", "| Category | Passed | Total |", "|---|---:|---:|"]
    for category, counts in sorted(report["categories"].items()):
        lines.append(f"| {category} | {counts['passed']} | {counts['total']} |")
    lines += ["", "## Individual results", "", "| Case | Result | Failure details |", "|---|---|---|"]
    for row in report["cases"]:
        failure = "; ".join(row["failures"]).replace("|", "\\|").replace("\n", " ")
        lines.append(f"| {row['id']} | {'PASS' if row['passed'] else 'FAIL'} | {failure or '—'} |")
    lines += ["", "## Measurement limits", "",
              "Source recall counts one obligation per `expected_all` source and one obligation for an "
              "`expected_any` group. Extra citations are not automatically incorrect, so this is not citation "
              "precision. All citations and assembled context are independently checked against the current "
              "connector permissions. Phrase checks cover specific fixture facts; they are not a general factuality judge. "
              "Static evaluation complements the separate revocation, fail-closed, grounding, and contract tests.", ""]
    return "\n".join(lines)


def run(cases: list[dict], scratch: Path) -> dict:
    # MUST precede app imports: never write to the user's demo/production audit files.
    os.environ["IB_LLM_PROVIDER"] = "stub"
    os.environ["IB_AUDIT_DB"] = str(scratch / "audit.db")
    os.environ["IB_ANCHOR_PATH"] = str(scratch / "anchors.jsonl")
    os.environ["IB_SYNC_DB"] = str(scratch / "sync.db")
    from app import audit, grounding
    from app.brain import Brain
    from app.identity import USERS
    from app.sync_state import SqliteSyncStateStore

    implementation = {name: hashlib.sha256((ROOT / "app" / name).read_bytes()).hexdigest()
                      for name in ("brain.py", "index.py", "evidence.py", "llm.py", "grounding.py", "planner.py")}
    audit.init()
    brain = Brain(sync_store=SqliteSyncStateStore(scratch / "sync.db"))
    rows = []
    category_counts = {}
    started = time.perf_counter()
    for case in cases:
        began = time.perf_counter()
        failures = []
        citations: set[str] = set()
        unauthorized = []
        unauthorized_context = []
        answer = ""
        context_ids: set[str] = set()
        try:
            user = USERS[case["user"]]
            result = brain.ask(user, case["question"])
            answer = result["answer"]
            citations = {c["uid"] for c in result["citations"]}
            for uid in sorted(citations):
                platform, native_id = uid.split(":", 1)
                if platform not in brain.connectors or not brain.connectors[platform].check(user, native_id).allowed:
                    unauthorized.append(uid)
            events = audit.search(query_id=result["query_id"], event="context_assembled")
            for event in events:
                for item in event["detail"].get("context", []):
                    uid = item["uid"] if isinstance(item, dict) else item
                    context_ids.add(uid)
                    platform, native_id = uid.split(":", 1)
                    if platform not in brain.connectors or not brain.connectors[platform].check(user, native_id).allowed:
                        unauthorized_context.append(uid)
            if unauthorized:
                failures.append("unauthorized citations: " + ", ".join(unauthorized))
            if unauthorized_context:
                failures.append("unauthorized model context: " + ", ".join(sorted(set(unauthorized_context))))
            if result.get("blocked"):
                failures.append("ordinary fixture question unexpectedly blocked")
            for uid in case["expected_all"]:
                if uid not in citations:
                    failures.append(f"missing citation {uid}")
            if case["expected_any"] and not citations.intersection(case["expected_any"]):
                failures.append("missing any of " + ", ".join(case["expected_any"]))
            for uid in sorted(citations.intersection(case["forbidden"])):
                failures.append(f"forbidden citation {uid}")
            for uid in sorted(context_ids.intersection(case["forbidden"])):
                failures.append(f"forbidden model context {uid}")
            if case["no_answer"]:
                if answer != grounding.NEUTRAL_NO_ANSWER or citations:
                    failures.append("expected neutral no-answer with no citations")
            elif answer == grounding.NEUTRAL_NO_ANSWER:
                failures.append("unexpected abstention")
            for group in case["answer_contains"]:
                if not any(phrase.casefold() in answer.casefold() for phrase in group):
                    failures.append("missing fact: " + " / ".join(group))
            for phrase in case["answer_absent"]:
                if phrase.casefold() in answer.casefold():
                    failures.append(f"forbidden answer phrase: {phrase}")
        except Exception as error:  # isolate the failure, report the remaining cases
            failures.append(f"exception: {type(error).__name__}: {error}")
        obligations = len(case["expected_all"]) + bool(case["expected_any"])
        satisfied = len(citations.intersection(case["expected_all"])) + bool(citations.intersection(case["expected_any"]))
        row = {"id": case["id"], "category": case["category"], "user": case["user"],
               "question": case["question"], "passed": not failures, "failures": failures,
               "citations": sorted(citations), "context_sources": sorted(context_ids), "answer": answer,
               "source_obligations": obligations, "source_obligations_met": satisfied,
               "unauthorized_citations": unauthorized, "unauthorized_context_sources": sorted(set(unauthorized_context)),
               "forbidden_citations": sorted(citations.intersection(case["forbidden"])),
               "forbidden_context_sources": sorted(context_ids.intersection(case["forbidden"])),
               "no_answer_expected": case["no_answer"],
               "no_answer_correct": bool(case["no_answer"] and answer == grounding.NEUTRAL_NO_ANSWER and not citations),
               "elapsed_ms": round((time.perf_counter() - began) * 1000, 3)}
        rows.append(row)
        counts = category_counts.setdefault(case["category"], {"passed": 0, "total": 0})
        counts["total"] += 1
        counts["passed"] += int(row["passed"])
    obligations = sum(r["source_obligations"] for r in rows)
    met = sum(r["source_obligations_met"] for r in rows)
    digest = hashlib.sha256(json.dumps(cases, sort_keys=True).encode()).hexdigest()
    return {"schema": "internal-brain.evaluation/1", "generated_at": datetime.now(timezone.utc).isoformat(),
            "provider": "stub", "corpus": "fictional Company A app/sources/world.py", "case_sha256": digest,
            "implementation_sha256_at_start": implementation,
            "summary": {"total": len(rows), "passed": sum(r["passed"] for r in rows),
                        "source_obligations": obligations, "source_obligations_met": met,
                        "source_recall": met / obligations if obligations else 1.0,
                        "unauthorized_citations": sum(len(r["unauthorized_citations"]) for r in rows),
                        "unauthorized_context_sources": sum(len(r["unauthorized_context_sources"]) for r in rows),
                        "forbidden_citations": sum(len(r["forbidden_citations"]) for r in rows),
                        "forbidden_context_sources": sum(len(r["forbidden_context_sources"]) for r in rows),
                        "no_answer_cases": sum(r["no_answer_expected"] for r in rows),
                        "no_answer_correct": sum(r["no_answer_correct"] for r in rows),
                        "elapsed_seconds": round(time.perf_counter() - started, 3)},
            "categories": category_counts, "cases": rows}


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--json", dest="json_path", help="Write the complete measured report as JSON")
    parser.add_argument("--markdown", help="Write a human-readable report as Markdown")
    parser.add_argument("--category", action="append", help="Run only this category; repeat to combine")
    parser.add_argument("--case", action="append", help="Run only this case id; repeat to combine")
    args = parser.parse_args()
    from evaluation.cases import CASES
    cases = [c for c in CASES if (not args.category or c["category"] in args.category)
             and (not args.case or c["id"] in args.case)]
    if not cases:
        parser.error("filters selected no cases")
    try:
        with tempfile.TemporaryDirectory(prefix="internal-brain-evaluation-") as tmp:
            report = run(cases, Path(tmp))
    except Exception as error:
        print(f"Evaluation setup failed: {type(error).__name__}: {error}", file=sys.stderr)
        return 2
    write_report(args.json_path, json.dumps(report, indent=2) + "\n")
    write_report(args.markdown, markdown(report))
    print(json.dumps(report["summary"], indent=2))
    for row in report["cases"]:
        if not row["passed"]:
            print(f"FAIL {row['id']}: {'; '.join(row['failures'])}")
    return 0 if report["summary"]["passed"] == report["summary"]["total"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
