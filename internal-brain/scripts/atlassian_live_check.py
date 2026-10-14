"""Read-only live conformance check for a real Atlassian site. Changes NOTHING on the site.

Usage:
  export IB_ATLASSIAN_MODE=live IB_ATLASSIAN_SITE=https://yourteam.atlassian.net \\
         IB_ATLASSIAN_EMAIL=bot@... IB_ATLASSIAN_API_TOKEN=... IB_ACCOUNT_MAP=accounts.json
  python scripts/atlassian_live_check.py expectations.json

expectations.json lists who SHOULD and SHOULDN'T see what, from how you set up the site:
  [{"user": "jdoe", "platform": "jira", "id": "SEC-1", "expect": "denied"},
   {"user": "asha", "platform": "jira", "id": "SEC-1", "expect": "allowed"}, ...]
Include at least: an inherited Confluence page restriction, a Jira issue with a
security level, and a user with no Atlassian account. Exit code 1 on any mismatch.

  --report evaluation/reports/atlassian-live-check.md   also save a dated, redacted copy
"""
import argparse
import builtins
import json
import pathlib
import sys
from datetime import datetime, timezone

sys.path.insert(0, ".")
from app.identity import USERS  # noqa: E402
from app.seeding.report import commit_label, redact  # noqa: E402
from app.sources.registry import build_connectors  # noqa: E402
from app.sources.world import World  # noqa: E402


def main(path, report=None):
    cs = build_connectors(World(), atlassian_mode="live")
    ok, out = True, []
    def print(line=""):  # noqa: A001  (also keep each line for the report)
        out.append(line)
        builtins.print(redact(line))
    for name in ("confluence", "jira"):
        c = cs[name]
        try:
            c.ping()
            ids, _ = c.list_page(None, 5)
            doc = c.fetch(ids[0]) if ids else None
            print(f"[{name}] reachable, first ids {ids}, fetched: {doc.title if doc else '-'} (v{doc.version if doc else '-'})")
            if doc:
                print(f"         links resolved: {doc.links}")
        except Exception as e:  # noqa: BLE001
            ok = False
            print(f"[{name}] FAILED: {type(e).__name__}: {e}")
    for exp in json.load(open(path)):
        r = cs[exp["platform"]].check(USERS[exp["user"]], exp["id"])
        match = r.decision.value == exp["expect"]
        ok &= match
        print(f"{'PASS' if match else 'FAIL'}  {exp['user']:6} {exp['platform']:10} {exp['id']:14} "
              f"expected {exp['expect']:9} got {r.decision.value:11} ({r.reason_code})")
    print("\nALL PASS" if ok else "\nMISMATCHES FOUND: do not demo live until fixed")
    if report:
        commit, dirty = commit_label()
        n = sum(1 for x in out if x.startswith(("PASS", "FAIL")))
        passed = sum(1 for x in out if x.startswith("PASS"))
        header = [f"# Atlassian live conformance check (live)", "",
                  f"- Date (UTC): {datetime.now(timezone.utc).isoformat(timespec='seconds')}",
                  f"- Commit: `{commit}`{' (uncommitted changes present)' if dirty else ''}",
                  "- Mode: **live** (real Atlassian Cloud site, Standard trial). Read-only: changes nothing.",
                  f"- Result: **{'ALL PASS' if ok else 'MISMATCHES'}** ({passed}/{n} persona x document checks)", "",
                  "Each line is Atlassian's own permission decision for that persona, made through the app's "
                  "connectors, compared with the expected decision from the demo company.", "", "```"]
        pathlib.Path(report).write_text(redact("\n".join(header + out + ["```", "",
            "Redacted: no API token, email, accountId or site name appears in this report."])) + "\n")
    sys.exit(0 if ok else 1)


if __name__ == "__main__":
    ap = argparse.ArgumentParser()
    ap.add_argument("expectations", nargs="?", default="expectations.json")
    ap.add_argument("--report", help="also write a dated, redacted markdown copy here")
    a = ap.parse_args()
    main(a.expectations, a.report)
