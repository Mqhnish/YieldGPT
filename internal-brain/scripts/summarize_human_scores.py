#!/usr/bin/env python3
"""Validate two-reviewer trial scores and write JSON and Markdown summaries."""
from __future__ import annotations

import argparse
import json
from pathlib import Path
import sys

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from evaluation.human_scoring import (
    HumanScoringError,
    load_manifest,
    load_scores,
    render_markdown,
    summarize,
)


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--trial-set",
        type=Path,
        default=ROOT / "evaluation" / "trial_set_v1.json",
    )
    parser.add_argument(
        "--scores",
        type=Path,
        default=ROOT / "evaluation" / "human_scores_v1.csv",
    )
    parser.add_argument(
        "--json",
        type=Path,
        default=ROOT / "evaluation" / "reports" / "human_scores_v1.json",
    )
    parser.add_argument(
        "--markdown",
        type=Path,
        default=ROOT / "evaluation" / "reports" / "human_scores_v1.md",
    )
    args = parser.parse_args()

    try:
        summary = summarize(load_manifest(args.trial_set), load_scores(args.scores))
    except HumanScoringError as exc:
        print(f"human scoring incomplete: {exc}", file=sys.stderr)
        return 2

    args.json.parent.mkdir(parents=True, exist_ok=True)
    args.markdown.parent.mkdir(parents=True, exist_ok=True)
    args.json.write_text(json.dumps(summary, indent=2) + "\n", encoding="utf-8")
    args.markdown.write_text(render_markdown(summary), encoding="utf-8")
    print(f"summarized {summary['question_count']} cases from two reviewers")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
