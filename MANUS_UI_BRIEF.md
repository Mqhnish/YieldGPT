# Manus UI redesign brief

## Assignment

Redesign the user interface for **YieldGPT**, a permission-aware enterprise knowledge assistant. Work only on branch `ui/manus-redesign`, which starts from PR #4's head commit `7914cb30c49ae7a590ccdcfc9c7c132800c43f2d`.

The application answers questions using Confluence, Jira, Slack, and Google Drive. It must never reveal a resource, title, citation, passage, or partial answer that the current user is not allowed to access.

## Repository and application structure

The production application is under `internal-brain/`.

The frontend is deliberately dependency-free:

- `internal-brain/app/static/index.html` — employee question-and-answer interface
- `internal-brain/app/static/styles.css` — shared employee interface styles
- `internal-brain/app/static/app.js` — authentication, questions, citations, evidence, history, and safe rendering
- `internal-brain/app/static/console.html` — administrative/demo console
- `internal-brain/app/static/compliance.html` — compliance and audit interface
- `internal-brain/app/main.py` and `internal-brain/app/server.py` — FastAPI routes and static-file serving
- `internal-brain/tests/browser/employee-ui.mjs` — browser-level security and behavior contract
- `internal-brain/tests/browser/README.md` — browser test instructions

Do not introduce React, Vue, a build system, a package manager, a client-side router, or a replacement backend. Improve the existing HTML/CSS/JavaScript implementation in place. External CDN assets and third-party tracking scripts are prohibited.

## Product goals

Create a polished, calm enterprise interface that makes evidence and permission boundaries easy to understand.

Priorities:

1. Make asking a question the clear primary action.
2. Present answers with strong typography and readable line lengths.
3. Make inline citations and source cards easy to scan and open.
4. Make source platform, document title, reference, freshness, and evidence status visually distinct.
5. Improve loading, empty, denied-neutral, unavailable, offline, and retry states.
6. Make persona selection understandable without implying that demo identities are production authentication.
7. Give the administration and compliance pages the same design system as the employee interface.
8. Support 390px mobile screens through wide desktop screens without horizontal overflow.
9. Meet WCAG 2.2 AA contrast, keyboard navigation, focus visibility, target size, and reduced-motion expectations.
10. Preserve the product's restrained, trustworthy tone. Avoid generic AI gradients, excessive glass effects, decorative dashboards, and fake metrics.

## Required information architecture

### Employee interface

Keep these areas:

- Workspace identity and navigation
- Sign-in/account controls
- Primary question composer
- Suggested questions
- In-progress state with cancellation
- Answer with inline citation controls
- Evidence/source list
- Source-evidence dialog
- Previous-question dialog
- Source and generation-mode disclosure
- Link to administration only when the authenticated user has the relevant right

The neutral denied/no-match experience must not disclose that a restricted document exists.

### Administration interface

Unify the visual language of `console.html` with the employee interface while retaining:

- Persona sign-in
- Question testing
- Demo controls, visible only to admins
- Sync controls and operational status
- Audit access appropriate to the user's rights

### Compliance interface

Unify `compliance.html` with the same design system while preserving role-based views and pseudonym handling.

## API contract: do not change

The existing frontend consumes these routes:

- `POST /api/login`
- `GET /api/session`
- `POST /api/ask`
- `GET /api/evidence/{query_id}/{ref}`
- `GET /api/history`
- `POST /api/history/{query_id}/replay`
- `GET /api/health`
- `GET /api/health/detail`
- `GET /api/freshness`
- `GET /api/sync/state`
- `GET /api/sync/changes`
- `POST /api/sync/poll`
- `POST /api/audit/query`
- `GET /api/audit/events`
- `GET /api/audit/verify`
- `POST /api/compliance/requests`
- `POST /api/audit/pseudonym`
- `POST /api/sim`

Do not rename routes, change request or response shapes, weaken authorization, add browser persistence for tokens or answers, or expose backend errors.

## Security invariants

These requirements are release blockers:

- Render all answer, title, passage, identity, and error data as inert text. Do not use `innerHTML` with untrusted values.
- Permit only validated HTTPS source links.
- Keep tokens and answer content out of `localStorage`, `sessionStorage`, URLs, logs, and analytics.
- Clear the question, answer, evidence, history, and in-flight requests when identities change.
- Prevent a delayed response from a previous identity from rendering after an account switch.
- Do not show restricted citations or metadata.
- Preserve private/no-store API behavior.
- Never add Atlassian credentials, account IDs, `.env` contents, `accounts.json`, `seed_manifest.json`, or `expectations.json` to the frontend or repository.
- Do not change connector, authorization, audit-chain, or live-check code as part of this redesign.

## Existing browser-test selectors

The browser checks depend on these identifiers and classes. Preserve them, or update the tests in the same commit without reducing their assertions:

- `#account-button`, `#mobile-account`, `#login-dialog`
- `[data-persona]`, `#demo-login-button`
- `#identity-name`, `#source-mode-label`, `#console-link`
- `#question`, `#question-form`, `#ask-button`
- `#working-state`, `#answer-section`, `#answer-body`
- `.inline-citation`, `.source-card`
- `#evidence-dialog`, `#evidence-content`, `.evidence-passage`, `.evidence-link`
- `#dialog-logout`

## Visual direction

Use a compact design system defined with CSS custom properties:

- Neutral warm background and high-contrast ink
- One restrained primary accent
- Source-specific accents used only for identification
- A clear type scale and 4/8px spacing rhythm
- Consistent buttons, inputs, cards, dialogs, badges, alerts, skeletons, and focus rings
- Subtle motion that is disabled by `prefers-reduced-motion`
- Platform labels must include text or accessible names; color alone is insufficient

Favor editorial clarity over density. Answers and evidence are the product. Operational detail belongs in the administration views.

## Work sequence

1. Read this brief and inspect all listed frontend and test files.
2. Run the current application and capture baseline desktop and 390px mobile screenshots.
3. Write a short design plan in the PR description before changing code.
4. Implement the shared design tokens and employee interface first.
5. Verify sign-in, asking, loading/cancel, citations, evidence, history, identity switching, errors, and mobile layout.
6. Apply the established system to administration and compliance views.
7. Run the Python suite and the browser checks.
8. Review the final diff for accidental backend, credential, API-contract, or authorization changes.
9. Add final screenshots and exact validation results to the PR description.

## Validation

From `internal-brain/`:

```bash
python -m pytest -q
```

With the local demo application running:

```bash
node tests/browser/employee-ui.mjs
```

The existing browser checks must continue to prove:

- Correct identity and mode display
- Privileged navigation hidden from ordinary employees
- Clickable citations and HTTPS evidence
- Evidence dialog closes with Escape
- Account switches clear prior content
- Restricted queries expose no source metadata
- Untrusted HTML remains inert
- `javascript:` links are omitted
- Delayed prior-user responses cannot render
- Mobile has no horizontal overflow
- Tokens and answers are not persisted in browser storage
- No unhandled browser errors

## Definition of done

The work is complete only when:

- All three interfaces share a coherent, responsive design system.
- Existing functionality and API behavior are preserved.
- Security and permission behavior is unchanged.
- Python and browser checks pass.
- No secrets or live data are committed.
- The PR contains before/after desktop and mobile screenshots plus validation results.
