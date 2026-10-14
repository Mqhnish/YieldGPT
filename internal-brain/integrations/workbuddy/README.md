# YieldGPT in WorkBuddy and CodeBuddy

`yieldgpt_mcp_server.py` lets a WorkBuddy agent ask YieldGPT questions in a normal WorkBuddy
conversation. It is a WorkBuddy connector (an MCP server over stdio), one file, Python standard
library only, so no `pip install` is needed.

Tools it gives the WorkBuddy agent:

| Tool | What it does |
|---|---|
| `yieldgpt_ask(question)` | Asks YieldGPT. Returns the grounded answer, numbered sources and a `query_id` |
| `yieldgpt_evidence(query_id, ref)` | Opens the passages behind one citation, after YieldGPT re-checks access |

**Permissions do not change.** The connector signs in as the one persona set in its config; the
agent cannot choose another user. Every question goes through `app.server:app` with all native
permission checks, the audit trail and checkpoint-before-release, exactly like the web UI. The
connector itself has no source access. It refuses plain `http://` to anything but localhost, so a
password never crosses a network unencrypted.

## Set up (macOS)

1. Start YieldGPT locally (from `internal-brain/`):
   `python -m uvicorn app.server:app --host 127.0.0.1 --port 8000 --workers 1`
2. Find your Python: `which python3`. Note the absolute path.
3. Create or edit `~/.workbuddy/mcp.json` and add the entry from
   [`mcp.json.example`](mcp.json.example). Replace the two absolute paths with yours. Keep
   `YIELDGPT_URL` at `http://127.0.0.1:8000` for a local demo, or the `https://` live URL later.
4. Quit and reopen WorkBuddy.
5. In the WorkBuddy sidebar open **专家·技能·连接器 (Experts · Skills · Connectors)** >
   **连接器 (Connectors)** > **MCP 服务管理 (MCP Server Management)** and switch **yieldgpt** on.
6. In a conversation ask: "What tools do you have?" You should see `yieldgpt_ask` and
   `yieldgpt_evidence`.
7. Then ask, for example: "Use YieldGPT: what's the status of the database migration project and
   were there any blockers raised in Slack last week?" and "Open source S1."

**CodeBuddy** (the Tencent IDE) reads the same entry from `~/.codebuddy/mcp.json`: add the same
`"yieldgpt"` block there, restart CodeBuddy, check that **yieldgpt** is enabled in its MCP settings,
and ask in an agent chat ("Use YieldGPT: ...").

Windows: use the absolute path of `python.exe` and double backslashes in the JSON paths, and save
`mcp.json` as UTF-8 without a BOM.

## Screenshots for the submission (CodeBuddy / WorkBuddy requirement)

Take each screenshot in WorkBuddy, with the conversation visible:
1. The tool list showing `yieldgpt_ask` and `yieldgpt_evidence`.
2. A cited answer as **jdoe** (database migration question above).
3. The same restricted question asked as **kim** and as **asha** ("Show me the Q3 breach incident
   report"): kim gets no sources, asha gets the report. Change `YIELDGPT_USERNAME`, restart
   WorkBuddy, ask again.

## Check it without WorkBuddy

```bash
printf '%s\n' '{"jsonrpc":"2.0","id":1,"method":"initialize","params":{}}' \
  '{"jsonrpc":"2.0","id":2,"method":"tools/call","params":{"name":"yieldgpt_ask","arguments":{"question":"database migration status"}}}' \
  | YIELDGPT_USERNAME=jdoe YIELDGPT_PASSWORD=demo python3 integrations/workbuddy/yieldgpt_mcp_server.py
```

Tests: `python -m pytest -q tests/test_member3_workbuddy.py` (starts a real local server).
