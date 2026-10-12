import os
import tempfile

_tmp = tempfile.mkdtemp()
os.environ['IB_DATA_DIR'] = _tmp
os.environ['IB_ENV_FILE'] = os.path.join(_tmp, '.env')
os.environ.setdefault("IB_AUDIT_DB", os.path.join(_tmp, "audit.db"))
os.environ.setdefault("IB_ANCHOR_PATH", os.path.join(_tmp, "anchors.jsonl"))
os.environ["IB_LLM_PROVIDER"] = "stub"
os.environ["IB_RECONCILE_EVERY_S"] = "0"   # detect deletions on every poll in tests
os.environ.setdefault("IB_ATLASSIAN_MODE", "fixture")

import pytest  # noqa: E402

from app import audit  # noqa: E402
from app.brain import Brain  # noqa: E402
from app.identity import USERS  # noqa: E402


@pytest.fixture(autouse=True)
def fresh_audit(tmp_path, monkeypatch):
    monkeypatch.setattr(audit, "AUDIT_DB", tmp_path / "audit.db")
    monkeypatch.setattr(audit, "ANCHOR_PATH", tmp_path / "anchors.jsonl")
    audit.init()


@pytest.fixture
def brain():
    return Brain()


@pytest.fixture
def ask(brain):
    def _ask(user, q):
        return brain.ask(USERS[user], q)
    return _ask


def cited(resp):
    return {c["uid"] for c in resp["citations"]}
