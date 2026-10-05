"""HTTP-level behaviour of the real Atlassian connectors: fail-closed error mapping,
no credential leaks, text/link extraction. Contract behaviour is in tests/contract."""
import os

import httpx
import pytest

from app.identity import USERS
from app.sources.atlassian_client import AtlassianClient
from app.sources.base import Decision, SourceUnavailable
from app.sources.confluence_cloud import ConfluenceCloudConnector
from app.sources.jira_cloud import JiraCloudConnector
from app.sources.textconv import adf_to_text, storage_to_text

TOKEN = "ATATT3xFfGF0-super-secret-token"


def _conn(cls, handler):
    client = AtlassianClient("https://companya.atlassian.net", "bot@companya.example", TOKEN,
                             transport=httpx.MockTransport(handler))
    return cls(client)


@pytest.mark.parametrize("status", [401, 403, 429, 500, 502, 400])
@pytest.mark.parametrize("cls", [ConfluenceCloudConnector, JiraCloudConnector])
def test_http_errors_fail_closed_without_leaking_token(cls, status):
    c = _conn(cls, lambda req: httpx.Response(status, headers={"Retry-After": "30"}, json={"message": TOKEN}))
    r = c.check(USERS["asha"], "CONF-101" if cls is ConfluenceCloudConnector else "PAY-110")
    assert r.decision is Decision.UNAVAILABLE and r.reason_code == "source_error"
    assert TOKEN not in r.reason
    with pytest.raises(SourceUnavailable) as e:
        c.fetch("X-1")
    assert TOKEN not in str(e.value)


@pytest.mark.parametrize("cls", [ConfluenceCloudConnector, JiraCloudConnector])
def test_network_error_fails_closed(cls):
    def boom(req):
        raise httpx.ConnectError("dns failure")
    r = _conn(cls, boom).check(USERS["asha"], "ANY-1")
    assert r.decision is Decision.UNAVAILABLE


def test_basic_auth_is_sent_and_only_to_the_site():
    seen = []

    def handler(req):
        seen.append((req.url.host, req.headers.get("authorization", "")))
        return httpx.Response(200, json={"hasPermission": True})
    c = _conn(ConfluenceCloudConnector, handler)
    c.check(USERS["asha"], "CONF-101")
    host, auth = seen[0]
    assert host == "companya.atlassian.net" and auth.startswith("Basic ")


def test_ambiguous_permission_response_is_not_an_allow():
    c = _conn(ConfluenceCloudConnector, lambda req: httpx.Response(200, json={}))
    assert c.check(USERS["asha"], "CONF-101").decision is Decision.UNAVAILABLE


def test_storage_format_to_text_and_links():
    html = ('<h2>Runbook</h2><p>Step 1: check <strong>dashboards</strong>.</p>'
            '<ac:structured-macro ac:name="info"><ac:parameter ac:name="title">cfg</ac:parameter>'
            '<ac:rich-text-body><p>Page the lead.</p></ac:rich-text-body></ac:structured-macro>'
            '<p><a href="https://companya.atlassian.net/browse/PAY-101">PAY-101</a></p>'
            '<p><ac:link><ri:url ri:value="https://drive.google.com/file/d/DRV-1/view"/></ac:link></p>')
    text, links = storage_to_text(html)
    assert text.split("\n") == ["Runbook", "Step 1: check dashboards.", "Page the lead."]
    assert "https://companya.atlassian.net/browse/PAY-101" in links and any("DRV-1" in u for u in links)


def test_adf_to_text_and_links():
    adf = {"type": "doc", "version": 1, "content": [
        {"type": "paragraph", "content": [{"type": "text", "text": "Blocked by "},
                                          {"type": "text", "text": "this", "marks": [{"type": "link", "attrs": {"href": "https://companya.slack.com/archives/db-migration/p2001"}}]}]},
        {"type": "bulletList", "content": [{"type": "listItem", "content": [{"type": "paragraph", "content": [{"type": "text", "text": "lag 40s"}]}]}]},
        {"type": "blockCard", "attrs": {"url": "https://companya.atlassian.net/wiki/spaces/eng/pages/CONF-102"}}]}
    text, links = adf_to_text(adf)
    assert text == "Blocked by this\nlag 40s"
    assert len(links) == 2


@pytest.mark.skipif(os.environ.get("IB_ATLASSIAN_MODE", "fixture") != "fixture", reason="needs the default fixture mode")
def test_fixture_mode_is_real_http(brain):
    """The default demo runs Confluence/Jira through the HTTP connectors, not the simulator."""
    assert type(brain.connectors["confluence"]).__name__ == "ConfluenceCloudConnector"
    assert type(brain.connectors["jira"]).__name__ == "JiraCloudConnector"
