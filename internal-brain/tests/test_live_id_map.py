"""Live mode: simulated Slack/Drive content uses the seeded site's real Jira keys and page ids."""
import json

from app.sources.registry import _map_demo_ids
from app.sources.world import World

MAP = {"issues": {"MIG-1": "MIG-1", "MIG-7": "MIG-2", "MIG-2": "MIG-9", "PAY-101": "PAY-1", "PAY-102": "PAY-2",
                  "PAY-103": "PAY-3"}, "pages": {"CONF-101": "131091"}}


def test_slack_and_drive_point_at_real_ids(tmp_path):
    p = tmp_path / "seed_manifest.json"
    p.write_text(json.dumps(MAP))
    w = World()
    assert _map_demo_ids(w, str(p)) > 0
    blocker = w.threads["T0COMPANYA/db-migration/2001"]["msgs"][0][2]
    assert "until MIG-2 is fixed" in blocker            # MIG-7 -> MIG-2, and not chained on to MIG-9
    assert "PAY-2 expiry alerting, PAY-3 loud failures" in w.files["DRV-1"]["text"]
    assert w.files["DRV-1"]["links"] == ["jira:PAY-1"]
    assert "ADR-17" in w.threads["T0COMPANYA/auth-design/1001"]["msgs"][2][2]   # unmapped ids untouched


def test_mapping_runs_once_and_skips_without_manifest(tmp_path):
    w = World()
    assert _map_demo_ids(w, str(tmp_path / "missing.json")) == 0
    p = tmp_path / "m.json"
    p.write_text(json.dumps(MAP))
    assert _map_demo_ids(w, str(p)) > 0 and _map_demo_ids(w, str(p)) == 0
    assert "until MIG-2 is fixed" in w.threads["T0COMPANYA/db-migration/2001"]["msgs"][0][2]
