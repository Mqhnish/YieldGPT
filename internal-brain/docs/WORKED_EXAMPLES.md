# Five worked examples from the challenge brief

Generated: 2026-09-28T18:48:42.222705+00:00

Executed against fictional Company A using the offline evidence selector. All assembled context was independently checked against the current user permissions. This demonstrates application behavior, not live cloud service certification.

**11/11 scenario checks passed.**

## 1. Unified natural-language query

### Request 1 — jdoe

What's the status of the database migration project and were there any blockers raised in Slack last week?

Query: `2703cbac5c56` · Generation: `extractive`

MIG-1 [In Progress] Epic: Postgres 12 to 16 migration. [S1]
Status: 70% of tables migrated. [S1]
Cutover to Postgres 16 is planned for 20 Oct. [S1]
Cutover checklist for the database migration: freeze schema changes, verify replication lag under 1s, switch read traffic, then writes. [S2]
@ravi: Blocker: replication lag on the orders table hit 40s during dual-write, so the migration cutover is on hold until MIG-7 is fixed. [S3]
@jdoe: Could we batch the backfill overnight to cut write load? [S3]
MIG-7 [Blocked] Replication lag on orders table during dual-write. [S4]
Replication lag on the orders table reaches 40 seconds during dual-write. [S4]
Cutover cannot proceed until this is fixed. [S4]

| Reference | Source | Version |
|---|---|---|
| S1 | [jira:MIG-1](https://companya.atlassian.net/browse/MIG-1) | 1790448522.119788 |
| S2 | [gdrive:DRV-2](https://drive.google.com/file/d/DRV-2) | 1790102922.119788 |
| S3 | [slack:db-migration/2001](https://companya.slack.com/archives/db-migration/p2001) | 08f9684fac5b1ae56da65d1d3788ca1f7dec2c66c4cc28db0e22786853e650b5 |
| S4 | [jira:MIG-7](https://companya.atlassian.net/browse/MIG-7) | 1790275722.119788 |

## 2. Fresh runbook after a missed webhook

Action: Append critical failover step at the source; deliberately omit webhook and polling.

### Request 1 — ravi

What's the latest runbook for the payment-service incident?

Query: `b7268f19fcfa` · Generation: `extractive`

Step 1: Check the payments dashboard for elevated card authorisation errors. [S1]
Step 2: Inspect TLS handshake errors between payment-service and the card network gateway. [S1]
Step 3: If certificate expiry is suspected, run the cert-check job and page the payments lead. [S1]
Step 4: Post status updates in #payments-oncall every 15 minutes. [S1]
PAY-101 [Done] Root cause: payment outage (Q2). [S2]
Root cause of the Q2 payment outage: the TLS certificate for the card network gateway expired because the nightly renewal job failed silently. [S2]
Follow-up tickets created: PAY-102 and PAY-103. [S2]
Postmortem for the Q2 payment outage. [S3]
Impact: card payments failed for 47 minutes. [S3]
@ravi: PAGE: card payments failing, TLS handshake errors to the card network gateway. [S4]
@ravi: Found it: gateway certificate expired. [S4]
PAY-102 [In Progress] Alert when any certificate expires within 14 days. [S5]
Follow-up to PAY-101. [S5]
Add expiry alerting. [S5]
PAY-103 [Done] Make cert renewal job fail loudly. [S6]
Follow-up to PAY-101. [S6]
Renewal job now pages on failure. [S6]

| Reference | Source | Version |
|---|---|---|
| S1 | [confluence:CONF-101](https://companya.atlassian.net/wiki/spaces/payment-gateway/pages/CONF-101) | 1788893322.119788 |
| S2 | [jira:PAY-101](https://companya.atlassian.net/browse/PAY-101) | 1781117322.119788 |
| S3 | [gdrive:DRV-1](https://drive.google.com/file/d/DRV-1) | 1781549322.119788 |
| S4 | [slack:payments-oncall/3001](https://companya.slack.com/archives/payments-oncall/p3001) | eb7759d216e52ee037a9079fc09e4c580463e94923085843318c2eb7a4768859 |
| S5 | [jira:PAY-102](https://companya.atlassian.net/browse/PAY-102) | 1788029322.119788 |
| S6 | [jira:PAY-103](https://companya.atlassian.net/browse/PAY-103) | 1785437322.119788 |

### Request 2 — ravi

What's the latest runbook for the payment-service incident?

Query: `b07fc7a03305` · Generation: `extractive`

Step 1: Check the payments dashboard for elevated card authorisation errors. [S1]
Step 2: Inspect TLS handshake errors between payment-service and the card network gateway. [S1]
Step 3: If certificate expiry is suspected, run the cert-check job and page the payments lead. [S1]
Step 4: Post status updates in #payments-oncall every 15 minutes. [S1]
Step 5: If the certificate cannot be renewed within 10 minutes, fail over payment-service to the secondary card network gateway. [S1]
PAY-101 [Done] Root cause: payment outage (Q2). [S2]
Root cause of the Q2 payment outage: the TLS certificate for the card network gateway expired because the nightly renewal job failed silently. [S2]
Follow-up tickets created: PAY-102 and PAY-103. [S2]
Postmortem for the Q2 payment outage. [S3]
Impact: card payments failed for 47 minutes. [S3]
@ravi: PAGE: card payments failing, TLS handshake errors to the card network gateway. [S4]
@ravi: Found it: gateway certificate expired. [S4]
PAY-102 [In Progress] Alert when any certificate expires within 14 days. [S5]
Follow-up to PAY-101. [S5]
Add expiry alerting. [S5]
PAY-103 [Done] Make cert renewal job fail loudly. [S6]
Follow-up to PAY-101. [S6]
Renewal job now pages on failure. [S6]

| Reference | Source | Version |
|---|---|---|
| S1 | [confluence:CONF-101](https://companya.atlassian.net/wiki/spaces/payment-gateway/pages/CONF-101) | 1790621322.153960 |
| S2 | [jira:PAY-101](https://companya.atlassian.net/browse/PAY-101) | 1781117322.119788 |
| S3 | [gdrive:DRV-1](https://drive.google.com/file/d/DRV-1) | 1781549322.119788 |
| S4 | [slack:payments-oncall/3001](https://companya.slack.com/archives/payments-oncall/p3001) | eb7759d216e52ee037a9079fc09e4c580463e94923085843318c2eb7a4768859 |
| S5 | [jira:PAY-102](https://companya.atlassian.net/browse/PAY-102) | 1788029322.119788 |
| S6 | [jira:PAY-103](https://companya.atlassian.net/browse/PAY-103) | 1785437322.119788 |

## 3. Negative case without a metadata disclosure

### Request 1 — kim

Show me the security incident report from the Q3 breach.

Query: `82f752a62044` · Generation: `extractive`

I couldn't find information you have access to that answers this. Try rephrasing, or ask the owner of the relevant space, project or channel.

| Reference | Source | Version |
|---|---|---|
| — | No source metadata returned | — |

### Request 2 — kim

Show me the unicorn migration to Mars report.

Query: `90e9ce544bf6` · Generation: `extractive`

I couldn't find information you have access to that answers this. Try rephrasing, or ask the owner of the relevant space, project or channel.

| Reference | Source | Version |
|---|---|---|
| — | No source metadata returned | — |

## 4. Live private-channel revocation

Action: Remove Ravi from private payments-oncall; omit webhook and polling; ask again.

### Request 1 — ravi

What did payments-oncall say about the gateway certificate?

Query: `2da7cf81e0f8` · Generation: `extractive`

@ravi: PAGE: card payments failing, TLS handshake errors to the card network gateway. [S1]
@ravi: Found it: gateway certificate expired. [S1]
Step 2: Inspect TLS handshake errors between payment-service and the card network gateway. [S2]
Step 5: If the certificate cannot be renewed within 10 minutes, fail over payment-service to the secondary card network gateway. [S2]
Postmortem for the Q2 payment outage. [S3]
Root cause: expired TLS certificate on the card network gateway after the renewal job failed silently. [S3]
PAY-101 [Done] Root cause: payment outage (Q2). [S4]
Root cause of the Q2 payment outage: the TLS certificate for the card network gateway expired because the nightly renewal job failed silently. [S4]
Follow-up tickets created: PAY-102 and PAY-103. [S4]
payment-service calls the card network gateway over mutual TLS. [S5]
Certificates are renewed by a nightly job. [S5]
PAY-102 [In Progress] Alert when any certificate expires within 14 days. [S6]
Follow-up to PAY-101. [S6]
Add expiry alerting. [S6]
PAY-103 [Done] Make cert renewal job fail loudly. [S7]
Follow-up to PAY-101. [S7]
Renewal job now pages on failure. [S7]

| Reference | Source | Version |
|---|---|---|
| S1 | [slack:payments-oncall/3001](https://companya.slack.com/archives/payments-oncall/p3001) | eb7759d216e52ee037a9079fc09e4c580463e94923085843318c2eb7a4768859 |
| S2 | [confluence:CONF-101](https://companya.atlassian.net/wiki/spaces/payment-gateway/pages/CONF-101) | 1790621322.153960 |
| S3 | [gdrive:DRV-1](https://drive.google.com/file/d/DRV-1) | 1781549322.119788 |
| S4 | [jira:PAY-101](https://companya.atlassian.net/browse/PAY-101) | 1781117322.119788 |
| S5 | [confluence:CONF-106](https://companya.atlassian.net/wiki/spaces/payment-gateway/pages/CONF-106) | 1787165322.119788 |
| S6 | [jira:PAY-102](https://companya.atlassian.net/browse/PAY-102) | 1788029322.119788 |
| S7 | [jira:PAY-103](https://companya.atlassian.net/browse/PAY-103) | 1785437322.119788 |

### Request 2 — ravi

What did payments-oncall say about the gateway certificate?

Query: `06cdb40fb4f6` · Generation: `extractive`

Step 2: Inspect TLS handshake errors between payment-service and the card network gateway. [S1]
Step 5: If the certificate cannot be renewed within 10 minutes, fail over payment-service to the secondary card network gateway. [S1]
Postmortem for the Q2 payment outage. [S2]
Root cause: expired TLS certificate on the card network gateway after the renewal job failed silently. [S2]
PAY-101 [Done] Root cause: payment outage (Q2). [S3]
Root cause of the Q2 payment outage: the TLS certificate for the card network gateway expired because the nightly renewal job failed silently. [S3]
Follow-up tickets created: PAY-102 and PAY-103. [S3]
payment-service calls the card network gateway over mutual TLS. [S4]
Certificates are renewed by a nightly job. [S4]
PAY-102 [In Progress] Alert when any certificate expires within 14 days. [S5]
Follow-up to PAY-101. [S5]
Add expiry alerting. [S5]
PAY-103 [Done] Make cert renewal job fail loudly. [S6]
Follow-up to PAY-101. [S6]
Renewal job now pages on failure. [S6]

| Reference | Source | Version |
|---|---|---|
| S1 | [confluence:CONF-101](https://companya.atlassian.net/wiki/spaces/payment-gateway/pages/CONF-101) | 1790621322.153960 |
| S2 | [gdrive:DRV-1](https://drive.google.com/file/d/DRV-1) | 1781549322.119788 |
| S3 | [jira:PAY-101](https://companya.atlassian.net/browse/PAY-101) | 1781117322.119788 |
| S4 | [confluence:CONF-106](https://companya.atlassian.net/wiki/spaces/payment-gateway/pages/CONF-106) | 1787165322.119788 |
| S5 | [jira:PAY-102](https://companya.atlassian.net/browse/PAY-102) | 1788029322.119788 |
| S6 | [jira:PAY-103](https://companya.atlassian.net/browse/PAY-103) | 1785437322.119788 |

## 5. Compliance audit inquiry

Compliance viewer: `priya`

Show me everything user 'jdoe' accessed related to the 'payment-gateway' Confluence space in the last 30 days.

| Actor | Query | Time (UTC) | Decisions | Answer recorded |
|---|---|---|---:|---|
| jdoe | 82a7a37093fc | 2026-09-28T18:48:42.208452+00:00 | 25 | Yes |
| jdoe | 0cf8cf1d4755 | 2026-09-28T18:48:42.197598+00:00 | 21 | Yes |

Full questions, source decisions, context versions, timestamps and answers are preserved in the accompanying JSON report.

## Reproduce

```sh
python scripts/judging_demo.py --markdown docs/WORKED_EXAMPLES.md --json evaluation/reports/judging-scenarios.json
```

The script creates temporary audit/sync data and does not use or overwrite your running demo database. Source links point to fictional fixture locations. Source APIs, SSO, external audit protection and the real model require separate team integration.
