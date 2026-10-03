"""Live Drive connector against a fake Drive API (httpx.MockTransport). No network."""
import json

import httpx
import pytest

from app.identity import USERS
from app.sources.base import ChangePage, Decision, SourceUnavailable
from app.sources.gdrive_live import DriveAPIError, DriveLiveConnector

BOT = "bot-token"
TOKENS = {"jdoe@companya.example": "tok-jdoe", "priya@companya.example": "tok-priya", "kim@vendorco.example": "tok-kim"}
DOC, FILE2, GONE = "docfile1", "txtfile2", "missing1"


class FakeDrive:
    """Per-token visibility: who may see which file, and canDownload."""

    def __init__(self):
        self.calls, self.fail = [], None
        self.meta = {DOC: dict(id=DOC, name="Runbook", mimeType="application/vnd.google-apps.document", trashed=False,
                               modifiedTime="2026-10-01T10:00:00.000Z", version="7", parents=["fldr0001"],
                               webViewLink="https://docs.google.com/document/d/docfile1/edit",
                               capabilities={"canDownload": True}),
                     FILE2: dict(id=FILE2, name="notes.txt", mimeType="text/plain", trashed=False,
                                 modifiedTime="2026-10-02T10:00:00Z", version="3", capabilities={"canDownload": True})}
        self.visible = {"tok-jdoe": {DOC, FILE2}, "tok-priya": {FILE2}, "tok-kim": set(), BOT: {DOC, FILE2}}
        self.nodownload = set()          # (token, id)

    def handler(self, req: httpx.Request) -> httpx.Response:
        self.calls.append(req)
        if self.fail:
            return self.fail(req)
        token = req.headers["authorization"].removeprefix("Bearer ")
        path, q = req.url.path.removeprefix("/drive/v3/"), dict(req.url.params)
        if path == "about":
            email = next((e for e, t in TOKENS.items() if t == token), "bot@companya.example")
            return httpx.Response(200, json={"user": {"emailAddress": email.upper()}})
        if path == "changes/startPageToken":
            return httpx.Response(200, json={"startPageToken": "100"})
        if path == "files":
            page2 = q.get("pageToken") == "p2"
            return httpx.Response(200, json={"files": [{"id": FILE2 if page2 else DOC}],
                                             **({} if page2 else {"nextPageToken": "p2"})})
        if path == "changes":
            if q["pageToken"] == "100":
                return httpx.Response(200, json={"nextPageToken": "101", "changes": [
                    {"fileId": DOC, "removed": False, "time": "2026-10-03T00:00:00Z", "file": {"trashed": False}}]})
            return httpx.Response(200, json={"newStartPageToken": "102", "changes": [
                {"fileId": FILE2, "removed": False, "time": "2026-10-03T00:00:01Z", "file": {"trashed": True}},
                {"fileId": GONE, "removed": True, "time": "2026-10-03T00:00:02Z"}]})
        parts = path.split("/")
        fid = parts[1]
        if fid not in self.visible.get(token, set()):
            return httpx.Response(404, json={"error": {"errors": [{"reason": "notFound"}]}})
        if len(parts) == 3 and parts[2] == "permissions":
            return httpx.Response(200, json={"permissions": [
                {"type": "user", "emailAddress": "ASHA@companya.example"}, {"type": "group", "emailAddress": "eng@companya.example"},
                {"type": "domain"}, {"type": "user", "emailAddress": "old@companya.example", "deleted": True}]})
        if len(parts) == 3 and parts[2] == "export":
            return httpx.Response(200, text="exported body")
        if q.get("alt") == "media":
            return httpx.Response(200, text="plain body")
        m = dict(self.meta[fid], capabilities={"canDownload": (token, fid) not in self.nodownload})
        return httpx.Response(200, json=m)


@pytest.fixture
def drive():
    return FakeDrive()


@pytest.fixture
def conn(drive):
    c = DriveLiveConnector("companya.example", BOT, lambda acct: TOKENS.get(acct),
                           client=httpx.Client(transport=httpx.MockTransport(drive.handler)))
    yield c
    c.client.close()


def test_allowed_denied_and_unlinked(conn):
    assert conn.check(USERS["jdoe"], DOC).decision is Decision.ALLOWED
    r = conn.check(USERS["priya"], DOC)
    assert (r.decision, r.reason_code) == (Decision.DENIED, "not_found")       # Drive hides it from her
    assert conn.check(USERS["priya"], FILE2).allowed
    assert conn.check(USERS["jdoe"], "x").reason_code == "not_found"          # malformed id never hits the API


def test_check_uses_the_askers_token_never_the_bot(conn, drive):
    conn.check(USERS["priya"], DOC)
    assert {c.headers["authorization"] for c in drive.calls} == {"Bearer tok-priya"}


def test_trashed_and_nodownload_are_denied(conn, drive):
    drive.meta[DOC]["trashed"] = True
    assert conn.check(USERS["jdoe"], DOC).reason_code == "trashed"
    drive.meta[DOC]["trashed"] = False
    drive.nodownload.add(("tok-jdoe", DOC))
    assert conn.check(USERS["jdoe"], DOC).reason_code == "limited_access_folder"


def test_check_fails_closed(conn, drive):
    drive.fail = lambda req: httpx.Response(503)
    assert conn.check(USERS["jdoe"], DOC).decision is Decision.UNAVAILABLE
    drive.fail = lambda req: httpx.Response(403, json={"error": {"errors": [{"reason": "userRateLimitExceeded"}]}})
    assert conn.check(USERS["jdoe"], DOC).decision is Decision.UNAVAILABLE      # rate limit is not a denial
    drive.fail = None
    c2 = DriveLiveConnector("companya.example", BOT, lambda acct: None, client=conn.client)
    assert c2.check(USERS["jdoe"], DOC).decision is Decision.UNAVAILABLE         # no delegated credential


def test_token_for_the_wrong_person_is_rejected(drive):
    c = DriveLiveConnector("companya.example", BOT, lambda acct: "tok-priya",   # jdoe's slot holds priya's token
                           client=httpx.Client(transport=httpx.MockTransport(drive.handler)))
    r = c.check(USERS["jdoe"], FILE2)
    assert r.decision is Decision.UNAVAILABLE and "tok-priya" not in r.reason


def test_fetch_exports_google_docs_and_reads_text(conn):
    d = conn.fetch(DOC)
    assert (d.uid, d.text, d.version, d.container, d.tenant) == ("gdrive:docfile1", "exported body", "7", "fldr0001", "companya.example")
    assert d.url.startswith("https://") and d.updated_at > 0
    assert conn.fetch(FILE2).text == "plain body" and conn.fetch(FILE2).url == "https://drive.google.com/file/d/txtfile2/view"


def test_fetch_none_when_deleted_but_raises_on_outage(conn, drive):
    assert conn.fetch(GONE) is None
    drive.meta[DOC]["trashed"] = True
    assert conn.fetch(DOC) is None
    drive.fail = lambda req: httpx.Response(500)
    with pytest.raises(SourceUnavailable):
        conn.fetch(FILE2)
    drive.fail = lambda req: (_ for _ in ()).throw(httpx.ConnectError("boom with secret-bot-token"))
    with pytest.raises(DriveAPIError) as e:
        conn.fetch(FILE2)
    assert "secret" not in str(e.value) and BOT not in str(e.value)


def test_read_authorized_is_the_askers_view(conn):
    assert conn.read_authorized(USERS["jdoe"], DOC).text == "exported body"
    assert conn.read_authorized(USERS["priya"], DOC) is None


def test_acl_hint_flattens_permissions(conn):
    assert conn.acl_hint(DOC) == {"user:asha", "group:eng", "domain"}
    assert conn.acl_hint(GONE) == set()


def test_list_pages_without_duplicates(conn):
    ids, tok = conn.list_page(None)
    more, end = conn.list_page(tok)
    assert (ids, more, end) == ([DOC], [FILE2], None)


def test_changes_map_to_upsert_and_delete_and_page(conn):
    assert conn.start_cursor() == "100"
    p1 = conn.changes_since("100")
    assert (p1.has_more, p1.next_cursor, [(c.native_id, c.kind) for c in p1.changes]) == (True, "101", [(DOC, "upsert")])
    p2 = conn.changes_since("101")
    assert isinstance(p2, ChangePage) and not p2.has_more and p2.next_cursor == "102"
    assert [(c.native_id, c.kind) for c in p2.changes] == [(FILE2, "delete"), (GONE, "delete")]


def test_ping_raises_when_down(conn, drive):
    conn.ping()
    drive.fail = lambda req: httpx.Response(503)
    with pytest.raises(SourceUnavailable):
        conn.ping()


def test_rejects_bad_config():
    with pytest.raises(ValueError):
        DriveLiveConnector("nodomain", BOT, lambda a: None)
    with pytest.raises(ValueError):
        DriveLiveConnector("companya.example", "", lambda a: None)
