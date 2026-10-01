"""Per-platform inputs to the shared contract suite.

Each connector owner fills in ONE ContractSpec. The generic tests in
test_contract.py then check that connector against the contract rules in
app/sources/base.py. Add cases whenever you add a permission feature.

  Confluence, Jira  -> Member 1
  Slack             -> Member 2
  Google Drive      -> Member 3
"""
from dataclasses import dataclass, field
from typing import Callable

from app.sources.base import Decision

A, D, U = Decision.ALLOWED, Decision.DENIED, Decision.UNAVAILABLE


@dataclass
class ContractSpec:
    platform: str
    # (username, native_id, expected decision) using the demo fixture
    matrix: list[tuple[str, str, Decision]]
    # mutate the world WITHOUT delivering an event so (user, id) loses access; return (user, id)
    revoke: Callable
    # edit content of an object; return its native id
    edit: Callable
    # an object that can be deleted
    deletable: str
    # ground truth for completeness: every native id that exists in the test estate.
    # For a live test tenant this comes from a fixture manifest, not from the connector.
    inventory: Callable = lambda w: set()
    # optional extra cases: fn(world) -> list[(username, native_id, expected)]
    extra: list[Callable] = field(default_factory=list)


def _conf_revoke(w):
    w.confluence_restrict("CONF-102", {"user:asha"}, push=False)
    return "jdoe", "CONF-102"


def _jira_revoke(w):
    w.jira_set_security_level("MIG-7", "security-only", push=False)
    return "jdoe", "MIG-7"


def _jira_unknown_level(w):
    w.issues["MIG-9"]["level"] = "does-not-exist"
    return [("jdoe", "MIG-9", U)]


def _slack_revoke(w):
    w.slack_remove_member("db-migration", "jdoe", push=False)
    return "jdoe", "T0COMPANYA/db-migration/2001"


def _drive_revoke(w):
    w.folders["fld-eng"]["shares"].pop("group:eng")  # folder share removed, no event
    return "jdoe", "DRV-2"


# ---- Drive cases from the Member 1 -> Member 3 handoff (section 5.4). Each builds on the test world only.
def _drive_file(w, fid, folder, shares, name):
    w.files[fid] = dict(folder=folder, shares=shares, updated=w.files["DRV-1"]["updated"], name=name,
                        text=f"{name}.", links=[])


def _drive_domain_share(w):
    _drive_file(w, "DRV-90", None, {"domain": "view"}, "Company holiday calendar")
    return [("jdoe", "DRV-90", A), ("priya", "DRV-90", A),
            ("kim", "DRV-90", D)]            # contractor: Drive account is on vendorco.example


def _drive_limited_folder(w):
    w.folders["fld-legal"] = {"name": "Legal hold", "parent": "fld-eng", "shares": {"user:asha": "view"},
                              "limited": True}
    _drive_file(w, "DRV-91", "fld-legal", {}, "Legal hold memo")
    return [("jdoe", "DRV-91", D),           # reaches it only via group:eng on the parent: metadata, not content
            ("asha", "DRV-91", A)]           # added to the limited folder itself


def _drive_shared_drive_vs_direct(w):
    w.shared_drives = {"sd-platform": {"members": {"group:eng": "reader"}}}
    w.folders["fld-sd"] = {"name": "Platform (shared drive)", "parent": None, "shares": {}, "drive": "sd-platform"}
    _drive_file(w, "DRV-92", "fld-sd", {"user:priya": "view"}, "Platform capacity plan")
    return [("jdoe", "DRV-92", A),           # shared drive membership
            ("priya", "DRV-92", A),          # direct file share
            ("kim", "DRV-92", D)]


def _drive_moved_out_of_shared_folder(w):
    w.files["DRV-2"]["folder"] = None        # moved to the owner's My Drive: acl change, content unchanged
    w._changed("gdrive", "DRV-2", False, kind="acl")
    return [("jdoe", "DRV-2", D)]


def _drive_trashed(w):
    w.files["DRV-3"]["trashed"] = True
    w._changed("gdrive", "DRV-3", False, kind="delete")
    return [("kim", "DRV-3", D)]


DRIVE_EXTRAS = [_drive_domain_share, _drive_limited_folder, _drive_shared_drive_vs_direct,
                _drive_moved_out_of_shared_folder, _drive_trashed]


def _slack_dm(w):
    import time
    now=time.time()
    w.channels['contract-dm']={'workspace':'T0COMPANYA','private':True,'is_im':True,
        'members':{'jdoe','asha'},'retention_days':1}
    w.threads['T0COMPANYA/contract-dm/9001']={'ts':now,'msgs':[('asha',now,'Direct confidential discussion.')]}
    return [('jdoe','T0COMPANYA/contract-dm/9001',A),('ravi','T0COMPANYA/contract-dm/9001',D)]


def _slack_public(w):
    w.channels['db-migration'].update(public_read=True,workspace_accounts={'T0COMPANYA/U0PRIYA'})
    return [('priya','T0COMPANYA/db-migration/2001',A),('kim','T0COMPANYA/db-migration/2001',D)]


def _slack_retention(w):
    import time
    w.channels['contract-old']={'workspace':'T0COMPANYA','private':True,'members':{'jdoe'},'retention_days':1}
    old=time.time()-2*86400
    w.threads['T0COMPANYA/contract-old/9002']={'ts':old,'msgs':[('jdoe',old,'Expired message.')]}
    return [('jdoe','T0COMPANYA/contract-old/9002',D)]


SLACK_EXTRAS=[_slack_dm,_slack_public,_slack_retention]


SPECS = [
    ContractSpec(
        "confluence",
        matrix=[
            ("jdoe", "CONF-102", A),   # eng space, all-employees
            ("jdoe", "CONF-101", A),   # payment-gateway via group:eng
            ("jdoe", "CONF-103", D),   # security space
            ("asha", "CONF-103", A),
            ("jdoe", "CONF-104", D),   # page restricted to dana
            ("dana", "CONF-104", A),
            ("jdoe", "CONF-105", D),   # inherits parent restriction
            ("dana", "CONF-105", A),
            ("kim", "CONF-102", D),    # contractor: no Atlassian account
            ("priya", "CONF-101", D),  # employee but not eng/payments
        ],
        revoke=_conf_revoke,
        edit=lambda w: (w.confluence_update("CONF-101", "Step 9: test edit.", push=False), "CONF-101")[1],
        deletable="CONF-106",
        inventory=lambda w: set(w.pages),
    ),
    ContractSpec(
        "jira",
        matrix=[
            ("jdoe", "MIG-1", A),
            ("priya", "MIG-1", A),     # viewers role = all-employees
            ("priya", "PAY-101", D),   # PAY browse = developers only
            ("jdoe", "PAY-101", A),
            ("jdoe", "PAY-110", D),    # issue security level
            ("asha", "PAY-110", A),
            ("jdoe", "SEC-4", D),
            ("asha", "SEC-4", A),
            ("kim", "MIG-1", D),       # no Atlassian account
        ],
        revoke=_jira_revoke,
        edit=lambda w: (w.jira_update("MIG-1", status="Done", push=False), "MIG-1")[1],
        deletable="MIG-9",
        inventory=lambda w: set(w.issues),
        extra=[_jira_unknown_level],
    ),
    ContractSpec(
        "slack",
        matrix=[
            ("jdoe", "T0COMPANYA/db-migration/2001", A),
            ("jdoe", "T0COMPANYA/mig-leads/2101", D),       # private channel she's not in
            ("ravi", "T0COMPANYA/mig-leads/2101", A),
            ("jdoe", "T0COMPANYA/sec-incidents/4001", D),
            ("kim", "T0VENDOR/vendor-collab/5001", A),    # shared channel
            ("kim", "T0COMPANYA/db-migration/2001", D),
        ],
        revoke=_slack_revoke,
        edit=lambda w: (w.slack_post("db-migration", "ravi", "Update: lag fixed.", "T0COMPANYA/db-migration/2001", push=False),
                        "T0COMPANYA/db-migration/2001")[1],
        deletable="T0COMPANYA/db-migration/2000",
        inventory=lambda w: set(w.threads),
        extra=SLACK_EXTRAS,
    ),
    ContractSpec(
        "gdrive",
        matrix=[
            ("jdoe", "DRV-2", A),      # shared drive folder share to group:eng
            ("jdoe", "DRV-1", A),      # inherited from grandparent folder
            ("priya", "DRV-1", D),
            ("jdoe", "DRV-4", D),      # personal file shared only with asha
            ("asha", "DRV-4", A),
            ("kim", "DRV-3", A),       # external "anyone" share
            ("kim", "DRV-2", D),
        ],
        revoke=_drive_revoke,
        edit=lambda w: (w.files["DRV-2"].update(text="edited", updated=w.files["DRV-2"]["updated"] + 1),
                        w._changed("gdrive", "DRV-2", False), "DRV-2")[2],
        deletable="DRV-2",
        inventory=lambda w: {fid for fid, f in w.files.items() if not f.get("trashed")},
        # Handoff 5.4 cases. Change kinds, fetch() and removal-of-either-path: tests/test_member3_drive.py
        extra=DRIVE_EXTRAS,
    ),
]

BY_PLATFORM = {s.platform: s for s in SPECS}
