# Integrated UI acceptance report

Date: 14 October 2026. Base commit: `f8cbfb25edfccf4bf89aa94d2998ccd41d3cd5cb`. Environment: local canonical FastAPI server, fixture data, demo sign-in, and headless Google Chrome. This report does not claim live Slack or live model verification.

## Automated results

- Lighthouse accessibility: **100/100**, with **0 failed scored accessibility audits**. The machine-readable report is [lighthouse-accessibility.json](lighthouse-accessibility.json).
- Product naming: the document title is `YieldGPT · Company A` and no visible legacy product name remains.
- Authentication and permissions: real demo login works; switching personas clears the prior answer and prevents contractor source access.
- Search and evidence: a real retrieval request returns citations, an evidence dialog opens, and Escape closes it.
- Keyboard: the sign-in control activates from the keyboard; the evidence dialog supports keyboard dismissal.
- Safe rendering: injected HTML remains inert and `javascript:` source links are suppressed.
- Session isolation: a delayed response from the previous persona cannot render after an account switch.
- Error recovery: a forced `/api/ask` 503 displays a safe error and the next request succeeds.
- Responsive layout: **390 px, 768 px, and 1440 px** viewports have no horizontal page overflow.
- Browser console: **0 JavaScript errors** during the acceptance run.

The repeatable browser checks live in `tests/browser/employee-ui.mjs`; run them against the canonical server as documented in `tests/browser/README.md`.

## Human evidence still required

- **U01:** record and time the final five-scenario walkthrough; the automated scenario suite is supporting evidence, not a timed judge-facing rehearsal.
- **U02:** recruit five first-time users and record task success. No user-study result is claimed yet.
- **U04:** the automated run covers the main keyboard path. Complete the manual keyboard checklist for every compliance filter and audit control before claiming 100%.
- Capture the final demo video and at least one real CodeBuddy or WorkBuddy project-chat screenshot for Imaad. These must be genuine human-session evidence.

## External-service dependencies

Live model and Slack checks remain unrun because the validation environment has no model provider credentials and no `IB_SLACK_CONFIG`. Their absence does not affect the fixture-mode UI evidence above, but it blocks live-service claims.

