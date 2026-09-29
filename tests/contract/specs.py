"""Per-platform inputs to the shared contract suite.

Each connector owner fills in ONE ContractSpec. The generic tests in
test_contract.py then check that connector against the contract rules in
app/sources/base.py. Add cases whenever you add a permission feature.

  Confluence, Jira  -> Member 1
  Slack             -> Member 2
  Google Drive      -> Member 3  (TODOs below are the minimum before "done")
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
    return "jdoe", "db-migration/2001"


def _drive_revoke(w):
    w.folders["fld-eng"]["shares"].pop("group:eng")  # folder share removed, no event
    return "jdoe", "DRV-2"


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
            ("jdoe", "db-migration/2001", A),
            ("jdoe", "mig-leads/2101", D),       # private channel she's not in
            ("ravi", "mig-leads/2101", A),
            ("jdoe", "sec-incidents/4001", D),
            ("kim", "vendor-collab/5001", A),    # shared channel
            ("kim", "db-migration/2001", D),
        ],
        revoke=_slack_revoke,
        edit=lambda w: (w.slack_post("db-migration", "ravi", "Update: lag fixed.", "db-migration/2001", push=False),
                        "db-migration/2001")[1],
        deletable="db-migration/2000",
        inventory=lambda w: set(w.threads),
        # TODO(Member 2): DM case, public-channel-by-scope case, message deletion/edit, retention expiry
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
        inventory=lambda w: set(w.files),
        # TODO(Member 3), required before the Drive adapter is "done":
        #  - limited-access folder: file inside is visible as metadata but contents DENIED
        #  - domain share: employee ALLOWED, contractor DENIED
        #  - shared drive membership vs direct file share
        #  - file moved out of a shared folder (acl change, no content change)
        #  - trashed file = fetch() None + kind "delete"
    ),
]

BY_PLATFORM = {s.platform: s for s in SPECS}
