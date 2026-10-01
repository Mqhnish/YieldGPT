"""Slack contract extensions, with real HTTP code exercised through MockTransport."""
import dataclasses
import hashlib
import hmac
import json
import time

import httpx
import pytest

from app.identity import USERS, User
from app.sources.base import Decision, SourceUnavailable
from app.sources.slack import SlackConnector
from app.sources.slack_events import SlackEventReceiver, SlackEventStore
from app.sources.slack_live import SlackLiveConnector
from app.sources.world import World

TEAM = "TTEAM"
ACCOUNT = "TTEAM/UJANE"
NID = "TTEAM/CDEMO/1700000000.000001"
ROOT = "1700000000.000001"
ASKER = dataclasses.replace(USERS["jdoe"], accounts=(("slack", ACCOUNT),))


def message(ts=ROOT, text="Migration is not approved.", **kwargs):
    return {"type": "message", "user": "UJANE", "ts": ts, "text": text, **kwargs}


class FakeSlack:
    def __init__(self):
        self.calls = []
        self.identity_user = "UJANE"
        self.team = TEAM
        self.bot = False
        self.denied = False
        self.error = None
        self.reply_pages = [[message()]]
        self.history_pages = [[message()]]
        self.rate_limit = 0
        self.retry_after = "0"

    def __call__(self, req):
        self.calls.append(req)
        token = req.headers["authorization"].split()[1]
        method = req.url.path.rsplit("/", 1)[-1]
        if method == "auth.test":
            return httpx.Response(200, json={"ok": True, "team_id": self.team,
                                           "user_id": self.identity_user, **({"bot_id": "BBOT"} if self.bot else {})})
        if self.rate_limit:
            self.rate_limit -= 1
            return httpx.Response(429, headers={"Retry-After": self.retry_after})
        if self.error:
            return httpx.Response(200, json={"ok": False, "error": self.error})
        if self.denied and token == "xoxp-asker":
            return httpx.Response(200, json={"ok": False, "error": "channel_not_found"})
        pages = self.history_pages if method == "conversations.history" else self.reply_pages
        page = int(req.url.params.get("cursor", "0"))
        return httpx.Response(200, json={"ok": True, "messages": pages[page],
            "response_metadata": {"next_cursor": str(page + 1) if page + 1 < len(pages) else ""},
            "has_more": page + 1 < len(pages)})


def adapter(tmp_path, fake=None, resolver=None, **kwargs):
    fake = fake or FakeSlack()
    store = SlackEventStore(tmp_path / "events.db")
    connector = SlackLiveConnector(TEAM, ["CDEMO", "DDEMO"], "xoxp-ingestion",
        resolver or (lambda account: "xoxp-asker" if account == ACCOUNT else None),
        store, client=httpx.Client(transport=httpx.MockTransport(fake)), sleep=lambda _: None, **kwargs)
    return connector, fake


def test_simulated_account_mapping_not_corporate_username():
    c = SlackConnector(World())
    renamed = dataclasses.replace(USERS["jdoe"], username="renamed")
    assert c.check(renamed, "T0COMPANYA/db-migration/2001").allowed
    impersonator = dataclasses.replace(USERS["kim"], username="jdoe")
    assert not c.check(impersonator, "T0COMPANYA/db-migration/2001").allowed


def test_simulated_dm_retention_and_public_scope():
    world = World()
    now = time.time()
    world.channels["dm-demo"] = dict(workspace="companya", private=True, is_im=True,
        member_accounts={"T0COMPANYA/U0JDOE", "T0COMPANYA/U0ASHA"}, retention_days=1)
    world.threads["dm-demo/1"] = dict(ts=now, msgs=[("asha", now - 200000, "Expired secret"), ("jdoe", now, "Visible reply")])
    c = SlackConnector(world)
    assert c.check(USERS["jdoe"], "dm-demo/1").allowed
    assert not c.check(USERS["ravi"], "dm-demo/1").allowed
    assert "Expired" not in c.fetch("dm-demo/1").text
    world.threads["dm-demo/1"]["msgs"].pop()
    assert c.fetch("dm-demo/1") is None
    assert not c.check(USERS["jdoe"], "dm-demo/1").allowed
    world.channels["db-migration"].update(public_read=True, workspace_accounts={"T0COMPANYA/U0PRIYA"})
    assert c.check(USERS["priya"], "T0COMPANYA/db-migration/2001").allowed
    assert not c.check(USERS["kim"], "T0COMPANYA/db-migration/2001").allowed


def test_simulated_edit_delete_changes_version_and_feed():
    world = World()
    c = SlackConnector(world)
    nid = "T0COMPANYA/db-migration/2001"
    before = c.fetch(nid)
    cursor = c.start_cursor()
    world.slack_edit_message(nid, 0, "Migration is not approved", push=False)
    edited = c.fetch(nid)
    assert edited.version != before.version and "not approved" in edited.text
    world.slack_delete_message(nid, 1, push=False)
    assert c.fetch(nid).version != edited.version
    assert len(c.changes_since(cursor).changes) == 2


def test_live_user_token_reads_not_ingestion_content(tmp_path):
    c, fake = adapter(tmp_path)
    assert c.fetch(NID)
    fake.denied = True
    assert c.check(ASKER, NID).decision is Decision.DENIED
    assert c.read_authorized(ASKER, NID) is None
    assert c.fetch(NID)  # bot/service access proves nothing about asker
    assert all("token" not in req.url.params for req in fake.calls)


@pytest.mark.parametrize("change", ["wrong_user", "wrong_team", "bot", "missing_credential"])
def test_live_wrong_identity_fails_closed(tmp_path, change):
    c, fake = adapter(tmp_path, resolver=(lambda _: None) if change == "missing_credential" else None)
    if change == "wrong_user": fake.identity_user = "UOTHER"
    if change == "wrong_team": fake.team = "TOTHER"
    if change == "bot": fake.bot = True
    assert c.check(ASKER, NID).decision is Decision.UNAVAILABLE
    assert not any(req.url.path.endswith("conversations.replies") for req in fake.calls)


def test_live_workspace_mismatch_and_no_account_never_hit_api(tmp_path):
    c, fake = adapter(tmp_path)
    foreign = dataclasses.replace(ASKER, accounts=(("slack", "TOTHER/UJANE"),))
    assert not c.check(foreign, NID).allowed
    assert not c.check(dataclasses.replace(ASKER, accounts=()), NID).allowed
    assert not c.check(ASKER, "TOTHER/CDEMO/1700000000.000001").allowed
    assert fake.calls == []


def test_live_pagination_deduplicates_thread_and_version_tracks_edits(tmp_path):
    c, fake = adapter(tmp_path)
    reply = message("1700000001.000001", "Review is tomorrow", thread_ts=ROOT)
    fake.reply_pages = [[message(), reply], [reply, message("1700000002.000001", "Still blocked", thread_ts=ROOT)]]
    doc = c.read_authorized(ASKER, NID)
    assert doc.text.count("Review is tomorrow") == 1
    assert "Still blocked" in doc.text and doc.native_id.startswith(TEAM + "/")
    fake.reply_pages[0][0]["text"] = "Migration is approved."
    edited = c.read_authorized(ASKER, NID)
    assert doc.version != edited.version
    fake.reply_pages = [[message()]]
    assert c.read_authorized(ASKER, NID).version != edited.version


def test_live_dm_and_public_access_delegates_to_slack(tmp_path):
    c, fake = adapter(tmp_path)
    # No membership heuristic: successful delegated read is authoritative for
    # public channels and DMs alike. Slack determines what this token can see.
    assert c.check(ASKER, NID).allowed
    assert c.check(ASKER, NID.replace("CDEMO", "DDEMO")).allowed
    fake.denied = True
    assert not c.check(ASKER, NID.replace("CDEMO", "DDEMO")).allowed


def test_live_pagination_budget_fails_closed(tmp_path):
    c, fake = adapter(tmp_path, max_pages=1)
    fake.reply_pages = [[message()], [message("1700000001.000001", "Unseen")]]
    assert c.check(ASKER, NID).decision is Decision.UNAVAILABLE


def test_live_rate_limit_is_bounded_and_no_retry_inside_check(tmp_path):
    c, fake = adapter(tmp_path)
    fake.rate_limit = 1
    assert c.check(ASKER, NID).decision is Decision.UNAVAILABLE
    assert len([r for r in fake.calls if r.url.path.endswith("conversations.replies")]) == 1
    fake.rate_limit = 1
    assert c.fetch(NID) is not None
    fake.rate_limit, fake.retry_after = 5, "60"
    with pytest.raises(SourceUnavailable, match="ratelimited"):
        c.fetch(NID)
    assert fake.rate_limit == 4


def test_live_safe_errors_never_contain_secret(tmp_path):
    c, fake = adapter(tmp_path)
    fake.error = "xoxp-sensitive-token-should-never-appear"
    result = c.check(ASKER, NID)
    assert result.decision is Decision.UNAVAILABLE
    assert "sensitive" not in result.reason
    def boom(_):
        raise RuntimeError("xoxp-sensitive-token-should-never-appear")
    c, _ = adapter(tmp_path, resolver=boom)
    assert "sensitive" not in c.check(ASKER, NID).reason


def test_live_crawl_paginates_and_survives_restart(tmp_path):
    c, fake = adapter(tmp_path)
    c.channels = ("CDEMO",)
    fake.history_pages = [[message(), message()], [message("1700000001.000001", "Second")]]
    ids, token = c.list_page(None, 1)
    assert ids == [NID] and token
    restarted, _ = adapter(tmp_path)
    ids2, token2 = restarted.list_page(token, 1)
    assert ids2 == ["TTEAM/CDEMO/1700000001.000001"] and token2 is None


def test_reconcile_deletions_only_after_complete_scan(tmp_path):
    c, fake = adapter(tmp_path)
    c.channels = ("CDEMO",)
    c.store.remember(NID)
    cursor = c.start_cursor()
    fake.error = "service_unavailable"
    with pytest.raises(SourceUnavailable):
        c.reconcile()
    assert c.changes_since(cursor).changes == []
    fake.error, fake.history_pages = None, [[]]
    c.reconcile()
    assert [(ch.native_id, ch.kind) for ch in c.changes_since(cursor).changes] == [(NID, "delete")]


def signed(payload, stamp=None, secret="test-signing-secret"):
    stamp = str(int(time.time()) if stamp is None else stamp)
    body = json.dumps(payload).encode()
    signature = "v0=" + hmac.new(secret.encode(), b"v0:" + stamp.encode() + b":" + body, hashlib.sha256).hexdigest()
    return body, {"X-Slack-Request-Timestamp": stamp, "X-Slack-Signature": signature}


def event(event_id="Ev1", inner=None):
    return {"type": "event_callback", "team_id": TEAM, "api_app_id": "ATEST", "event_id": event_id,
            "event_time": time.time(), "event": inner or {"type": "message", "channel": "CDEMO", **message()}}


def receiver(tmp_path):
    store = SlackEventStore(tmp_path / "events.db")
    return SlackEventReceiver(store, "test-signing-secret", TEAM, ["CDEMO"], app_id="ATEST")


def test_signed_events_deduplicate_persistently(tmp_path):
    r = receiver(tmp_path)
    body, headers = signed(event())
    assert r.receive(body, headers) == {"ok": True, "duplicate": False}
    restarted = receiver(tmp_path)
    assert restarted.receive(body, headers)["duplicate"]
    assert len(restarted.store.changes_since("0").changes) == 1


@pytest.mark.parametrize("case", ["old", "future", "bad_signature", "wrong_team", "wrong_app"])
def test_signed_events_reject_replay_or_wrong_installation(tmp_path, case):
    r = receiver(tmp_path)
    payload = event()
    if case == "wrong_team": payload["team_id"] = "TOTHER"
    if case == "wrong_app": payload["api_app_id"] = "AOTHER"
    stamp = time.time() - 301 if case == "old" else time.time() + 301 if case == "future" else time.time()
    body, headers = signed(payload, int(stamp))
    if case == "bad_signature": headers["X-Slack-Signature"] = "v0=bad"
    with pytest.raises(ValueError): r.receive(body, headers)
    assert r.store.changes_since("0").changes == []


def test_events_edits_reply_delete_root_delete_and_revocation(tmp_path):
    r = receiver(tmp_path)
    r.store.remember(NID, [ROOT, "1700000001.000001"])
    mutations = [
        {"type": "message", "channel": "CDEMO", "subtype": "message_changed", "message": message(text="Edited")},
        {"type": "message", "channel": "CDEMO", "subtype": "message_deleted", "deleted_ts": "1700000001.000001"},
        {"type": "member_left_channel", "channel": "CDEMO", "user": "UJANE"},
        {"type": "message", "channel": "CDEMO", "subtype": "message_deleted", "deleted_ts": ROOT},
    ]
    for i, mutation in enumerate(mutations):
        r.receive(*signed(event(f"Ev{i}", mutation)))
    assert [(ch.native_id, ch.kind) for ch in r.store.changes_since("0").changes] == [
        (NID, "upsert"), (NID, "upsert"), (NID, "acl"), (NID, "delete")]


def test_signed_url_challenge_and_channel_allowlist(tmp_path):
    r = receiver(tmp_path)
    assert r.receive(*signed({"type": "url_verification", "challenge": "hello"})) == {"challenge": "hello"}
    r.receive(*signed(event(inner={"type": "message", "channel": "CSECRET", **message()})))
    assert r.store.changes_since("0").changes == []


def test_message_spans_preserve_creation_time_and_exact_offsets(tmp_path):
    c, fake = adapter(tmp_path)
    fake.reply_pages = [[message(text="Old root\nSecond line"), message("1701000000.000001", "New reply", thread_ts=ROOT)]]
    doc = c.read_authorized(ASKER, NID)
    assert len(doc.message_spans) == 2
    first, second = doc.message_spans
    assert "Old root\nSecond line" in doc.text[first["start"]:first["end"]]
    assert "New reply" in doc.text[second["start"]:second["end"]]
    assert first["ts"] < second["ts"]
    fake.reply_pages[0][0]["edited"] = {"ts": "1702000000.000001"}
    edited = c.read_authorized(ASKER, NID)
    assert edited.updated_at > doc.updated_at
    assert edited.message_spans[0]["ts"] == first["ts"]
    world = World()
    sim = SlackConnector(world)
    thread = sim.fetch("T0COMPANYA/db-migration/2001")
    assert thread.message_spans[0]["ts"] == world.threads["T0COMPANYA/db-migration/2001"]["msgs"][0][1]
    for span in thread.message_spans:
        assert thread.text[span["start"]:span["end"]].startswith("@")


def test_deleted_reply_after_edit_routes_correctly_across_restart(tmp_path):
    r = receiver(tmp_path)
    reply_ts = "1700000001.000001"
    edit = {"type": "message", "channel": "CDEMO", "subtype": "message_changed",
            "message": message(reply_ts, "Edited reply", thread_ts=ROOT)}
    r.receive(*signed(event("EvEditReply", edit)))
    cursor = r.store.head()
    restarted = receiver(tmp_path)
    deleted = {"type": "message", "channel": "CDEMO", "subtype": "message_deleted", "deleted_ts": reply_ts}
    restarted.receive(*signed(event("EvDeleteReply", deleted)))
    assert [(c.native_id, c.kind) for c in restarted.store.changes_since(cursor).changes] == [(NID, "upsert")]


def test_reconcile_restart_catches_deletion_without_events(tmp_path):
    c, fake = adapter(tmp_path)
    c.channels = ("CDEMO",)
    c.list_page()
    cursor = c.start_cursor()
    restarted, new_fake = adapter(tmp_path)
    restarted.channels = ("CDEMO",)
    new_fake.history_pages = [[]]
    restarted.reconcile()
    assert [(ch.native_id, ch.kind) for ch in restarted.changes_since(cursor).changes] == [(NID, "delete")]


@pytest.mark.parametrize("corruption", [
    {"event_time": "xoxp-sensitive-value"},
    {"event_time": float("nan")},
    {"event": {"type": ["message"], "channel": "CDEMO"}},
    {"event": {"type": "message", "channel": []}},
    {"event": {"type": "message", "channel": "CDEMO", "subtype": []}},
    {"event": {"type": "message", "channel": "CDEMO", "subtype": "message_changed", "message": "xoxp-sensitive-value"}},
])
def test_malformed_signed_event_is_safe_and_does_not_poison_dedup(tmp_path, corruption):
    r = receiver(tmp_path)
    broken = event()
    broken.update(corruption)
    with pytest.raises(ValueError) as exc:
        r.receive(*signed(broken))
    assert "sensitive" not in str(exc.value)
    assert r.store.changes_since("0").changes == []
    # A malformed attempt never consumes the valid event id in the transaction.
    assert r.receive(*signed(event()))["duplicate"] is False


def test_duplicate_event_different_body_cannot_mutate_original(tmp_path):
    r = receiver(tmp_path)
    r.receive(*signed(event()))
    changed = event(inner={"type": "message", "channel": "CDEMO", "subtype": "message_deleted", "deleted_ts": ROOT})
    assert r.receive(*signed(changed))["duplicate"]
    assert [(c.native_id, c.kind) for c in r.store.changes_since("0").changes] == [(NID, "upsert")]


def test_delegated_visibility_does_not_restore_ingested_hidden_messages(tmp_path):
    fake = FakeSlack()
    fake.reply_pages = [[message(), message("1700000001.000001", "Visible only to ingestion")]]
    def different_views(request):
        response = fake(request)
        if (request.url.path.endswith("conversations.replies")
                and request.headers["authorization"] == "Bearer xoxp-asker"):
            return httpx.Response(200, json={"ok": True, "messages": [message()], "has_more": False})
        return response
    c, _ = adapter(tmp_path, fake=different_views)
    assert "Visible only to ingestion" in c.fetch(NID).text
    assert "Visible only to ingestion" not in c.read_authorized(ASKER, NID).text
    assert c.check(ASKER, NID).resource_version != c.fetch(NID).version
