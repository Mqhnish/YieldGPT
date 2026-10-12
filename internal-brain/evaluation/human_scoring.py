"""Validate and summarize independent human scores for the frozen trial set."""
from __future__ import annotations

from collections import defaultdict
import csv
import json
from pathlib import Path

METRICS = ("correctness", "completeness", "grounded", "safe")
SLICE_FIELDS = ("persona", "case_type", "source_scope")


class HumanScoringError(ValueError):
    pass


def load_scores(path: Path) -> list[dict]:
    with path.open(encoding="utf-8", newline="") as stream:
        return list(csv.DictReader(stream))


def _binary(value: str, case_id: str, reviewer: str, metric: str) -> int:
    if value not in {"0", "1"}:
        raise HumanScoringError(
            f"{case_id} {reviewer} has invalid {metric}; expected 0 or 1"
        )
    return int(value)


def _kappa(pairs: list[tuple[int, int]]) -> float | None:
    if not pairs:
        return None
    observed = sum(left == right for left, right in pairs) / len(pairs)
    left_yes = sum(left for left, _ in pairs) / len(pairs)
    right_yes = sum(right for _, right in pairs) / len(pairs)
    expected = left_yes * right_yes + (1 - left_yes) * (1 - right_yes)
    if expected == 1:
        return 1.0 if observed == 1 else None
    return round((observed - expected) / (1 - expected), 4)


def _metric_summary(rows: list[dict]) -> dict:
    result = {}
    for metric in METRICS:
        values = [row[metric] for row in rows]
        result[metric] = {
            "pass_rate": round(sum(values) / len(values), 4),
            "ratings": len(values),
        }
    return result


def summarize(manifest: dict, raw_scores: list[dict]) -> dict:
    questions = {row["id"]: row for row in manifest["questions"]}
    grouped: dict[str, list[dict]] = defaultdict(list)
    seen = set()
    for raw in raw_scores:
        case_id = (raw.get("case_id") or "").strip()
        reviewer = (raw.get("reviewer") or "").strip()
        if case_id not in questions:
            raise HumanScoringError(f"unknown case_id: {case_id or '<blank>'}")
        if not reviewer:
            raise HumanScoringError(f"{case_id} has a blank reviewer")
        key = (case_id, reviewer)
        if key in seen:
            raise HumanScoringError(f"duplicate score row: {case_id} {reviewer}")
        seen.add(key)
        row = {"case_id": case_id, "reviewer": reviewer}
        for metric in METRICS:
            row[metric] = _binary((raw.get(metric) or "").strip(), case_id, reviewer, metric)
        grouped[case_id].append(row)

    missing = sorted(set(questions) - set(grouped))
    if missing:
        raise HumanScoringError(f"missing scores for {len(missing)} cases: {', '.join(missing[:5])}")

    ordered = []
    pairs = {metric: [] for metric in METRICS}
    disagreements = {metric: 0 for metric in METRICS}
    for case_id in questions:
        rows = sorted(grouped[case_id], key=lambda item: item["reviewer"])
        if len(rows) != 2 or rows[0]["reviewer"] == rows[1]["reviewer"]:
            raise HumanScoringError(f"{case_id} must have exactly two distinct reviewers")
        ordered.extend(rows)
        for metric in METRICS:
            pair = (rows[0][metric], rows[1][metric])
            pairs[metric].append(pair)
            disagreements[metric] += pair[0] != pair[1]

    reviewers = {row["reviewer"] for row in ordered}
    if len(reviewers) != 2:
        raise HumanScoringError(
            f"the evaluation must use the same two reviewers; found {len(reviewers)} labels"
        )

    slices = {}
    for field in SLICE_FIELDS:
        by_value: dict[str, list[dict]] = defaultdict(list)
        for row in ordered:
            by_value[questions[row["case_id"]][field]].append(row)
        slices[field] = {
            value: _metric_summary(rows) for value, rows in sorted(by_value.items())
        }

    return {
        "schema": "yieldgpt.human-evaluation/1",
        "trial_version": manifest["version"],
        "question_count": len(questions),
        "reviewer_count": len(reviewers),
        "overall": _metric_summary(ordered),
        "agreement": {
            metric: {
                "cohen_kappa": _kappa(pairs[metric]),
                "disagreements": disagreements[metric],
            }
            for metric in METRICS
        },
        "slices": slices,
    }


def load_manifest(path: Path) -> dict:
    return json.loads(path.read_text(encoding="utf-8"))


def render_markdown(summary: dict) -> str:
    lines = [
        "# Human evaluation summary",
        "",
        f"Trial version: `{summary['trial_version']}`",
        f"Questions: {summary['question_count']}",
        f"Reviewers: {summary['reviewer_count']}",
        "",
        "## Overall",
        "",
        "| Metric | Pass rate | Cohen kappa | Disagreements |",
        "|---|---:|---:|---:|",
    ]
    for metric in METRICS:
        overall = summary["overall"][metric]
        agreement = summary["agreement"][metric]
        kappa = agreement["cohen_kappa"]
        kappa_text = "n/a" if kappa is None else f"{kappa:.4f}"
        lines.append(
            f"| {metric} | {overall['pass_rate']:.1%} | {kappa_text} | "
            f"{agreement['disagreements']} |"
        )
    for field in SLICE_FIELDS:
        lines.extend(["", f"## By {field.replace('_', ' ')}", ""])
        for value, metrics in summary["slices"][field].items():
            rates = ", ".join(
                f"{metric} {metrics[metric]['pass_rate']:.1%}" for metric in METRICS
            )
            lines.append(f"- **{value}:** {rates}")
    return "\n".join(lines) + "\n"
