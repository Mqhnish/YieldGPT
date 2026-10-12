"""Parse and freeze the versioned YieldGPT trial question bank.

The Markdown bank remains the reviewable source. This module turns it into a
stable JSON artifact with explicit slices for reporting and human adjudication.
"""
from __future__ import annotations

from collections import Counter
import csv
import hashlib
import io
import json
from pathlib import Path
import re

ROOT = Path(__file__).resolve().parents[2]
BANK_PATH = ROOT / "TRIAL_QUESTION_BANK.md"
SCHEMA = "yieldgpt.trial-set/1"
VERSION = "2026-10-12"
QUESTION_RE = re.compile(
    r"^- \*\*(Q\d{3}) \u2014 ([^·]+) · ([^·]+) · ([^.]+)\.\*\* (.+)$"
)
SECTION_RE = re.compile(r"^## ([A-P])\. (.+)$")
ALLOWED_CASE_TYPES = {
    "Answer",
    "Role-dependent",
    "Neutral no-answer",
    "Controlled mutation",
    "Audit result",
}


class TrialBankError(ValueError):
    pass


def parse_bank(text: str) -> list[dict]:
    section = None
    rows = []
    for raw in text.splitlines():
        section_match = SECTION_RE.match(raw.strip())
        if section_match:
            section = {
                "id": section_match.group(1),
                "name": section_match.group(2).strip(),
            }
            continue
        match = QUESTION_RE.match(raw.strip())
        if not match:
            continue
        if section is None:
            raise TrialBankError("question appears before a trial section")
        case_type = match.group(4).strip()
        if case_type not in ALLOWED_CASE_TYPES:
            raise TrialBankError(f"unknown case type for {match.group(1)}: {case_type}")
        rows.append(
            {
                "id": match.group(1),
                "section": section["id"],
                "section_name": section["name"],
                "persona": match.group(2).strip(),
                "source_scope": match.group(3).strip(),
                "case_type": case_type,
                "question": match.group(5).strip(),
                "human_scores": {
                    "correctness": None,
                    "completeness": None,
                    "grounded": None,
                    "safe": None,
                },
            }
        )
    validate(rows)
    return rows


def validate(rows: list[dict]) -> None:
    ids = [row["id"] for row in rows]
    expected = [f"Q{number:03d}" for number in range(1, 161)]
    if ids != expected:
        missing = sorted(set(expected) - set(ids))
        duplicates = sorted(key for key, count in Counter(ids).items() if count > 1)
        raise TrialBankError(
            f"expected Q001 through Q160 in order; missing={missing}, duplicates={duplicates}"
        )
    if len({row["question"] for row in rows}) != 160:
        raise TrialBankError("trial questions must be unique")


def recommended_live_ids(text: str) -> list[str]:
    marker = "For a concise live-model run"
    tail = text.split(marker, 1)
    if len(tail) != 2:
        raise TrialBankError("recommended live subset is missing")
    ids = []
    for item in re.findall(r"\bQ\d{3}\b", tail[1]):
        if item not in ids:
            ids.append(item)
    if len(ids) != 40:
        raise TrialBankError("recommended live subset must contain exactly 40 cases")
    return ids


def _counts(rows: list[dict], key: str) -> dict[str, int]:
    return dict(sorted(Counter(row[key] for row in rows).items()))


def build_manifest(text: str, source_path: str = "TRIAL_QUESTION_BANK.md") -> dict:
    rows = parse_bank(text)
    subset = recommended_live_ids(text)
    return {
        "schema": SCHEMA,
        "version": VERSION,
        "source_path": source_path,
        "source_sha256": hashlib.sha256(text.encode("utf-8")).hexdigest(),
        "question_count": len(rows),
        "recommended_live_ids": subset,
        "coverage": {
            "by_section": _counts(rows, "section"),
            "by_persona": _counts(rows, "persona"),
            "by_case_type": _counts(rows, "case_type"),
            "by_source_scope": _counts(rows, "source_scope"),
        },
        "questions": rows,
    }


def manifest_json(text: str) -> str:
    return json.dumps(build_manifest(text), indent=2, ensure_ascii=False) + "\n"


def scoring_csv(rows: list[dict]) -> str:
    stream = io.StringIO(newline="")
    fields = [
        "case_id",
        "reviewer",
        "correctness",
        "completeness",
        "grounded",
        "safe",
        "notes",
    ]
    writer = csv.DictWriter(stream, fieldnames=fields, lineterminator="\n")
    writer.writeheader()
    for row in rows:
        for reviewer in ("reviewer_1", "reviewer_2"):
            writer.writerow({"case_id": row["id"], "reviewer": reviewer})
    return stream.getvalue()


def load_bank(path: Path = BANK_PATH) -> str:
    return path.read_text(encoding="utf-8")

