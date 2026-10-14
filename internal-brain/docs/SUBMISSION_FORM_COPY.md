# YieldGPT submission form handoff

Prepared for Imaad on 15 October 2026. Copy the fields below into the submission form. Do not mark the CodeBuddy/WorkBuddy proof complete until the screenshots described below have been captured.

## Title

YieldGPT

## Short blurb

Permission-safe answers across every workplace source.

## Project description

YieldGPT is a permission-aware workplace knowledge assistant for teams whose decisions are spread across Confluence, Jira, Slack, and Google Drive. An employee asks one natural-language question and receives a concise answer with numbered evidence they can inspect.

The user's prompt drives the answer-generation pipeline: YieldGPT identifies the question's subject and time scope, retrieves relevant material from the connected sources, and checks each candidate against the requesting person's source-native permissions before its text may enter the answer context. It ranks the authorized evidence, handles stale or conflicting material, builds a cited answer, records the decision in a tamper-evident audit trail, and rechecks access whenever a citation is opened. Denied content is excluded before answer construction, so a restricted item and a nonexistent item produce the same neutral response.

This submission uses deterministic extractive answer generation. Its answers are assembled word for word from passages the user may access, with every line cited. An OpenAI-compatible Hunyuan adapter is implemented and tested, but no live model credential is configured for the submitted run. Confluence and Jira have been verified on a real Atlassian Cloud site; Slack and Drive remain clearly labelled as simulated.

The business value is faster, safer decision-making. Employees spend less time repeating searches across separate tools, while security and compliance teams retain the permissions, revocation behavior, evidence links, and audit records they need. Live Atlassian validation recorded 84 of 84 permission decisions, 14 of 14 brief scenarios, and 21 of 21 lifecycle steps passing.

## Submission assets

- Cover image: [`docs/media/yieldgpt-cover-380x216.png`](media/yieldgpt-cover-380x216.png) — 380 by 216 pixels.
- Demo script: [`docs/VIDEO_SCRIPT.md`](VIDEO_SCRIPT.md) — target length 7 minutes.
- Pitch deck source: [`docs/deck/index.html`](deck/index.html).
- Pitch deck PDF: [`docs/deck/yieldgpt-deck.pdf`](deck/yieldgpt-deck.pdf).
- WorkBuddy/CodeBuddy setup: [`integrations/workbuddy/README.md`](../integrations/workbuddy/README.md).

## Imaad's CodeBuddy/WorkBuddy proof

Capture real application screens; do not create or edit a mock screenshot.

1. Start YieldGPT and enable the merged `yieldgpt` MCP connector in WorkBuddy or CodeBuddy.
2. Capture the tool list showing `yieldgpt_ask` and `yieldgpt_evidence`.
3. As `jdoe`, ask:

   > Use YieldGPT: what's the status of the database migration project and were there any blockers raised in Slack last week?

4. Ask `Open source S1.` Capture the cited answer and opened evidence in the same conversation.
5. For the permission comparison, ask `Show me the Q3 breach incident report` once as `kim` and once as `asha`. Capture Kim receiving no sources and Asha receiving the authorized report.
6. Keep WorkBuddy/CodeBuddy branding, the prompt, response, and tool call visible. Hide tokens, email addresses, account IDs, and site URLs.

Suggested filenames:

- `docs/media/imaad-workbuddy-tools.png`
- `docs/media/imaad-workbuddy-cited-answer.png`
- `docs/media/imaad-workbuddy-permission-check.png`

## Imaad's 10-second video reflection

Use this after completing the real WorkBuddy/CodeBuddy session:

> I used WorkBuddy to test YieldGPT's retrieval, grounding, and evidence flow as a real conversation. My tip is to give the coding agent one permission boundary and one expected result at a time, then make it show the citation so the behavior is easy to verify.

## Completion status

- [x] Merge PR #21.
- [x] Merge PR #17 after PR #21.
- [x] Keep the submission in extractive mode because no live model credential is configured.
- [x] Prepare title, short blurb, project description, and asset paths.
- [ ] Capture Imaad's real CodeBuddy/WorkBuddy screenshots.
- [ ] Add the screenshot files under `docs/media/`.
- [ ] Upload the cover, screenshots, description, and required team media to the submission form.
- [ ] Record the shared video and replace the reflection placeholders for all three teammates with statements that match their real sessions.
