# Submission media package

## Listing copy

**Title:** YieldGPT

**Short blurb:** Permission-safe answers across every workplace source.

**Cover:** `docs/media/yieldgpt-cover-380x216.png`

The cover was generated for this project with OpenAI image generation, then resized to the required 380 by 216 pixels. It contains no third-party logos.

## Six-minute demo script

### 0:00 to 0:30 | The problem

Show a fast sequence of a Slack thread, Jira issue, Confluence page, and repository file. Say:

> A team should not need four searches and a meeting to answer one operational question. YieldGPT connects workplace knowledge, keeps source permissions intact, and shows the evidence behind every answer.

Open the employee interface and identify the question box, persona selector, source status, and evidence area.

### 0:30 to 1:10 | How trust works

Use one slide or architecture screen. Explain the flow in plain language: retrieve authorized sources, rank evidence, apply freshness and conflict checks, generate through Hunyuan, then return citations and an audit trail.

State the run mode visible in the demo. If a connector is using fixtures, label it as fixture mode on screen. Do not imply that a fixture result came from a live service.

### 1:10 to 2:05 | Cross-source answer

Ask the prepared migration-status question as an employee. Show the answer drawing from the available Slack, Jira, Confluence, and repository evidence. Open at least two citations. Point out:

- Evidence appears beside the claim it supports.
- Conflicting or stale material is called out.
- The activity is available to the audit view.

### 2:05 to 2:50 | Freshness after a missed event

Run the documented missed-webhook scenario. Show the stale state, trigger the permitted repair path, and rerun the question. Compare the before and after evidence timestamps. Use the measured timings from the run report. If the live scenario has not run, show the fixture scenario and label it clearly.

### 2:50 to 3:35 | Permission-safe refusal

Switch to the contractor or restricted persona. Ask the prepared payroll or security-level question. Show the neutral no-answer response without confirming that a restricted document or issue exists. Explain that retrieval is filtered before generation and that denied identifiers do not reach the model context.

### 3:35 to 4:20 | Live revocation

Use the prepared revocation scenario. Show a user who can initially access an answer, revoke the relevant permission, refresh the source state, and ask again. The expected result is a neutral no-answer with no leaked title, snippet, or identifier. Report only the measured revocation time from the captured run.

### 4:20 to 5:00 | Audit and operations

Open the admin audit view. Filter to one request and show persona, sources consulted, policy outcome, citations, latency, token use, and cost where available. Export or inspect the audit record without exposing secrets or personal data.

### 5:00 to 5:35 | Evaluation evidence

Show the frozen 160-question trial set, the 40-case recommended live subset, and the two-reviewer scoring workflow. Present fixture, live, and human-reviewed numbers in separate groups. If the human review or live run is incomplete, say that it is pending.

### 5:35 to 6:00 | Close

Return to the employee interface. Say:

> YieldGPT gives employees one place to ask, evidence they can inspect, and answers that respect the permissions they already have. It reduces search time without weakening the controls teams rely on.

End on the cover image and repository link.

## Capture checklist

- Record at 1080p or higher with browser zoom and text sized for judges.
- Keep the fixture or live mode visible during every scenario.
- Use prepared demo accounts and synthetic data. Hide tokens, email addresses, and personal information.
- Capture the exact commit SHA and report filenames used in the recording.
- Include a CodeBuddy development screenshot if the submission form requires proof of tool use.
- Verify the cover is exactly 380 by 216 pixels and remains legible at thumbnail size.
- Keep the final video between five and eight minutes.
- Do not state that live Slack, Atlassian, Hunyuan, or human evaluation passed until the retained evidence supports that claim.

