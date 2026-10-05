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
"""
import json
import sys

sys.path.insert(0, ".")
from app.identity import USERS  # noqa: E402
from app.sources.registry import build_connectors  # noqa: E402
from app.sources.world import World  # noqa: E402


def main(path):
    cs = build_connectors(World(), atlassian_mode="live")
    ok = True
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
    sys.exit(0 if ok else 1)


if __name__ == "__main__":
    main(sys.argv[1] if len(sys.argv) > 1 else "expectations.json")
