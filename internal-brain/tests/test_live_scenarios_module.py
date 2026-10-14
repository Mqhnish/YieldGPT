"""app/seeding/scenarios.py (used by scripts/atlassian_live_scenarios.py) passes on the fixture site
and translates demo ids to a seeded site's real ids."""
import os

import pytest

from app.brain import Brain
from app.seeding.scenarios import Ids, run
from app.sources.registry import build_connectors
from app.sources.world import World


@pytest.mark.skipif(os.environ.get("IB_ATLASSIAN_MODE", "fixture") != "fixture", reason="drives the HTTP connectors")
def test_scenarios_pass_on_fixture_site():
    w = World()
    checks = run(Brain(world=w, connectors=build_connectors(w, atlassian_mode="fixture")), Ids())
    assert len(checks) >= 14 and all(c.ok for c in checks), [c for c in checks if not c.ok]


def test_ids_translate_through_the_manifest():
    ids = Ids({"pages": {"CONF-103": "66170"}, "issues": {"PAY-110": "PAY-4"}})
    assert ids("confluence:CONF-103") == "confluence:66170" and ids("jira:PAY-110") == "jira:PAY-4"
    assert ids("slack:T0COMPANYA/db-migration/2001") == "slack:T0COMPANYA/db-migration/2001"
    assert ids.native("jira:PAY-110") == "PAY-4" and Ids()("jira:MIG-1") == "jira:MIG-1"
