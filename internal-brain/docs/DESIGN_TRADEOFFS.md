# Key design trade-offs

Companion to the architecture and trust-boundary diagram (`architecture-trust-boundaries.svg`).
Each choice below names what we gave up for it. Numbers come from the dated reports in
`evaluation/reports/`.

| Decision | What we chose | What it costs | Why |
|---|---|---|---|
| **Who decides access** | Ask each platform, live, as the user (Confluence permission check, Jira bulk permission check, Slack membership, Drive sharing), before reading, after reading and before release. | More API calls per question, and the answer depends on the platforms being up. | Copying permissions into our own model flattens four different schemes and goes stale. Live on the Atlassian site the next query after a revoke was denied in 0.27 s (Confluence) and 0.18 s (Jira). |
| **When a check fails** | Fail closed: errors, timeouts and rate limits mean "not shown". | A platform outage shows fewer answers, not wrong ones. | A leak is worse than a gap. Every phase shares one deadline, so a slow platform can't stall a question. |
| **Index prefilter** | A coarse hint (page restrictions, "anyone with an account") may only remove candidates, never allow. | More documents reach the slower live check than a precise filter would send. | A stale precise filter could hide or expose documents; a superset hint can only cost time. |
| **What the model may do** | The model only picks passage identifiers; the server writes the answer from the exact authorized text and cites every line. Extractive mode (no model call) is the default in this submission. | Answers read as quoted evidence, not free prose. | No invented numbers, flipped negations or content the model "remembers" from training. Grounding cases: 28/28, 0 false accepts. |
| **Restricted vs missing** | A denied document produces exactly the same response as one that never existed. | Users get no "ask for access" hint. | The brief forbids metadata side channels. Proven live (14/14 scenarios). |
| **Freshness** | Polling every 5 minutes with a 3-minute overlap, deletion reconciliation, and a fresh read at question time for every candidate. No Atlassian webhooks yet. | A brand-new page can take up to 5 minutes to become searchable. | Edits to known documents are served fresh at question time (read-through), well inside the brief's "minutes to about an hour". |
| **Search** | Lexical search with controlled aliases and permission-checked link hops; no embeddings. | Weaker on loose paraphrases. | Predictable, explainable ranking with no hidden-document statistics; a hidden document can never push a visible one out of the results. |
| **Audit** | One hash-chained row per decision, sealed text, two write-once checkpoint stores; no checkpoint means no answer. Each permission phase writes its rows in one transaction. | Storage grows with every candidate considered (thousands per broad question at scale). | Complete and tamper-evident beats compact. Batching cut question p95 from 11.9 s to 1.3 s on 30,726 documents (synthetic) without dropping a row. |
| **Scale evidence** | 30,726-document synthetic estate through the real connectors against an in-process fake site; live proof on a small seeded Atlassian site. | Neither is a real 12,000-page production estate with real API rate limits. | Honest, reproducible numbers, each labelled live, fixture or synthetic. |
| **Slack and Drive** | Real API adapters, tested against mocked services; simulated in the demo. | Not proven against real workspaces. | Time: Confluence and Jira were proven live first. Same connector contract and tests apply. |
