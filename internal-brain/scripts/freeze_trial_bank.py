#!/usr/bin/env python3
"""Freeze TRIAL_QUESTION_BANK.md into JSON and a human scoring template."""
from __future__ import annotations

import argparse
from pathlib import Path
import sys

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from evaluation.trial_bank import build_manifest, load_bank, manifest_json, scoring_csv


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--bank",
        type=Path,
        default=ROOT.parent / "TRIAL_QUESTION_BANK.md",
        help="Reviewable Markdown question bank",
    )
    parser.add_argument(
        "--output",
        type=Path,
        default=ROOT / "evaluation" / "trial_set_v1.json",
        help="Frozen JSON output",
    )
    parser.add_argument(
        "--scores",
        type=Path,
        default=ROOT / "evaluation" / "human_scores_v1.csv",
        help="Blank two-reviewer scoring template",
    )
    parser.add_argument(
        "--check",
        action="store_true",
        help="Fail if committed outputs differ; do not write files",
    )
    args = parser.parse_args()

    text = load_bank(args.bank)
    manifest = build_manifest(text)
    frozen = manifest_json(text)
    scores = scoring_csv(manifest["questions"])

    if args.check:
        mismatches = []
        for path, expected in ((args.output, frozen), (args.scores, scores)):
            if not path.exists() or path.read_text(encoding="utf-8") != expected:
                mismatches.append(str(path))
        if mismatches:
            print("stale trial artifacts: " + ", ".join(mismatches), file=sys.stderr)
            return 1
    else:
        args.output.parent.mkdir(parents=True, exist_ok=True)
        args.output.write_text(frozen, encoding="utf-8")
        args.scores.write_text(scores, encoding="utf-8")

    coverage = manifest["coverage"]
    print(
        f"trial set {manifest['version']}: {manifest['question_count']} questions; "
        f"{len(manifest['recommended_live_ids'])} recommended live cases"
    )
    print("personas:", coverage["by_persona"])
    print("case types:", coverage["by_case_type"])
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
