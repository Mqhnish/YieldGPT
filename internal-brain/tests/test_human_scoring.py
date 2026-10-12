import pytest

from evaluation.human_scoring import HumanScoringError, summarize


def _manifest():
    return {
        "version": "test",
        "questions": [
            {
                "id": "Q001",
                "persona": "jdoe",
                "case_type": "Answer",
                "source_scope": "Slack",
            },
            {
                "id": "Q002",
                "persona": "asha",
                "case_type": "Neutral no-answer",
                "source_scope": "Jira",
            },
        ],
    }


def _scores():
    return [
        {"case_id": case_id, "reviewer": reviewer, **{metric: score for metric in ("correctness", "completeness", "grounded", "safe")}}
        for case_id, score in (("Q001", "1"), ("Q002", "0"))
        for reviewer in ("alice", "bob")
    ]


def test_summary_reports_overall_slices_and_agreement():
    result = summarize(_manifest(), _scores())
    assert result["question_count"] == 2
    assert result["reviewer_count"] == 2
    assert result["overall"]["correctness"]["pass_rate"] == 0.5
    assert result["agreement"]["correctness"] == {
        "cohen_kappa": 1.0,
        "disagreements": 0,
    }
    assert result["slices"]["persona"]["jdoe"]["correctness"]["pass_rate"] == 1.0


def test_summary_rejects_blank_template_scores():
    rows = _scores()
    rows[0]["safe"] = ""
    with pytest.raises(HumanScoringError, match="invalid safe"):
        summarize(_manifest(), rows)


def test_summary_requires_two_reviewers_per_case():
    with pytest.raises(HumanScoringError, match="exactly two"):
        summarize(_manifest(), _scores()[:-1])


def test_summary_requires_same_reviewers_across_cases():
    rows = _scores()
    rows[-1]["reviewer"] = "charlie"
    with pytest.raises(HumanScoringError, match="same two reviewers"):
        summarize(_manifest(), rows)
