"""Integrity of the hand-curated expectations and synthetic load fixture.

Answer behavior is evaluated by scripts/evaluate.py. These tests prevent stale,
impossible or accidentally self-contradictory evaluation expectations.
"""
from collections import Counter
import hashlib
import json
import os
from pathlib import Path
import subprocess
import sys

import pytest

from app.identity import USERS
from app.sources.registry import build_connectors
from app.sources.world import World
from evaluation.cases import CASES
from evaluation.synthetic import FULL_COUNTS, PRINCIPALS, TARGETS, make_corpus, queries


def test_curated_case_coverage_and_schema():
    assert len(CASES) >= 50
    assert len({c["id"] for c in CASES}) == len(CASES)
    assert len({(c["user"], c["question"]) for c in CASES}) == len(CASES)
    assert {c["category"] for c in CASES} == {
        "exact_identifier", "paraphrase", "cross_source", "time", "no_evidence", "security"}
    assert {c["user"] for c in CASES} == set(USERS)
    assert sum(c["no_answer"] for c in CASES) >= 10
    for case in CASES:
        assert case["question"].strip() and case["user"] in USERS
        expected = set(case["expected_all"]) | set(case["expected_any"])
        assert not expected.intersection(case["forbidden"])
        assert not case["no_answer"] or not expected
        assert case["no_answer"] or expected
        assert all(group and all(phrase for phrase in group) for group in case["answer_contains"])


def test_expected_sources_exist_and_persona_can_read_them():
    connectors = build_connectors(World())
    for case in CASES:
        user = USERS[case["user"]]
        for uid in case["expected_all"] + case["expected_any"]:
            platform, native = uid.split(":", 1)
            assert connectors[platform].fetch(native), (case["id"], uid)
            assert connectors[platform].check(user, native).allowed, (case["id"], uid)
        for uid in case["forbidden"]:
            platform, native = uid.split(":", 1)
            assert connectors[platform].fetch(native), (case["id"], uid)


def test_synthetic_corpus_is_deterministic_and_targets_are_eligible():
    def signature():
        digest = hashlib.sha256()
        for doc, hint in make_corpus("small"):
            digest.update(json.dumps([doc.uid, doc.title, doc.text, doc.updated_at, sorted(hint)]).encode())
        return digest.hexdigest()
    assert signature() == signature()
    docs = {doc.uid: (doc, hint) for doc, hint in make_corpus("small")}
    for query in queries():
        doc, hint = docs[query["expected_uid"]]
        assert hint.intersection(PRINCIPALS)
        assert doc.title and doc.text and doc.url.startswith("https://")
    assert len(queries()) == len(TARGETS)


def test_full_synthetic_estate_shape_and_varied_access():
    counts = Counter()
    containers = {p: set() for p in FULL_COUNTS}
    workspaces, drive_parents, access_patterns = set(), set(), set()
    for doc, hint in make_corpus("full"):
        counts[doc.platform] += 1
        containers[doc.platform].add(doc.container)
        access_patterns.add(frozenset(hint))
        if doc.platform == "slack":
            workspaces.add(doc.tenant)
        if doc.platform == "gdrive":
            drive_parents.add(doc.parent)
            assert doc.container.startswith(doc.parent + "/")
        assert doc.uid == f"{doc.platform}:{doc.native_id}"
    assert dict(counts) == FULL_COUNTS
    assert len(containers["confluence"]) == 52
    assert len(containers["jira"]) == 32
    assert len(containers["slack"]) == 220
    assert len(workspaces) == 3 and len(drive_parents) == 30
    assert len(access_patterns) == 7


@pytest.mark.parametrize("script,args", [
    ("evaluate.py", ["--case", "exact-migration-epic"]),
    ("benchmark.py", ["--size", "small", "--rounds", "1"]),
])
def test_cli_forces_offline_and_does_not_modify_existing_state(tmp_path, script, args):
    env = os.environ.copy()
    sentinel_paths = []
    for key in ("IB_AUDIT_DB", "IB_ANCHOR_PATH", "IB_SYNC_DB"):
        path = tmp_path / key.lower()
        path.write_bytes(b"existing-demo-state-must-not-change")
        env[key] = str(path)
        sentinel_paths.append(path)
    env["IB_LLM_PROVIDER"] = "openai_compatible"
    env["IB_LLM_BASE_URL"] = "http://127.0.0.1:1/unreachable"
    output = tmp_path / "measured.json"
    root = Path(__file__).resolve().parents[1]
    result = subprocess.run([sys.executable, str(root / "scripts" / script), *args, "--json", str(output)],
                            cwd=root, env=env, capture_output=True, text=True, timeout=30)
    assert result.returncode == 0, result.stdout + result.stderr
    assert json.loads(output.read_text())["schema"].startswith("internal-brain.")
    assert all(path.read_bytes() == b"existing-demo-state-must-not-change" for path in sentinel_paths)
