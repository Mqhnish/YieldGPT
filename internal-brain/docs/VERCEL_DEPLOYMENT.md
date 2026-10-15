# Vercel demo deployment

Set the Vercel project **Root Directory** to `internal-brain`. Vercel detects
`app/server.py` as the FastAPI entrypoint and applies its native application
routing.

Set these environment variables in Vercel for Preview and Production:

- `IB_DATA_DIR`: `/tmp/yieldgpt`
- `IB_SERVERLESS`: `1`
- `IB_DEMO_MODE`: `1`
- `IB_ATLASSIAN_MODE`: `fixture`
- `IB_LLM_PROVIDER`: `stub`
- `IB_SECRET_KEY`: a long random value
- `IB_WEBHOOK_SECRET`: a different long random value
- `IB_AUDIT_PSEUDONYM_KEY`: another long random value
- `IB_AUDIT_CONTENT_KEY`: 32 random bytes, base64 encoded

Do not add live Slack, Google Drive, Jira, Confluence, or model credentials to
the public demo project.

Vercel Functions can only write to `/tmp`, and that storage is ephemeral. The
deployment therefore demonstrates the UI, synthetic personas, permission-aware
answers, and evidence flow. Audit history, sync cursors, simulated changes, and
login sessions may reset after a cold start. Use the Docker deployment with
durable storage for live connectors or compliance evidence.
