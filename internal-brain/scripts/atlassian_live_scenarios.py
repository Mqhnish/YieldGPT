"""Run the brief's scenarios (S1, S3, S5) through the real pipeline against the Atlassian site.

  IB_ATLASSIAN_MODE=live IB_ACCOUNT_MAP=accounts.json python scripts/atlassian_live_scenarios.py
  python scripts/atlassian_live_scenarios.py --mode fixture        # offline, fake site

Read-only: only asks questions. S2 (freshness) and S4 (revocation) need edits and revokes on the
site; scripts/atlassian_lifecycle_probe.py proves those. Needs the seeded site and its
seed_manifest.json. Slack and Drive stay simulated. Report: evaluation/reports/atlassian-<mode>-scenarios.md
and .json, redacted. Exit code 1 if any check failed.
"""
import argparse
import json
import os
import pathlib
import sys
import tempfile
from datetime import datetime, timezone

sys.path.insert(0, ".")
_tmp = tempfile.mkdtemp(prefix="scenarios-")
os.environ["IB_AUDIT_DB"] = os.path.join(_tmp, "audit.db")      # a fresh audit trail just for this run
os.environ["IB_ANCHOR_PATH"] = os.path.join(_tmp, "anchors.jsonl")

from app import audit, config  # noqa: E402
from app.brain import Brain  # noqa: E402
from app.seeding.report import commit_label, redact  # noqa: E402
from app.seeding.scenarios import Ids, run  # noqa: E402
from app.sources.registry import build_connectors  # noqa: E402
from app.sources.world import World  # noqa: E402


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--mode", default=config.ATLASSIAN_MODE, choices=["live", "fixture"])
    ap.add_argument("--manifest", default="seed_manifest.json")
    ap.add_argument("--out", help="report path without extension (default evaluation/reports/atlassian-<mode>-scenarios)")
    a = ap.parse_args()
    manifest = None
    if a.mode == "live":
        if not pathlib.Path(a.manifest).exists():
            sys.exit(f"{a.manifest} not found: run scripts/seed_atlassian.py first")
        manifest = json.loads(pathlib.Path(a.manifest).read_text())
    audit.init()
    world = World()
    brain = Brain(world=world, connectors=build_connectors(world, atlassian_mode=a.mode))
    checks = run(brain, Ids(manifest))
    commit, dirty = commit_label()
    passed = sum(c.ok for c in checks)
    r = {"mode": a.mode, "date": datetime.now(timezone.utc).isoformat(timespec="seconds"), "commit": commit,
         "dirty": dirty, "checks": [c.__dict__ for c in checks], "passed": passed,
         "all_pass": bool(checks) and passed == len(checks)}
    lines = [f"# Brief scenarios on the Atlassian site ({a.mode})", "",
             f"- Date (UTC): {r['date']}",
             f"- Commit: `{commit}`{' (uncommitted changes present)' if dirty else ''}",
             f"- Mode: **{a.mode}** ({'Confluence + Jira on a real Atlassian Cloud site' if a.mode == 'live' else 'real HTTP connectors against the in-process fake site, not live evidence'}); "
             "Slack and Drive simulated in both modes",
             f"- Result: **{'ALL PASS' if r['all_pass'] else 'FAILURES'}** ({passed}/{len(checks)} checks)", "",
             "Every check asks the question through the app's real pipeline as that persona. S2 (freshness) and "
             "S4 (revocation) need edits on the site and are proven by the lifecycle probe report.", "",
             "| Scenario | Check | Result | Detail |", "|---|---|---|---|"]
    lines += [f"| {c.scenario} | {c.check} | {'PASS' if c.ok else 'FAIL'} | {c.detail} |" for c in checks]
    lines += ["", "Redacted: no API token, email, accountId or site name appears in this report."]
    out = pathlib.Path(a.out or f"evaluation/reports/atlassian-{a.mode}-scenarios")
    out.parent.mkdir(parents=True, exist_ok=True)
    out.with_suffix(".json").write_text(redact(json.dumps(r, indent=2)) + "\n")
    out.with_suffix(".md").write_text(redact("\n".join(lines)) + "\n")
    for c in checks:
        print(redact(f"{'PASS' if c.ok else 'FAIL'}  {c.scenario}  {c.check:80} {c.detail}"))
    print(f"\n{'ALL PASS' if r['all_pass'] else 'FAILURES'}  report: {out}.md / .json")
    sys.exit(0 if r["all_pass"] else 1)


if __name__ == "__main__":
    main()
