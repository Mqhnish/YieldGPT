# Integrated browser verification

Date: 29 September 2026. Local canonical server on 127.0.0.1:8766, fictional Company A, offline selector. Verified through the in-app browser at its existing narrow viewport using keyboard activation and visible page state.

- Engineer sign-in and MIG-1 question returned a cited answer with an explicit “No language model used” label.
- Previous questions displayed timestamps and revisit controls without stored question/answer/source text in the history entries.
- Revisit produced a new query ID and the label “checked against your current access.”
- Citation inspection after replay displayed source title, version and supporting passages.
- Switching to the contractor cleared the previous answer, source previews and question. Contractor history was empty; the engineer's entries were absent.

[Verified history screenshot](../../docs/screenshots/integrated-history.png).

Server regression tests separately exercise revoked access, fresh content after a lost webhook, expired retained question content, cross-actor replay, checkpoint outage and preview-only delivery exclusion. Browser checks are local demo evidence, not real Slack or live model verification. Existing historical screenshots and browser scripts are retained; this session did not rerun their entire older seven-group automation suite.
