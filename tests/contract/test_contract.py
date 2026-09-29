"""THE CONNECTOR CONTRACT SUITE. Every connector must pass every test here.
Run just this suite:  python -m pytest tests/contract -q
Rule numbers (R1..R10) refer to app/sources/base.py.
"""
import dataclasses
import itertools

import pytest

from app.identity import USERS, principals
from app.sources.base import Decision, PermissionResult, SourceDoc, SourceUnavailable
from app.sources.registry import build_connectors
from app.sources.world import World

from .specs import SPECS

ids = [s.platform for s in SPECS]


def crawl(c) -> list[str]:
    """Enumerate through the PUBLIC contract only, so this suite also runs against real connectors."""
    seen, token = [], None
    while True:
        page, token = c.list_page(token, page_size=2)
        seen += page
        if not token:
            return seen


@pytest.fixture
def env():
    w = World()
    return w, build_connectors(w)


@pytest.mark.parametrize("spec", SPECS, ids=ids)
def test_permission_matrix(env, spec):
    w, cs = env
    for user, nid, expected in spec.matrix:
        got = cs[spec.platform].check(USERS[user], nid)
        assert got.decision is expected, f"{user} on {nid}: expected {expected.value}, got {got.decision.value} ({got.reason})"


@pytest.mark.parametrize("spec", SPECS, ids=ids)
def test_extra_cases(env, spec):
    w, cs = env
    for fn in spec.extra:
        for user, nid, expected in fn(w):
            assert cs[spec.platform].check(USERS[user], nid).decision is expected


@pytest.mark.parametrize("spec", SPECS, ids=ids)
def test_R1_R10_result_shape(env, spec):
    w, cs = env
    r = cs[spec.platform].check(USERS["jdoe"], spec.matrix[0][1])
    assert isinstance(r, PermissionResult)
    assert r.reason_code and r.reason_code.replace("_", "").isalnum()   # stable machine code
    assert r.checked_at > 0 and r.platform_account


@pytest.mark.parametrize("spec", SPECS, ids=ids)
def test_R1_outage_fails_closed(env, spec):
    w, cs = env
    w.outages.add(spec.platform)
    user, nid, _ = next(c for c in spec.matrix if c[2] is Decision.ALLOWED)
    r = cs[spec.platform].check(USERS[user], nid)                       # must not raise
    assert r.decision is Decision.UNAVAILABLE and r.reason_code == "source_error"
    with pytest.raises(SourceUnavailable):                              # R6: outage != deletion
        cs[spec.platform].fetch(nid)


@pytest.mark.parametrize("spec", SPECS, ids=ids)
def test_R3_no_linked_account_is_denied(env, spec):
    w, cs = env
    ghost = dataclasses.replace(USERS["asha"], accounts=())
    for _, nid, _ in spec.matrix:
        r = cs[spec.platform].check(ghost, nid)
        assert r.decision is Decision.DENIED and r.reason_code == "no_linked_account"


@pytest.mark.parametrize("spec", SPECS, ids=ids)
def test_R4_unknown_resource_is_denied_not_found(env, spec):
    w, cs = env
    r = cs[spec.platform].check(USERS["asha"], "DOES-NOT-EXIST/0")
    assert r.decision is Decision.DENIED and r.reason_code == "not_found"


@pytest.mark.parametrize("spec", SPECS, ids=ids)
def test_R2_revocation_without_event(env, spec):
    w, cs = env
    user, nid = spec.revoke(World())  # dry run on a scratch world to learn the target
    assert cs[spec.platform].check(USERS[user], nid).allowed, "precondition: allowed before revocation"
    spec.revoke(w)
    assert not cs[spec.platform].check(USERS[user], nid).allowed


@pytest.mark.parametrize("spec", SPECS, ids=ids)
def test_R5_acl_hint_covers_every_allowed_user(env, spec):
    w, cs = env
    c = cs[spec.platform]
    for user, nid in itertools.product(USERS.values(), crawl(c)):
        if c.check(user, nid).allowed:
            assert principals(user) & c.acl_hint(nid), f"hint for {nid} would hide it from {user.username}"


@pytest.mark.parametrize("spec", SPECS, ids=ids)
def test_R7_list_page_is_complete_without_duplicates(env, spec):
    w, cs = env
    seen = crawl(cs[spec.platform])
    assert len(seen) == len(set(seen)), "duplicates across pages"
    assert set(seen) == spec.inventory(w), "crawl missed or invented objects"


@pytest.mark.parametrize("spec", SPECS, ids=ids)
def test_R7_R8_changes_since_cursor(env, spec):
    w, cs = env
    c = cs[spec.platform]
    cur = c.start_cursor()
    assert c.changes_since(cur).changes == []
    nid = spec.edit(w)
    page = c.changes_since(cur)
    assert [ch.native_id for ch in page.changes] == [nid] and page.changes[0].kind == "upsert"
    assert c.changes_since(page.next_cursor).changes == []              # cursor advanced
    assert c.changes_since(cur).changes == page.changes                 # replayable


@pytest.mark.parametrize("spec", SPECS, ids=ids)
def test_R6_R7_deletion(env, spec):
    w, cs = env
    c = cs[spec.platform]
    cur = c.start_cursor()
    assert c.fetch(spec.deletable) is not None
    w.delete(spec.platform, spec.deletable, push=False)
    assert c.fetch(spec.deletable) is None
    assert [(ch.native_id, ch.kind) for ch in c.changes_since(cur).changes] == [(spec.deletable, "delete")]


@pytest.mark.parametrize("spec", SPECS, ids=ids)
def test_R9_document_shape_and_versioning(env, spec):
    w, cs = env
    c = cs[spec.platform]
    for nid in crawl(c):
        d = c.fetch(nid)
        if d is None:
            continue
        assert isinstance(d, SourceDoc)
        assert d.uid == f"{spec.platform}:{nid}" and d.platform == spec.platform and d.native_id == nid
        assert d.version and d.tenant and d.url.startswith("https://")
    nid = spec.edit(w)
    before = cs[spec.platform].fetch(nid).version
    spec.edit(w)
    assert cs[spec.platform].fetch(nid).version != before
