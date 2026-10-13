"""Confluence + Jira lifecycle probe: create, edit, revoke, delete, each timed (L05, L06, G14).

  IB_ATLASSIAN_MODE=live IB_ACCOUNT_MAP=accounts.json python scripts/atlassian_lifecycle_probe.py
  python scripts/atlassian_lifecycle_probe.py --mode fixture          # offline, fake site

WRITES to the site: creates one page (space --space) and one issue (project --project),
edits, restricts and deletes them. Touches nothing else. The page ends in the trash.
Needs the seeded site (scripts/seed_atlassian.py) and the issue security level.

Report: evaluation/reports/atlassian-<mode>.md and .json. Redacted: no token, email,
accountId or site name. Exit code 1 if any step failed.
"""
import argparse
import json
import os
import pathlib
import sys
import tempfile
from datetime import datetime, timezone

sys.path.insert(0, ".")
_tmp = tempfile.mkdtemp(prefix="lifecycle-")
os.environ["IB_AUDIT_DB"] = os.path.join(_tmp, "audit.db")      # keep probe queries out of the app's audit
os.environ["IB_ANCHOR_PATH"] = os.path.join(_tmp, "anchors.jsonl")
os.environ["IB_RECONCILE_EVERY_S"] = "0"                        # look for deletions on every poll

from app import audit, config  # noqa: E402
from app.brain import Brain  # noqa: E402
from app.identity import USERS  # noqa: E402
from app.seeding.lifecycle import LifecycleProbe, ProbeConfig  # noqa: E402
from app.seeding.report import commit_label, redact  # noqa: E402,F401  (redact re-exported for tests)
from app.sources.atlassian_client import AtlassianClient  # noqa: E402
from app.sources.registry import build_connectors  # noqa: E402
from app.sources.world import World  # noqa: E402


def markdown(r):
    lines = [f"# Atlassian lifecycle probe ({r['mode']})", "",
             f"- Date (UTC): {r['date']}",
             f"- Commit: `{r['commit']}`{' (uncommitted changes present)' if r['dirty'] else ''}",
             f"- Mode: **{r['mode']}** ({'real Atlassian Cloud site, Standard trial' if r['mode'] == 'live' else 'real HTTP connectors against the in-process fake site, not live evidence'})",
             f"- Personas: viewer `{r['config']['viewer']}`, insider `{r['config']['insider']}`; "
             f"space `{r['config']['space_key']}`, project `{r['config']['project_key']}`",
             f"- Result: **{'ALL PASS' if r['all_pass'] else 'FAILURES'}** ({r['passed']}/{len(r['steps'])} steps)", "",
             "Every step goes through the app's real pipeline (`Brain.ask`, live permission checks). "
             "Retrievability times include an immediate poll, so they measure pipeline visibility, "
             "not the 5-minute production poll interval.", "",
             "| Platform | Step | Mode | Result | Seconds | Detail |", "|---|---|---|---|---:|---|"]
    for s in r["steps"]:
        lines.append(f"| {s['platform']} | {s['step']} | {r['mode']} | {'PASS' if s['ok'] else 'FAIL'} | "
                     f"{s['seconds']} | {s['detail']} |")
    lines += ["", "Redacted: no API token, email, accountId or site name appears in this report."]
    return "\n".join(lines) + "\n"


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--mode", default=config.ATLASSIAN_MODE, choices=["live", "fixture"])
    ap.add_argument("--space", help="space key (default ENG live, eng fixture)")
    ap.add_argument("--project", default="MIG")
    ap.add_argument("--viewer", default="ravi")
    ap.add_argument("--insider", default="asha")
    ap.add_argument("--platforms", default="confluence,jira")
    ap.add_argument("--out", help="report path without extension (default evaluation/reports/atlassian-<mode>)")
    a = ap.parse_args()
    cfg = ProbeConfig(space_key=a.space or ("ENG" if a.mode == "live" else "eng"), project_key=a.project,
                      viewer=a.viewer, insider=a.insider)
    if a.mode == "fixture":
        cfg.timeout_s, cfg.poll_every_s = 5, 0
    audit.init()
    world = World()
    brain = Brain(world=world, connectors=build_connectors(world, atlassian_mode=a.mode))
    writer = (AtlassianClient(config.ATLASSIAN_SITE, config.ATLASSIAN_EMAIL, config.ATLASSIAN_API_TOKEN, timeout_s=45)
              if a.mode == "live" else None)
    probe = LifecycleProbe(brain, cfg, writer=writer)
    steps = probe.run(tuple(a.platforms.split(",")))
    commit, dirty = commit_label()
    r = {"mode": a.mode, "date": datetime.now(timezone.utc).isoformat(timespec="seconds"),
         "commit": commit, "dirty": dirty,
         "config": {k: getattr(cfg, k) for k in ("space_key", "project_key", "viewer", "insider", "security_level")},
         "steps": [s.__dict__ for s in steps], "passed": sum(s.ok for s in steps),
         "all_pass": bool(steps) and all(s.ok for s in steps)}
    out = pathlib.Path(a.out or f"evaluation/reports/atlassian-{a.mode}")
    out.parent.mkdir(parents=True, exist_ok=True)
    out.with_suffix(".json").write_text(redact(json.dumps(r, indent=2)) + "\n")
    out.with_suffix(".md").write_text(redact(markdown(r)))
    for s in steps:
        print(redact(f"{'PASS' if s.ok else 'FAIL'}  {s.platform:10} {s.step:62} {s.seconds:8.3f}s  {s.detail}"))
    print(f"\n{'ALL PASS' if r['all_pass'] else 'FAILURES'}  report: {out}.md / .json")
    sys.exit(0 if r["all_pass"] else 1)


if __name__ == "__main__":
    main()
