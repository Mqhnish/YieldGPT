"""Member 3: Drive change tracking and the handoff 5.4 cases beyond single decisions
(reason codes, removal of either access path, change kinds, sync effects)."""
import itertools

from app.identity import USERS, principals
from app.index import Index
from app.sources.gdrive import DriveConnector
from app.sources.world import World
from app.sync import Syncer

from .contract.specs import DRIVE_EXTRAS, _drive_limited_folder, _drive_shared_drive_vs_direct


def setup():
    w = World()
    return w, DriveConnector(w)


def test_limited_access_folder_denies_contents_to_parent_only_access():
    w, c = setup()
    _drive_limited_folder(w)
    r = c.check(USERS["jdoe"], "DRV-91")
    assert not r.allowed and r.reason_code == "limited_access_folder"
    assert c.check(USERS["asha"], "DRV-91").allowed
    assert principals(USERS["jdoe"]).isdisjoint(c.acl_hint("DRV-91"))   # prefilter never grants it either


def test_removing_either_shared_drive_or_direct_access_path():
    w, c = setup()
    _drive_shared_drive_vs_direct(w)
    w.files["DRV-92"]["shares"].pop("user:priya")          # direct share removed
    assert not c.check(USERS["priya"], "DRV-92").allowed and c.check(USERS["jdoe"], "DRV-92").allowed
    w.files["DRV-92"]["shares"]["user:jdoe"] = "view"
    w.shared_drives["sd-platform"]["members"].clear()      # shared drive membership removed
    assert c.check(USERS["jdoe"], "DRV-92").allowed        # still allowed through the direct share
    w.files["DRV-92"]["shares"].clear()
    assert c.check(USERS["jdoe"], "DRV-92").reason_code == "not_shared"


def test_move_out_of_shared_folder_is_an_acl_change_and_sync_recomputes_the_hint():
    w, c = setup()
    s = Syncer({"gdrive": c}, Index())
    s.full_load()
    assert "group:eng" in s.index.get("gdrive:DRV-2").acl_hint
    cursor, version = c.start_cursor(), c.fetch("DRV-2").version
    w.files["DRV-2"]["folder"] = None
    w._changed("gdrive", "DRV-2", False, kind="acl")
    assert [(x.native_id, x.kind) for x in c.changes_since(cursor).changes] == [("DRV-2", "acl")]
    assert c.fetch("DRV-2").version == version                       # content unchanged
    s.poll()
    assert "group:eng" not in s.index.get("gdrive:DRV-2").acl_hint
    assert not c.check(USERS["jdoe"], "DRV-2").allowed


def test_trash_removes_the_file_and_untrash_restores_it():
    w, c = setup()
    s = Syncer({"gdrive": c}, Index())
    s.full_load()
    cursor = c.start_cursor()
    w.files["DRV-3"]["trashed"] = True
    w._changed("gdrive", "DRV-3", False, kind="delete")
    assert c.fetch("DRV-3") is None and "DRV-3" not in c.list_page(None, 100)[0]
    assert [(x.native_id, x.kind) for x in c.changes_since(cursor).changes] == [("DRV-3", "delete")]
    assert c.check(USERS["kim"], "DRV-3").reason_code == "trashed"
    s.poll()
    assert s.index.get("gdrive:DRV-3") is None and s.store.tombstone("gdrive", "DRV-3") is not None
    w.files["DRV-3"]["trashed"] = False
    w._changed("gdrive", "DRV-3", False)
    s.poll()
    assert s.index.get("gdrive:DRV-3") is not None and c.check(USERS["kim"], "DRV-3").allowed


def test_domain_share_uses_the_drive_account_domain_not_the_employee_flag():
    w, c = setup()
    w.files["DRV-1"]["shares"]["domain"] = "view"
    contractor_on_company_domain = USERS["kim"].__class__(**{**USERS["kim"].__dict__,
                                                             "accounts": (("gdrive", "kim@companya.example"),)})
    employee_on_other_domain = USERS["priya"].__class__(**{**USERS["priya"].__dict__,
                                                           "accounts": (("gdrive", "priya@elsewhere.example"),)})
    assert c.check(contractor_on_company_domain, "DRV-1").allowed
    assert not c.check(employee_on_other_domain, "DRV-1").allowed


def test_acl_hint_covers_every_allowed_user_in_the_extended_estate():
    w, c = setup()
    for extra in DRIVE_EXTRAS:
        extra(w)
    for user, fid in itertools.product(USERS.values(), c.list_page(None, 1000)[0]):
        if c.check(user, fid).allowed:
            assert principals(user) & c.acl_hint(fid), (user.username, fid)
