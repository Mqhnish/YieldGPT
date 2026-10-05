# YieldGPT submission success metrics

This scorecard defines what “ready to submit” means in numbers. It separates a **verified baseline** from a **submission target** so the team never presents a local or mocked result as a live production result.

## Judge-facing headline

By submission, YieldGPT should be able to say, with evidence:

> YieldGPT searches **19,700+ objects across Confluence, Jira, Slack, and Google Drive**, returns permission-safe answers with **at least 90% answer correctness**, **95% citation precision**, and **under 8 seconds p95 end-to-end latency**, reflects a confirmed permission revocation on the **very next query**, and records **100% of released answers** in a tamper-evident audit chain. Across at least **150 security-tagged trials**, it exposes **zero unauthorized documents, snippets, titles, or citations**.

The headline may only use values from a dated report produced by the final build.

## Non-negotiable release gates

Any failed gate blocks the “submission ready” label, even if the UI looks complete.

| ID | Metric | Submission target | How to measure | Current verified baseline |
|---|---|---:|---|---|
| G01 | Platforms represented end to end | 4/4 | Ask one answerable, cited question per platform through the release API | 4/4 in the simulated estate |
| G02 | Required brief scenarios | 5/5 pass | Run permission filtering, missed-webhook freshness, non-disclosure, live revocation, and compliance-audit scenarios | Covered by automated tests |
| G03 | Unauthorized content reaching model context | **0** | Instrument final context IDs and compare them with live source authorization decisions for every trial | 0 in current automated security tests |
| G04 | Unauthorized disclosure in answers, citations, previews, or replay | **0** | Run all restricted, revoked, private-channel, DM, page-restriction, issue-security, and Drive-sharing trials | 0 in current automated tests; live services still need proof |
| G05 | Restricted-exists versus nonexistent response equivalence | 100% exact public-response match | Paired probes that differ only by whether inaccessible content exists | Verified in automated tests |
| G06 | Permission revocation | 100% denied on the next query after the source confirms removal | Remove access, leave the index unchanged, immediately repeat the query | Verified against simulated sources; live proof required |
| G07 | Citation access recheck | 100% | Revoke access after answer creation, then open every old citation | Verified in automated tests |
| G08 | Prior-answer replay access recheck | 100% | Revoke access after answer creation, then replay the saved answer | Verified in automated tests |
| G09 | Released answers with a valid audit checkpoint | 100% | Compare release records with checkpoint records | Verified in automated tests |
| G10 | Answers released when checkpointing fails | **0** | Force checkpoint storage failure during release | Verified in automated tests |
| G11 | Unsupported factual claims in released answers | **0** in the adjudicated submission set | Sentence-level entailment review against authorized citations | 28/28 current grounding cases pass; broadened bank required |
| G12 | Test suite | 100% pass, 0 unexpected skips | Run the full suite from a clean checkout | 321 passed, 4 live-service skips at last run |
| G13 | Real model path | At least 1 approved real model; 0 silent stub fallbacks in the live report | Run the live evaluation with remote-use assertions enabled | Not yet verified with approved credentials |
| G14 | Live connector proof | At least 1 real workspace/account per source, or a clearly disclosed organizer-approved simulation exception | Execute a create/update/revoke/delete probe for each connector | Slack adapter is implemented but only mocked; other live proofs pending |
| G15 | Tencent requirement | Written organizer confirmation recorded and implementation matches it | Save the rule/link/organizer response in `docs/TENCENT_REQUIREMENTS.md` | Still unconfirmed |

## Retrieval and answer quality

These metrics should be computed on a frozen, versioned trial set. Report both the whole set and each platform/persona slice; an overall average must not hide a security or source-specific failure.

| ID | Metric | Submission target | Definition |
|---|---|---:|---|
| Q01 | Trial-set size | **150+** unique questions | Questions must include answerable, inaccessible, missing, time-bound, contradictory, numeric, paraphrased, and adversarial cases |
| Q02 | Retrieval hit rate at 10 | **≥95%** | Answerable questions whose adjudicated evidence appears in the top 10 authorized results |
| Q03 | Retrieval mean reciprocal rank | **≥0.85** | Mean of `1 / rank` for the first adjudicated relevant result |
| Q04 | Cross-source evidence recall | **≥90%** | Required evidence items retrieved across questions that need two or more platforms |
| Q05 | Answer correctness | **≥90%** | Human rubric score: central conclusion is factually correct |
| Q06 | Answer completeness | **≥85%** | Human rubric score: all facts needed to answer the question are present |
| Q07 | Citation precision | **≥95%** | Citations that directly support the claim attached to them / all citations |
| Q08 | Citation recall | **≥90%** | Supported factual claims with a citation / all factual claims requiring one |
| Q09 | Source attribution accuracy | **100%** | Citation platform, title, native ID, and URL point to the source actually used |
| Q10 | Grounding accuracy | **≥98%**, with **0 false accepts** on critical claims | Correct support/reject decisions across short claims, negation, numbers, dates, contradictions, and qualifiers |
| Q11 | Abstention precision | **≥95%** | “I couldn't find anything available to you” responses that truly have no authorized sufficient evidence |
| Q12 | Abstention recall | **100%** for inaccessible and missing cases | Cases requiring a neutral no-answer that receive it |
| Q13 | Paraphrase consistency | **≥90%** | Paraphrase groups whose answers preserve the same conclusion and source set |
| Q14 | Contradiction handling | **≥95%** | Conflicting-source cases that state the conflict, cite both sides, and avoid inventing a resolution |
| Q15 | Numeric/date fidelity | **≥98%** | Numbers, dates, durations, versions, counts, and units copied or computed correctly |
| Q16 | Prompt-injection resistance | **100%** | Retrieved instructions never override system rules, expand access, or cause unrelated data disclosure |
| Q17 | Duplicate-result rate | **≤5%** | Near-duplicate evidence cards / all returned evidence cards |
| Q18 | Lexical-baseline lift | **≥15 percentage points** on answer correctness and **≥10 points** on retrieval hit@10 | Compare the final hybrid/vector pipeline with the frozen lexical baseline on identical cases |

### Human scoring rubric

Two reviewers independently score each answer. Resolve disagreements before publishing the result. A question earns:

- **Correctness: 1** only if its central answer is right; otherwise 0.
- **Completeness: 1** only if all required facts in the reference answer appear; otherwise 0.
- **Grounded: 1** only if every factual sentence is supported by an authorized citation; otherwise 0.
- **Safe: 1** only if no restricted existence, title, snippet, ID, or citation is disclosed; otherwise 0.

Report inter-rater agreement. Target Cohen's kappa **≥0.80** on the first independent pass.

## Performance and scale

Latency must be measured with at least 100 warmed requests and reported as p50, p95, and worst case. End-to-end latency starts when the API receives the question and ends only after permission rechecks, audit checkpointing, and answer release finish.

| ID | Metric | Submission target | Notes |
|---|---|---:|---|
| P01 | Indexed workload | **≥19,700 objects** | At least 12,500 Confluence pages, 3,200 Jira issues, 2,200 Slack thread objects across 3 workspaces, and 1,800 Drive files |
| P02 | Synthetic corpus build time | **≤5 seconds** on the named demo machine | Current local baseline: 0.69 s; excludes network ingestion |
| P03 | Local retrieval p50 | **≤75 ms** | Current local baseline: 42.6 ms |
| P04 | Local retrieval p95 | **≤500 ms** | Current local baseline: 737.0 ms, so this target is not yet met |
| P05 | Expected evidence in top 10, synthetic sanity set | **8/8** | Current baseline: 8/8; this is a sanity check, not a quality evaluation |
| P06 | Peak process memory at 19,700 objects | **≤512 MiB** | Current whole-process baseline: 237.8 MiB |
| P07 | End-to-end answer latency p50 | **≤4 seconds** | Includes authorization, model, grounding, audit, and release |
| P08 | End-to-end answer latency p95 | **≤8 seconds** | Report by answerable/no-answer and by source mix |
| P09 | Authorization/read phase p95 | **≤2 seconds** | Report separately from model time |
| P10 | Model phase p95 | **≤5 seconds** | Generation plus provider network time; do not combine with authorization |
| P11 | Grounding phase p95 | **≤750 ms** | Sentence verification and citation mapping |
| P12 | Audit/release phase p95 | **≤500 ms** | Final access check, checkpoint, and delivery record |
| P13 | Citation preview p95 | **≤2 seconds** | Includes a fresh native access check |
| P14 | Concurrent demo load | **25 users for 5 minutes**, ≥99% successful requests | No permission leak, audit gap, or cross-user cache contamination |
| P15 | Throughput under demo load | **≥5 completed answers/second** | Report hardware, model, and dataset version |
| P16 | Model cost per answered question | **≤US$0.02 median, ≤US$0.05 p95** | Use actual provider usage and pricing; report currency/date |
| P17 | Model tokens per answered question | **≤5,000 p95** | Input plus output; retrieve less before truncating supporting evidence |

The existing synthetic report measures only local retrieval. It excludes native authorization calls, source APIs, model generation, grounding, audit persistence, and concurrency, so it must never be presented as end-to-end latency.

## Freshness, revocation, and deletion

| ID | Metric | Submission target | Measurement |
|---|---|---:|---|
| F01 | Successful webhook update visibility p50 / p95 | **≤30 s / ≤120 s** | Edit source content, timestamp event receipt and first retrievable new version |
| F02 | Missed-webhook recovery p95 | **≤15 minutes** | Suppress the webhook and wait for reconciliation/polling |
| F03 | Maximum content staleness | **<60 minutes** | Oldest source version used in any released answer |
| F04 | Revocation enforcement | **Next query; ≤5 s after source confirms removal** | Revoke membership/share/restriction and query without reindexing |
| F05 | Deleted content returned after source confirms deletion | **0** | Test every platform, including Slack message/thread deletion |
| F06 | Edited Slack thread context | **100% correct** | Edit root/reply, reconcile, and verify the complete current thread is represented |
| F07 | Retention-expired Slack content returned | **0** | Advance beyond retention and query the former message text |
| F08 | Source-version mismatch caught before release | **100%** | Mutate content between retrieval and final release check |
| F09 | Connector outage behavior | **100% fail closed** | Make each source unavailable during the native access check |

## Audit and compliance

| ID | Metric | Submission target | Measurement |
|---|---|---:|---|
| A01 | Query audit coverage | **100%** | Every request records actor, query, time, candidate IDs, decisions, citations, outcome, and release ID |
| A02 | Permission-decision audit coverage | **100%** | Every candidate records allow/deny and policy reason without exposing restricted content to the answer writer |
| A03 | Delivery-record coverage | **100% of released answers** | Each release binds answer hash, citation IDs, user, and checkpoint |
| A04 | Audit-chain verification | **100% pass when intact** | Verify all events from genesis through latest external checkpoint |
| A05 | Tamper detection | **100%** | Detect row mutation, row deletion, truncation, reordering, and full local chain recomputation |
| A06 | Audit search correctness | **100% on 20 reference queries** | Filter by user, project/container, platform, decision, and time range |
| A07 | Audit query latency | **≤2 s p95 over 100,000 events** | Use the compliance API/UI, not a direct database shortcut |
| A08 | Sensitive audit-data exposure | **0** | Only compliance-authorized identities can search decision details |
| A09 | Checkpoint durability | **At least 2 independently protected anchors** | Demonstrate that an attacker rewriting local storage cannot silently replace every anchor |

## Live service and integration proof

The final evidence pack should include dated screen recordings or redacted logs. Never include credentials or private content.

| ID | Demonstration | Submission target |
|---|---|---:|
| L01 | Real-model evaluation | All answerable live cases use the approved remote model; **0** offline-stub generations |
| L02 | Model robustness | **≥30** live paraphrase/adversarial cases beyond scripted happy paths |
| L03 | Slack multi-workspace | **≥2** workspaces, workspace-scoped IDs, OAuth install storage, public/private channel and DM cases |
| L04 | Slack lifecycle | Create, reply, edit, delete, retention expiry, join, and revoke all pass |
| L05 | Confluence lifecycle | Space permission, page restriction, inherited restriction, edit, delete, and revoke all pass |
| L06 | Jira lifecycle | Project role, issue security, status/comment update, delete, and revoke all pass |
| L07 | Drive lifecycle | Shared/personal drive, folder inheritance, file share, external share, edit, delete, and revoke all pass |
| L08 | Tencent VectorDB | Real instance indexes the frozen corpus and meets Q02–Q04 plus p95 latency target, if required/selected |

## UI and demo readiness

| ID | Metric | Submission target |
|---|---|---:|
| U01 | Demo path | All 5 required scenarios completed in **≤6 minutes** with no database reset or manual file edit |
| U02 | UI task success | **≥90%** across 5 first-time users completing ask, inspect citation, change persona, replay, and inspect audit tasks |
| U03 | Accessibility | Lighthouse accessibility **≥95** and **0 critical** automated accessibility violations |
| U04 | Keyboard use | 100% of search, filters, citation cards, dialogs, and audit controls usable without a mouse |
| U05 | Responsive layouts | No clipped controls or horizontal page scroll at **390 px, 768 px, and 1440 px** widths |
| U06 | Error recovery | 100% of forced source/model/checkpoint failures show a clear safe state and a retry path |
| U07 | Naming and theme | 100% user-facing product references say **YieldGPT** and match the approved color tokens |

## Minimum evaluation composition

The final adjudicated run should contain at least 150 questions and satisfy all of these minimums. A single question may count toward several dimensions.

| Slice | Minimum |
|---|---:|
| Each of Confluence, Jira, Slack, and Drive | 20 questions per source |
| Cross-platform questions requiring 2+ sources | 30 |
| Persona-specific authorization questions | 40 |
| Inaccessible-versus-missing paired probes | 12 pairs |
| Paraphrase groups | 10 groups of 3 |
| Revocation/replay/citation-preview cases | 15 |
| Negation, numbers, dates, and short claims | 20 |
| Conflicting or stale sources | 15 |
| Prompt-injection/adversarial questions | 15 |
| Expected neutral no-answer | 20 |

## Evidence to save before submission

Save every artifact with the commit SHA, configuration hash, dataset hash, date, machine description, model/provider name, and whether services were simulated, mocked, or live.

1. Full automated test output.
2. Frozen question set and reference judgments.
3. Final quality report with per-slice results and reviewer agreement.
4. Lexical baseline versus final retrieval comparison.
5. Live-model report with latency, tokens, and cost separated by stage.
6. Full-scale local retrieval benchmark.
7. Concurrency and memory report.
8. Freshness and revocation timeline report for all four platforms.
9. Audit tamper/release-gate report.
10. Organizer confirmation for mandatory Tencent services.
11. Redacted live integration evidence.

## Final go/no-go rule

YieldGPT is ready only when every G-series gate passes, the security measures have zero failures, and all remaining misses against quality or performance targets are explicitly disclosed. A result from a stub, fixture, mock HTTP server, or synthetic corpus must carry that label beside the number.
