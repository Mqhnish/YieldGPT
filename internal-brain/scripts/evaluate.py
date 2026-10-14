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


def provider_label(mode: str, base_url: str) -> str:
    """'live' only for a remote model endpoint. A localhost or private-network endpoint (a stand-in
    or mock used to test the plumbing) must never produce a report that reads as live evidence."""
    if mode != "live":
        return "stub"
    import ipaddress
    from urllib.parse import urlparse
    host = (urlparse(base_url).hostname or "").strip("[]").lower()
    if host in ("", "localhost") or host.endswith((".localhost", ".local", ".internal")):
        return "local_endpoint_not_live"
    try:
        ip = ipaddress.ip_address(host)
    except ValueError:
        return "live"
    return "local_endpoint_not_live" if (ip.is_loopback or ip.is_private or ip.is_link_local) else "live"


def markdown(report: dict) -> str:
    summary = report["summary"]
    lines = ["# Company A " + report["provider"] + " evaluation (" + report["variant"] + ")", "", f"Generated: {report['generated_at']}", "",
             *(["**Not live evidence:** the model endpoint was on this machine or a private network (a stand-in "
                "used to test the plumbing).", ""] if report["provider"] == "local_endpoint_not_live" else []),
             "These are measured results on fictional fixtures. The provider mode is recorded above. "
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
    g = report.get('grounding', {})
    lines += ['', f"Grounding decision accuracy: {g.get('passed', 0)}/{g.get('total', 0)}; false accepts: {g.get('false_accepts', 0)}; false rejects: {g.get('false_rejects', 0)}.",
              '', 'Model measurements (each attempt, token counts, configured price estimates) and separate retrieval/authorization/generation phases are in the JSON report. Unknown prices and failed-call usage remain null. Phase timings overlap and must not be added together. Baseline phase metrics are unavailable; its total elapsed time is measured.', '']
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


def run(cases: list[dict], scratch: Path, mode="offline", baseline=False) -> dict:
    # MUST precede app imports: never write to the user's demo/production audit files.
    if mode == "live":
        from app.env import load_env
        load_env()
        os.environ["IB_LLM_REQUIRE_LIVE"] = "1"
    else:
        os.environ["IB_ENV_FILE"] = str(scratch / ".env")
        os.environ["IB_LLM_PROVIDER"] = "stub"
        os.environ["IB_LLM_REQUIRE_LIVE"] = "0"
    os.environ["IB_DATA_DIR"] = str(scratch)
    os.environ["IB_SLACK_CONFIG"] = ""
    # Evaluations use isolated local checkpoints even when production env is present.
    for key in list(os.environ):
        if key.startswith("IB_CHECKPOINT_") or key in {"IB_CONTENT_KEY", "IB_SLACK_TOKEN_KEY"}:
            os.environ.pop(key)
    if baseline:
        import importlib.util
        import app
        for name in ("index", "planner", "grounding", "llm", "brain"):
            path = ROOT / "evaluation" / "baseline_member1" / (name + ".py")
            spec = importlib.util.spec_from_file_location("app." + name, path)
            module = importlib.util.module_from_spec(spec)
            sys.modules["app." + name] = module
            setattr(app, name, module)
            spec.loader.exec_module(module)
    os.environ["IB_AUDIT_DB"] = str(scratch / "audit.db")
    os.environ["IB_ANCHOR_PATH"] = str(scratch / "anchors.jsonl")
    os.environ["IB_SYNC_DB"] = str(scratch / "sync.db")
    from app import audit, grounding, llm
    from app.brain import Brain
    from app.identity import USERS
    from app.sync_state import SqliteSyncStateStore

    if mode == "live" and llm.configuration_problems():
        return {"schema": "internal-brain.evaluation/2", "status": "not_run_missing_credentials",
                "generated_at": datetime.now(timezone.utc).isoformat(), "provider": "live_requested",
                "reasons": llm.configuration_problems(), "cases_requested": len(cases), "cases": []}
    implementation = {name: hashlib.sha256((ROOT / "app" / name).read_bytes()).hexdigest()
                      for name in ("brain.py", "index.py", "evidence.py", "llm.py", "grounding.py", "planner.py")}
    if baseline:
        implementation = {name + ".py": hashlib.sha256((ROOT / "evaluation" / "baseline_member1" / (name + ".py")).read_bytes()).hexdigest()
                          for name in ("brain", "index", "grounding", "llm", "planner")}
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
        measured, phases = [], {}
        result = None
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
            measured = [e['detail'] for e in audit.search(query_id=result['query_id'], event='model_measurement')]
            timing = audit.search(query_id=result['query_id'], event='query_performance')
            phases = timing[0]['detail']['phases_ms'] if timing else {}
            if mode == 'live' and not case['no_answer'] and not case.get('expected_blocked'):
                if not measured or any(m.get('mode') != 'model_selected' for m in measured):
                    failures.append('live model selection was not exercised successfully')
            if case.get('expected_blocked'):
                if not result.get('blocked') or citations:
                    failures.append('expected policy block without citations')
            elif result.get("blocked"):
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
            failures.append(f"exception: {type(error).__name__}")
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
               "measurements": measured, "phases_ms": phases,
               "elapsed_ms": round((time.perf_counter() - began) * 1000, 3)}
        rows.append(row)
        counts = category_counts.setdefault(case["category"], {"passed": 0, "total": 0})
        counts["total"] += 1
        counts["passed"] += int(row["passed"])
    obligations = sum(r["source_obligations"] for r in rows)
    met = sum(r["source_obligations_met"] for r in rows)
    digest = hashlib.sha256(json.dumps(cases, sort_keys=True).encode()).hexdigest()
    return {"schema": "internal-brain.evaluation/2", "status": "completed", "variant": "frozen_member1_lexical" if baseline else "current", "generated_at": datetime.now(timezone.utc).isoformat(),
            "provider": provider_label(mode, llm.LLM_BASE_URL), "corpus": "fictional Company A app/sources/world.py", "case_sha256": digest,
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
    parser.add_argument("--mode", choices=("offline", "live"), default="offline")
    parser.add_argument("--baseline", action="store_true", help="Frozen Member 1 lexical pipeline; offline only")
    parser.add_argument("--json", dest="json_path", help="Write the complete measured report as JSON")
    parser.add_argument("--markdown", help="Write a human-readable report as Markdown")
    parser.add_argument("--category", action="append", help="Run only this category; repeat to combine")
    parser.add_argument("--case", action="append", help="Run only this case id; repeat to combine")
    args = parser.parse_args()
    from evaluation.cases import CASES
    if args.baseline and args.mode == 'live':
        parser.error('baseline must be offline')
    if args.mode == 'live':
        from evaluation.live_cases import LIVE_CASES
        CASES = [*CASES, *LIVE_CASES]
    cases = [c for c in CASES if (not args.category or c["category"] in args.category)
             and (not args.case or c["id"] in args.case)]
    if not cases:
        parser.error("filters selected no cases")
    try:
        with tempfile.TemporaryDirectory(prefix="internal-brain-evaluation-") as tmp:
            report = run(cases, Path(tmp), args.mode, args.baseline)
    except Exception as error:
        print(f"Evaluation setup failed: {type(error).__name__}: {error}", file=sys.stderr)
        return 2
    write_report(args.json_path, json.dumps(report, indent=2) + "\n")
    if report.get('status') != 'completed':
        write_report(args.markdown, '# Live model evaluation: NOT RUN\n\nApproved model credentials are not configured. No offline result counts as live evidence.\n')
        print(json.dumps(report, indent=2))
        return 2
    from evaluation.grounding_cases import evaluate_grounding
    from app import grounding
    report['grounding'] = evaluate_grounding(grounding.enforce)
    report['categories']['grounding'] = {k: report['grounding'][k] for k in ('passed','total')}
    write_report(args.json_path, json.dumps(report, indent=2) + "\n")
    write_report(args.markdown, markdown(report))
    print(json.dumps(report["summary"], indent=2))
    for row in report["cases"]:
        if not row["passed"]:
            print(f"FAIL {row['id']}: {'; '.join(row['failures'])}")
    return 0 if report["summary"]["passed"] == report["summary"]["total"] and report["grounding"]["passed"] == report["grounding"]["total"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
