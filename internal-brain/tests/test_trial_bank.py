from pathlib import Path

import pytest

from evaluation.trial_bank import (
    TrialBankError,
    build_manifest,
    load_bank,
    parse_bank,
    recommended_live_ids,
    scoring_csv,
)


def test_repository_bank_is_complete_and_ordered():
    text = load_bank()
    rows = parse_bank(text)
    assert len(rows) == 160
    assert rows[0]["id"] == "Q001"
    assert rows[-1]["id"] == "Q160"
    assert {row["section"] for row in rows} == set("ABCDEFGHIJKLMNOP")
    assert all(row["question"] for row in rows)


def test_manifest_has_stable_source_hash_and_report_slices():
    text = load_bank()
    one = build_manifest(text)
    two = build_manifest(text)
    assert one == two
    assert len(one["source_sha256"]) == 64
    assert one["question_count"] == 160
    assert sum(one["coverage"]["by_persona"].values()) == 160
    assert sum(one["coverage"]["by_case_type"].values()) == 160
    assert sum(one["coverage"]["by_section"].values()) == 160
    assert len(one["recommended_live_ids"]) == 40


def test_scoring_template_has_two_blank_rows_per_case():
    rows = parse_bank(load_bank())
    output = scoring_csv(rows).splitlines()
    assert output[0] == "case_id,reviewer,correctness,completeness,grounded,safe,notes"
    assert len(output) == 321
    assert output[1].startswith("Q001,reviewer_1,")
    assert output[2].startswith("Q001,reviewer_2,")
    assert output[-2].startswith("Q160,reviewer_1,")
    assert output[-1].startswith("Q160,reviewer_2,")


def test_parser_rejects_incomplete_bank():
    text = load_bank()
    with pytest.raises(TrialBankError):
        parse_bank(text.replace("Q160", "Q999", 1))


def test_recommended_subset_must_remain_large_enough():
    text = load_bank()
    assert recommended_live_ids(text)[0] == "Q001"
    with pytest.raises(TrialBankError):
        recommended_live_ids(text.split("For a concise live-model run", 1)[0] + "For a concise live-model run: Q001")

