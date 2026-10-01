# Member 2 review against the complete challenge brief

The supplied brief defines required behavior and five scenarios. It does not provide numerical judging weights or settle the precise Tencent service minimum. Official event material positions Tencent products as part of the event; exact mandatory usage remains unconfirmed. See [the requirements record](TENCENT_REQUIREMENTS.md) before deployment. This review maps implemented evidence to those requirements without assuming an unpublished rubric.

**Conclusion:** Member 2 is ready for teammate integration and an offline judged demonstration. The complete team solution is not yet production-complete or verified with live model credentials. A polished UI cannot substitute for the remaining live cloud and identity verification.

## Requirement-to-evidence map

| Brief requirement | Member 2 implementation and verification | Remaining dependency |
|---|---|---|
| Preserve heterogeneous permission semantics | Reuses Member 1's native Connector checks; Confluence/Jira semantics and the shared base contract preserved; Member 3's extended Drive semantics integrated; contract tests retained. Optional Slack performs delegated user reads. | Member 1's live source adapters and trusted account mapping. Real Slack is mock-HTTP verified, not live certified. |
| Identify the asker and filter before the LLM | Corporate User passed into every candidate check; source content enters context only after current authorization and read validation; no cross-question permission cache. Evaluator independently checks every model-context source. | Replace the seeded login with trusted SSO before connecting real users/data. |
| Fan out, rank and assemble coherent cross-source evidence | Searches four platforms; explicit source/time filters; complete passages with stable IDs/versions; up to three linked hops with authorization at every hop; a regression spans Jira → Confluence → Drive → Slack. | Lexical search is implemented; embeddings are optional future relevance work. Broad queries require capacity tuning for live API checks. |
| Unified answer with citations | One combined answer containing source passages; validated citations, original URLs, independently checked evidence previews; optional model selects passages. | Real AI augmentation must be demonstrated after approved model credentials are configured. Free-form prose synthesis is not implemented; describe this accurately as model-selected, combined evidence. |
| Fresh data within minutes to an hour | Current source reads at query time; updated versions before release; shared webhooks/polling; optional Slack signed events plus 15-minute reconciliation; new failover step verified after a missed webhook. | Sustained live freshness depends on connector completeness, outages, request budgets and scan duration. Local synthetic speed does not prove this SLA. |
| No restricted-content or existence disclosure | Neutral missing response and no citations; hidden documents do not set ranking statistics or pre-auth cutoffs; denied intermediate links stop traversal; account changes clear prior UI content. | Timing/availability side channels are not proven absent. Do not claim cryptographic indistinguishability or constant-time execution. |
| Live revocation | Permissions rechecked during source read, before delivery, on citation preview, and when replaying a question; changed evidence discards and rebuilds the answer once; a second failure withholds it. | No distributed check can revoke text already delivered or remove the final check-to-delivery race entirely. |
| Complete, queryable audit evidence | Original event schemas retained with extra phases, context fingerprints/passages, attempts, model mode and preview events. Terminal audit failure prevents answer delivery. Priya reconstructs the exact brief inquiry. | Member 3's encrypted storage, retention, S3 Object Lock checkpoints and delivery middleware are integrated. The default local checkpoint mode is weaker; live WORM tests remain separately configured. |
| Mitigate invented or training-derived claims | Model returns only passage IDs; server renders exact approved passages and rejects unknown IDs; grounding tests cover altered numbers, lost negation, unsupported clauses and citation laundering. | Exact quotations do not prove source truth or guarantee perfect selection, completeness or resolution of contradictions. |

## Improvements made after reviewing this brief

1. **Cross-platform links now traverse up to three hops**, with cycle detection and an independent gate on every target. A denied intermediate document cannot expose its linked descendants.
2. **Requested runbooks/checklists retain their complete procedure.** Context packing and model selection cannot silently discard a late failover step. If the complete procedure cannot fit, the query abstains instead of presenting a truncated operational procedure.
3. **The final citation-preview permission check is recorded**, matching the brief's requirement to log meaningful authorization decisions.
4. **All five scenarios now have generated worked examples**, including before/after source updates, private-channel revocation and a real audit reconstruction through the compliance read policy.

See [worked examples](WORKED_EXAMPLES.md), [added regressions](../tests/test_brief_acceptance.py), [Member 2 integration handoff](HANDOFF_MEMBER2.md) and [evaluation methods](EVALUATION.md).

## How to present this to judges

Start with the engineer's cross-platform migration question and open its citations. Switch to the contractor and ask about the breach; show the neutral result. Demonstrate a missed runbook webhook and an immediate source update on the next question. Revoke private-channel access and repeat the query. Finally, use the compliance view to reconstruct who asked, what was considered, which decisions were made, and what was answered.

The generated examples reproduce these steps without credentials and keep all temporary audit data separate from the running demo. Supplement them with a separately recorded live model/Slack run once credentials are available. Do not present offline selection as a live language-model response or a synthetic index benchmark as full-company performance.

## Final team priorities

- **Member 2:** preserve the tested permission/context boundary and strict grounding while teammates integrate. Run the evaluation suite after every merge.
- **Member 1:** provide trusted identity mappings and real-source configuration; measure source-native permission calls, pagination/rate budgets and missed-event repair at the target scale.
- **Member 3:** retain the integrated independent checkpoint and compliance implementations; verify the configured WORM deployment with the live suite.
- **Together:** configure the approved AI endpoint, run a live credentialed demonstration, and record the exact freshness/latency measurements and limitations.

The latest integration also adds a measured lexical baseline, 28 grounding evaluation cases, actor-scoped replay, multi-workspace Slack and encrypted OAuth installation storage. See [the gap-by-gap review](INTEGRATION_REVIEW.md).
