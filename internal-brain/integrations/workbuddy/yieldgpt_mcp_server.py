#!/usr/bin/env python3
"""YieldGPT connector for WorkBuddy: an MCP server over stdio, Python standard library only.

WorkBuddy starts this script from ~/.workbuddy/mcp.json and exposes two tools to its agent:
  yieldgpt_ask(question)             ask YieldGPT; returns the grounded answer and its sources
  yieldgpt_evidence(query_id, ref)   open one cited source (YieldGPT re-checks access first)

Identity is fixed by the connector's configuration (YIELDGPT_USERNAME / YIELDGPT_PASSWORD),
never by tool arguments, so the WorkBuddy agent cannot pick who it asks as. Every question
goes through app.server:app, which runs every native permission check, audits it and
checkpoints it before release, exactly as for the web UI. This script holds no source access.

Environment:
  YIELDGPT_URL       default http://127.0.0.1:8000 (HTTPS required unless localhost)
  YIELDGPT_USERNAME  demo persona, e.g. jdoe
  YIELDGPT_PASSWORD  demo password
  YIELDGPT_TIMEOUT   seconds per request, default 60

Protocol: newline-delimited JSON-RPC 2.0 on stdin/stdout. Diagnostics go to stderr only.
"""
import json
import os
import sys
import urllib.error
import urllib.parse
import urllib.request

PROTOCOL_VERSION = "2024-11-05"
SERVER_INFO = {"name": "yieldgpt", "version": "1.0.0"}
LOCAL_HOSTS = {"localhost", "127.0.0.1", "::1"}

TOOLS = [
    {"name": "yieldgpt_ask",
     "description": ("Ask YieldGPT, the company knowledge assistant, a question about Confluence, Jira, Slack "
                     "or Google Drive content. Answers only from sources this user may see right now, with "
                     "numbered citations. Returns a query_id for opening sources."),
     "inputSchema": {"type": "object", "properties": {
         "question": {"type": "string", "description": "The question, in natural language (max 2000 characters)."}},
         "required": ["question"]}},
    {"name": "yieldgpt_evidence",
     "description": ("Open the passages behind one citation of a previous yieldgpt_ask answer. YieldGPT checks "
                     "the user's access again before showing anything."),
     "inputSchema": {"type": "object", "properties": {
         "query_id": {"type": "string", "description": "query_id from the yieldgpt_ask result."},
         "ref": {"type": "string", "description": "Citation reference such as S1."}},
         "required": ["query_id", "ref"]}},
]


class ToolError(Exception):
    """A failure the WorkBuddy agent should see as a tool error. Never contains credentials."""


def check_base_url(url: str) -> str:
    """Return the normalised YieldGPT base URL, or raise ValueError if it is unsafe to send
    the persona's password to it."""
    parts = urllib.parse.urlsplit(url.strip())
    host = parts.hostname or ""
    if parts.scheme == "https" and host:
        return url.strip().rstrip("/")
    if parts.scheme == "http" and host in LOCAL_HOSTS:  # exact match: 127.0.0.1.evil.example is not local
        return url.strip().rstrip("/")
    raise ValueError(f"YIELDGPT_URL must be https://, or http:// to localhost only (got {parts.scheme or 'no'} scheme"
                     f"{', host ' + host if host else ''})")


class YieldGPT:
    def __init__(self, base_url: str, username: str, password: str, timeout: float = 60):
        if not username or not password:
            raise ValueError("Set YIELDGPT_USERNAME and YIELDGPT_PASSWORD in the connector's env block.")
        self.base, self.username, self.password, self.timeout = check_base_url(base_url), username, password, timeout
        self.token = None

    def _request(self, method, path, body=None, auth=True):
        headers = {"Content-Type": "application/json", "Accept": "application/json"}
        if auth:
            headers["Authorization"] = "Bearer " + self.token
        data = json.dumps(body).encode() if body is not None else None
        req = urllib.request.Request(self.base + path, data=data, method=method, headers=headers)
        with urllib.request.urlopen(req, timeout=self.timeout) as r:
            return json.load(r)

    def _login(self):
        try:
            self.token = self._request("POST", "/api/login", {"username": self.username, "password": self.password},
                                       auth=False)["token"]
        except urllib.error.HTTPError as e:
            raise ToolError("YieldGPT sign-in failed (demo sign-in disabled)" if e.code == 403
                            else f"YieldGPT sign-in failed (HTTP {e.code}); check the connector's username and password")

    def call(self, method, path, body=None):
        """Authenticated call; signs in on first use and once more if the token has expired."""
        for attempt in (1, 2):
            try:
                if self.token is None:
                    self._login()
                return self._request(method, path, body)
            except urllib.error.HTTPError as e:
                if e.code == 401 and attempt == 1:
                    self.token = None
                    continue
                raise ToolError(_http_message(e)) from None
            except (urllib.error.URLError, OSError) as e:  # refused, DNS, TLS, timeout (sign-in included)
                reason = getattr(e, "reason", e)
                raise ToolError(f"Cannot reach YieldGPT at {self.base} ({type(reason).__name__})") from None


def _http_message(e: urllib.error.HTTPError) -> str:
    try:
        detail = json.load(e).get("detail")
    except Exception:  # noqa: BLE001
        detail = None
    if isinstance(detail, str):  # YieldGPT's details are generic and safe to show
        return f"{detail} (HTTP {e.code})"
    return f"YieldGPT returned HTTP {e.code}"


def format_answer(r: dict) -> str:
    lines = [r.get("answer", "").strip()]
    cites = r.get("citations") or []
    if cites:
        lines += ["", "Sources:"]
        lines += [f"[{c['ref']}] {c.get('title', '')} ({c.get('platform', '')}, updated {c.get('updated_iso', '?')})"
                  f" {c.get('url', '')}".rstrip() for c in cites]
        lines += ["", f"query_id: {r['query_id']} (open a source with yieldgpt_evidence)"]
    elif r.get("status") == "no_answer":
        lines += ["", "No source this user can access answers this question."]
    return "\n".join(lines)


def format_evidence(e: dict) -> str:
    head = f"[{e['ref']}] {e.get('title', '')} ({e.get('platform', '')}, version {e.get('version', '?')}) {e.get('url', '')}"
    return "\n".join([head.rstrip(), ""] + [p["text"] for p in e.get("passages", [])])


def run_tool(client: YieldGPT, name: str, args: dict) -> str:
    if name == "yieldgpt_ask":
        question = str(args.get("question", "")).strip()
        if not question or len(question) > 2000:
            raise ToolError("question must contain 1 to 2000 characters")
        return format_answer(client.call("POST", "/api/ask", {"question": question}))
    if name == "yieldgpt_evidence":
        qid, ref = str(args.get("query_id", "")), str(args.get("ref", ""))
        if not qid or not ref:
            raise ToolError("query_id and ref are required")
        path = f"/api/evidence/{urllib.parse.quote(qid, safe='')}/{urllib.parse.quote(ref, safe='')}"
        return format_evidence(client.call("GET", path))
    raise ToolError(f"unknown tool: {name}")


def handle(msg: dict, client_factory):
    """One JSON-RPC message -> response dict, or None for notifications."""
    method, mid = msg.get("method"), msg.get("id")
    if mid is None:
        return None  # notifications (e.g. notifications/initialized) get no reply
    if method == "initialize":
        result = {"protocolVersion": PROTOCOL_VERSION, "capabilities": {"tools": {}}, "serverInfo": SERVER_INFO}
    elif method == "ping":
        result = {}
    elif method == "tools/list":
        result = {"tools": TOOLS}
    elif method == "tools/call":
        params = msg.get("params") or {}
        try:
            text, is_error = run_tool(client_factory(), params.get("name", ""), params.get("arguments") or {}), False
        except (ToolError, ValueError) as e:
            text, is_error = str(e), True
        result = {"content": [{"type": "text", "text": text}], "isError": is_error}
    else:
        return {"jsonrpc": "2.0", "id": mid, "error": {"code": -32601, "message": f"method not found: {method}"}}
    return {"jsonrpc": "2.0", "id": mid, "result": result}


def main() -> int:
    client = None

    def client_factory():  # built on first tool call, so a config problem surfaces as a tool error
        nonlocal client
        if client is None:
            client = YieldGPT(os.getenv("YIELDGPT_URL", "http://127.0.0.1:8000"), os.getenv("YIELDGPT_USERNAME", ""),
                              os.getenv("YIELDGPT_PASSWORD", ""), float(os.getenv("YIELDGPT_TIMEOUT", "60")))
        return client

    for line in sys.stdin:
        if not line.strip():
            continue
        try:
            msg = json.loads(line)
        except json.JSONDecodeError:
            resp = {"jsonrpc": "2.0", "id": None, "error": {"code": -32700, "message": "parse error"}}
        else:
            resp = handle(msg, client_factory)
        if resp is not None:
            sys.stdout.write(json.dumps(resp) + "\n")
            sys.stdout.flush()
    return 0


if __name__ == "__main__":
    sys.exit(main())
