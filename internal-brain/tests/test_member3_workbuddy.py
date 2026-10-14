"""Member 3: the WorkBuddy connector (integrations/workbuddy/yieldgpt_mcp_server.py).

Runs the connector exactly as WorkBuddy does (a subprocess speaking JSON-RPC on stdio)
against a real local uvicorn app.server:app, so every answer passes the same permission
checks, audit and checkpoint-before-release as the web UI.
"""
import importlib.util
import json
import os
import socket
import subprocess
import sys
import time
from pathlib import Path

import httpx
import pytest

ROOT = Path(__file__).resolve().parents[1]
SCRIPT = ROOT / "integrations" / "workbuddy" / "yieldgpt_mcp_server.py"
spec = importlib.util.spec_from_file_location("yieldgpt_mcp_server", SCRIPT)
mcp = importlib.util.module_from_spec(spec)
spec.loader.exec_module(mcp)


@pytest.fixture(scope="module")
def server(tmp_path_factory):
    tmp = tmp_path_factory.mktemp("wb")
    with socket.socket() as s:
        s.bind(("127.0.0.1", 0))
        port = s.getsockname()[1]
    env = {**os.environ, "IB_DATA_DIR": str(tmp), "IB_AUDIT_DB": str(tmp / "audit.db"),
           "IB_ANCHOR_PATH": str(tmp / "anchors.jsonl"), "IB_ENV_FILE": str(tmp / ".env"), "IB_LLM_PROVIDER": "stub"}
    env = {k: v for k, v in env.items() if not k.startswith("IB_CHECKPOINT_")}
    proc = subprocess.Popen([sys.executable, "-m", "uvicorn", "app.server:app", "--port", str(port),
                             "--log-level", "warning"], cwd=ROOT, env=env)
    base = f"http://127.0.0.1:{port}"
    try:
        for _ in range(150):
            try:
                if httpx.get(base + "/api/health", timeout=1).status_code == 200:
                    break
            except httpx.HTTPError:
                time.sleep(0.1)
        yield base
    finally:
        proc.terminate()
        proc.wait(timeout=20)


def connector(base, user, *messages, password="demo"):
    """Run the connector as WorkBuddy would and return its replies by id."""
    env = {**os.environ, "YIELDGPT_URL": base, "YIELDGPT_USERNAME": user, "YIELDGPT_PASSWORD": password}
    lines = "".join(json.dumps(m) + "\n" for m in messages)
    out = subprocess.run([sys.executable, str(SCRIPT)], input=lines, capture_output=True, text=True, env=env,
                         timeout=60).stdout
    replies = [json.loads(line) for line in out.splitlines()]
    assert all(r["jsonrpc"] == "2.0" for r in replies)
    return {r["id"]: r for r in replies}


def call(i, name, **args):
    return {"jsonrpc": "2.0", "id": i, "method": "tools/call", "params": {"name": name, "arguments": args}}


def text(reply):
    return reply["result"]["content"][0]["text"]


MIGRATION = "What's the status of the database migration project?"


def test_handshake_and_tool_list(server):
    r = connector(server, "jdoe",
                  {"jsonrpc": "2.0", "id": 1, "method": "initialize", "params": {}},
                  {"jsonrpc": "2.0", "method": "notifications/initialized"},
                  {"jsonrpc": "2.0", "id": 2, "method": "tools/list"},
                  {"jsonrpc": "2.0", "id": 3, "method": "no/such"})
    assert set(r) == {1, 2, 3}                                   # the notification got no reply
    assert r[1]["result"]["serverInfo"]["name"] == "yieldgpt"
    tools = {t["name"]: t for t in r[2]["result"]["tools"]}
    assert set(tools) == {"yieldgpt_ask", "yieldgpt_evidence"}
    assert "username" not in json.dumps(tools)                  # the agent cannot choose who it asks as
    assert r[3]["error"]["code"] == -32601


def test_ask_returns_grounded_answer_with_sources_and_preview(server):
    r = connector(server, "jdoe", call(1, "yieldgpt_ask", question=MIGRATION))
    answer = text(r[1])
    assert not r[1]["result"]["isError"] and "Sources:" in answer and "[S1]" in answer
    qid = answer.split("query_id: ")[1].split()[0]
    # A new connector process signs in again; the evidence cache is per user, not per token.
    r = connector(server, "jdoe", call(2, "yieldgpt_evidence", query_id=qid, ref="S1"))
    assert not r[2]["result"]["isError"] and text(r[2]).startswith("[S1]")


def test_permissions_follow_the_configured_persona(server):
    q = "Show me the Q3 breach incident report"
    asha = text(connector(server, "asha", call(1, "yieldgpt_ask", question=q))[1])
    kim = text(connector(server, "kim", call(1, "yieldgpt_ask", question=q))[1])
    assert "Sources:" in asha and "Sources:" not in kim


def test_another_users_citation_is_not_available(server):
    answer = text(connector(server, "jdoe", call(1, "yieldgpt_ask", question=MIGRATION))[1])
    qid = answer.split("query_id: ")[1].split()[0]
    r = connector(server, "kim", call(1, "yieldgpt_evidence", query_id=qid, ref="S1"))
    assert r[1]["result"]["isError"] and "not available" in text(r[1])


def test_bad_password_is_a_tool_error_without_the_password(server):
    r = connector(server, "jdoe", call(1, "yieldgpt_ask", question=MIGRATION), password="wrong-pass-123")
    assert r[1]["result"]["isError"] and "sign-in failed" in text(r[1]) and "wrong-pass-123" not in text(r[1])


def test_expired_token_signs_in_again(server):
    client = mcp.YieldGPT(server, "jdoe", "demo")
    client.token = "expired"
    assert "Sources:" in mcp.run_tool(client, "yieldgpt_ask", {"question": MIGRATION})


def test_unreachable_server_is_a_clear_tool_error():
    client = mcp.YieldGPT("http://127.0.0.1:9", "jdoe", "demo", timeout=2)
    with pytest.raises(mcp.ToolError, match="Cannot reach YieldGPT"):
        mcp.run_tool(client, "yieldgpt_ask", {"question": "hi"})


@pytest.mark.parametrize("url, expected", [
    ("http://127.0.0.1:8000", "http://127.0.0.1:8000"),
    ("http://localhost:8000/", "http://localhost:8000"),
    ("http://[::1]:8000", "http://[::1]:8000"),
    ("https://yieldgpt.example.com/", "https://yieldgpt.example.com"),
])
def test_base_url_accepted(url, expected):
    assert mcp.check_base_url(url) == expected


@pytest.mark.parametrize("url", [
    "http://yieldgpt.example.com",          # password would cross the network in clear text
    "http://127.0.0.1.attacker.example",    # looks local, is not
    "ftp://127.0.0.1",
    "https://",
    "127.0.0.1:8000",
])
def test_base_url_rejected(url):
    with pytest.raises(ValueError):
        mcp.check_base_url(url)
