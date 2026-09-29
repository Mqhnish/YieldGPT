# Evidence and retrieval evaluation

Member 2 owns the question set, offline evaluator, and synthetic retrieval load fixture. These complement Member 1's connector/authorization tests and Member 3's audit integrity tests. They do not replace those tests.

## Run the checks

From the repository root, using the environment where `requirements.txt` is installed:

```sh
python -m pytest tests/test_evaluation_data.py tests/test_member2_review.py -q
python scripts/evaluate.py --json reports/evaluation.json --markdown reports/evaluation.md
python scripts/benchmark.py --size small --json reports/benchmark-small.json
python scripts/benchmark.py --size full --json reports/benchmark-full.json --markdown reports/benchmark-full.md
```

Reports are created only at the destinations requested. A failed case or missed benchmark target exits with a nonzero status, so these commands can be used in CI. Filter the evaluator with `--category security` or `--case exact-migration-epic`; repeat the option to combine selections. A filter selecting zero cases is an error.

The submitted measured snapshots are in `evaluation/reports/`. Regenerate them after changing the code. JSON reports include implementation-file fingerprints taken at run start, the case/corpus fingerprint, and the run time so a report is not mistaken for a guarantee about a later build.

The scripts force the offline `stub` provider and configure temporary audit, anchor and sync paths **before importing the application**. Each evaluation uses a fresh fictional company and a temporary durable sync store. Your existing demo audit and synchronization state are not used or modified. No model key or network service is required. Run these as separate processes, not after importing the app into an interactive Python session.

## What the question set measures

`evaluation/cases.py` contains hand-curated questions drawn from the existing fictional Company A records. It covers exact identifiers, natural paraphrases, answers needing multiple platforms, recent Slack windows, absent evidence, and different users' permissions. Expected facts come from fixture records, not from whichever answer the implementation currently produces.

- `expected_all`: every listed document must appear in the citations.
- `expected_any`: at least one listed document must appear. Use this when several records independently support the same answer.
- `forbidden`: these documents must never appear in citations or model context. This includes access restrictions, expired time windows and poisoned content.
- `no_answer`: require the exact neutral no-answer text and an empty citation list.
- `answer_contains`: each group of alternatives must have at least one phrase present in the answer.
- `answer_absent`: a phrase that must not be disclosed or invented.

**Source recall** is the fraction of citation obligations satisfied: one obligation per `expected_all` item and one per nonempty `expected_any` group. This is not precision; an extra relevant source may be perfectly valid. Do not rename this metric to “accuracy.” The evaluator separately reports all-case pass rate, neutral-answer success, forbidden citations, and unauthorized citations. It independently checks both citations and every assembled model-context source with the user's current connector permissions.

These phrase checks catch selected factual failures such as missing amounts, dates and actors. They do not establish general semantic entailment. A retrieved source could be correctly cited while the answer misrepresents it. The grounding tests must separately exercise negation, altered numbers, unsupported clauses, fabricated source references and source instructions.

`tests/test_member2_review.py` independently checks that unrelated citations cannot be attached to a valid claim, that adding an unsupported clause invalidates an otherwise supported sentence, and that permissions or source versions changing during the final read invalidate the answer or evidence preview.

Time windows use the fixture's relative timestamps. “Last week” means the rolling previous seven days, and “last sprint” is fourteen days in this demo. A source-document update time is not proof that an event occurred in that window. Several cases require a Slack message in the window; an old ticket does not substitute for that message.

The fixture includes one intentionally poisoned Drive file. It must be quarantined, while an independently relevant permitted guide can still answer the question. Admin and audit roles do not grant access to source documents.

## Synthetic scale workload

`evaluation/synthetic.py` generates a deterministic index-only corpus, with seed `20260928` and fixed timestamps:

| Source | Objects | Shape |
|---|---:|---|
| Confluence | 12,500 pages | 52 spaces, parent references |
| Jira | 3,200 issues | 32 projects |
| Slack | 2,200 thread objects | 220 channels across 3 workspaces |
| Drive | 1,800 files | 150 folders with drive/team/folder tags |

This is **19,700 generated objects**, not 19,700 objects fetched from live platforms. The benchmark records a corpus fingerprint, local environment, build duration, warmed search p50/p95, whole-process peak memory and expected-source recall at configurable `--top-k` (default 10). `--rounds` controls repeat count, default five. The small corpus is for quick smoke checks.

Documents contain overlapping operational topics, varied sentence lengths and seven ACL-hint patterns. Eight hand-written targets test meaningful retrieval among that noise. The benchmark applies a synthetic principal-hint filter. **It does not test native platform permissions, real-time revocation, connector throughput, network latency, concurrent load, model cost, grounding or end-to-end answer latency.** Do not present it as evidence of those capabilities. Peak memory includes generation and the Python process, not just the index.

The full scale test deliberately has no arbitrary latency pass threshold. Hardware varies; record the measurements and choose a justified service target before enforcing one. It fails when an expected target is absent from the top results. Eight targets are a sanity check, not a production relevance study.

## Team handoff

Keep the existing `Brain.ask(user, question)` response's `answer`, `citations`, `query_id`, and `blocked` fields. Citation objects must retain `uid`. Keep the `context_assembled/1` event with source `uid` and `version`. These let the evaluator check the same boundaries as the employee UI without reaching into retrieval internals.

Member 1 can replace connectors without changing the evaluator, provided the fictional fixture UIDs and `Connector.check()` contract remain stable. Member 3 can replace audit persistence while preserving the existing queryable event contract. `scripts/benchmark.py` requires only the existing `Index.upsert(doc, hint)` and `Index.search(query, platforms, since)` contracts.

Before a judged demonstration, run the whole automated test suite and save a fresh evaluator report. Report failures honestly and keep the measured report beside the submitted code. For a real model, create a separate reviewed evaluation run using permitted test accounts; these offline results must not be described as Hunyuan or live-Slack results.
