"""scripts/write_account_map.py maps persona emails to accountIds without printing either."""
import importlib
import json
import sys

import httpx
import pytest

from app import config
from app.sources import atlassian_client

USERS_ON_SITE = {"a@x.org": "557058:aaa", "b@x.org": "557058:bbb"}


def test_writes_map_and_prints_no_ids_or_emails(tmp_path, monkeypatch, capsys):
    def handler(req):
        q = req.url.params.get("query")
        hits = [{"accountId": USERS_ON_SITE[q], "accountType": "atlassian"}] if q in USERS_ON_SITE else []
        return httpx.Response(200, json=hits + [{"accountId": "app-bot", "accountType": "app"}])
    real = atlassian_client.AtlassianClient
    sys.path.insert(0, "scripts")
    mod = importlib.import_module("write_account_map")
    monkeypatch.setattr(mod, "AtlassianClient", lambda *a, **k: real(a[0], transport=httpx.MockTransport(handler)))
    for k, v in {"ATLASSIAN_SITE": "https://t.atlassian.net", "ATLASSIAN_EMAIL": "me@x.org", "ATLASSIAN_API_TOKEN": "tok"}.items():
        monkeypatch.setattr(config, k, v)
    out = tmp_path / "accounts.json"
    with pytest.raises(SystemExit) as e:
        mod.main(["jdoe=a@x.org", "ravi=b@x.org", "asha=missing@x.org"], out=str(out))
    assert e.value.code == 1                                   # asha not found
    m = json.loads(out.read_text())
    assert m["jdoe"] == {"confluence": "557058:aaa", "jira": "557058:aaa"}
    assert m["kim"] == {} and m["asha"] == {}
    printed = capsys.readouterr().out
    assert "557058" not in printed and "@x.org" not in printed


def test_account_map_drops_placeholder_ids_for_unlisted_personas():
    # Live bug: dana wasn't in accounts.json, kept "atl-557058:dana", and Atlassian rejected the
    # seeder's page restriction with HTTP 400. Unlisted personas have no Atlassian account.
    from app.identity import USERS, account_for, apply_account_map
    users = dict(USERS)
    apply_account_map({"ravi": {"confluence": "557058:r", "jira": "557058:r"}, "kim": {}}, users)
    assert account_for(users["ravi"], "jira") == "557058:r"
    for name in ("dana", "jdoe", "kim"):
        assert account_for(users[name], "confluence") is None and account_for(users[name], "jira") is None
    assert account_for(users["dana"], "slack") == account_for(USERS["dana"], "slack")   # other platforms untouched
    assert USERS["dana"] is not users["dana"]                                            # caller's dict only
