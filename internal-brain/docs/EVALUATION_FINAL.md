# Final evaluation runbook

This runbook freezes the Member 2 evaluation set and prevents incomplete human review from being reported as a finished result. It does not claim that a live model, live Slack, or live Atlassian evaluation has passed.

## Frozen set

The reviewable source is `TRIAL_QUESTION_BANK.md` at the repository root. The committed artifacts are:

- `evaluation/trial_set_v1.json`: 160 ordered questions, source hash, slice metadata, and the documented 40-case live subset.
- `evaluation/human_scores_v1.csv`: two independent reviewer rows per question.

Regenerate the artifacts after an intentional bank change:

```bash
cd internal-brain
python scripts/freeze_trial_bank.py
```

Check that the committed outputs still match the Markdown source:

```bash
python scripts/freeze_trial_bank.py --check
```

The `2026-10-12` frozen set contains 160 questions and 40 recommended live cases. Its measured coverage is:

- Personas: asha 20, dana 9, jdoe 66, kim 25, priya 11, ravi 29.
- Case types: Answer 93, Audit result 11, Controlled mutation 17, Neutral no-answer 28, Role-dependent 11.

These numbers describe the question bank. They are not model quality scores.

## Automated runs

Run the full fixture suite first, then the evaluation runner:

```bash
cd internal-brain
python -m pytest -q
python scripts/evaluate.py --mode offline \
  --json evaluation/reports/offline.json \
  --markdown evaluation/reports/offline.md
```

Run the executable live regression cases only after the Slack, Atlassian, and Hunyuan setup checks pass. Keep credentials in the local `.env` file and never commit them.

```bash
python scripts/evaluate.py --mode live \
  --json evaluation/reports/live.json \
  --markdown evaluation/reports/live.md
```

The executable regression cases and the 160-question trial bank are separate artifacts. `evaluate.py` does not automatically execute the recommended 40 questions. Run those questions through the employee UI or API, retain each response and its citations, and transfer the two independent reviews to the scoring CSV.

Record the commit SHA, date, configuration, dataset version, model name, and whether each result is fixture or live. Controlled mutation and audit cases need the staged runbooks described in the existing evaluation documentation. A static question in the frozen bank is not proof that its scenario ran successfully.

## Human review

Use two independent reviewers. Each reviewer scores every selected case with `0` or `1` for correctness, completeness, groundedness, and safety. Reviewers should not compare scores until both passes are complete.

Replace `reviewer_1` and `reviewer_2` with stable reviewer labels, fill every score cell, then run:

```bash
python scripts/summarize_human_scores.py
```

The summarizer refuses blank scores, unknown cases, duplicate reviewer rows, and cases without exactly two distinct reviewers. On a complete file it writes overall pass rates, results by persona, case type, and source scope, plus Cohen's kappa and disagreement counts.

Do not update submission metrics from the blank template. Human quality results remain pending until the completed CSV and generated reports are reviewed and committed.

## Evidence required for a final claim

Before describing the live evaluation as complete, retain:

1. The exact frozen trial set and source hash.
2. The machine-generated fixture and live reports.
3. The completed two-reviewer CSV and generated human summary.
4. Proof that Slack used two real workspaces and that Atlassian permission checks passed.
5. The exact Hunyuan model and endpoint configuration, with secrets removed.
6. Any failures, exclusions, or unexecutable cases listed beside the reported denominator.

