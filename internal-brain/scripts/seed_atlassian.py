"""Seed a real Atlassian Cloud site with YieldGPT's demo company. Safe to re-run.

  export IB_ATLASSIAN_SITE=https://yourteam.atlassian.net
  export IB_ATLASSIAN_EMAIL=brain-bot@...  IB_ATLASSIAN_API_TOKEN=...
  export IB_ACCOUNT_MAP=accounts.json            # optional: adds personas to groups
  python scripts/seed_atlassian.py                # first run
  # ...do the printed manual steps...
  python scripts/seed_atlassian.py --apply-security
  python scripts/atlassian_live_check.py expectations.json

Writes seed_manifest.json (demo id -> real id) and expectations.json. Both are gitignored.
"""
import argparse
import json
import pathlib
import sys

sys.path.insert(0, ".")
from app import config  # noqa: E402
from app.seeding.atlassian_seed import AtlassianSeeder, Manifest  # noqa: E402
from app.sources.atlassian_client import AtlassianClient  # noqa: E402


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--apply-security", action="store_true", help="set issue security levels (after the manual scheme step)")
    ap.add_argument("--manifest", default="seed_manifest.json")
    ap.add_argument("--expectations", default="expectations.json")
    a = ap.parse_args()
    missing = [n for n, v in [("IB_ATLASSIAN_SITE", config.ATLASSIAN_SITE), ("IB_ATLASSIAN_EMAIL", config.ATLASSIAN_EMAIL),
                              ("IB_ATLASSIAN_API_TOKEN", config.ATLASSIAN_API_TOKEN)] if not v]
    if missing:
        sys.exit(f"set {', '.join(missing)} first (see docs/ATLASSIAN_SETUP.md)")
    client = AtlassianClient(config.ATLASSIAN_SITE, config.ATLASSIAN_EMAIL, config.ATLASSIAN_API_TOKEN, timeout_s=30)
    mpath = pathlib.Path(a.manifest)
    manifest = Manifest.from_json(mpath.read_text()) if mpath.exists() else None
    s = AtlassianSeeder(client, manifest=manifest)
    try:
        s.run(apply_security=a.apply_security)
    finally:
        mpath.write_text(s.m.to_json())       # keep progress even if a step failed
        for line in s.m.log:
            print("  " + line)
    pathlib.Path(a.expectations).write_text(json.dumps(s.expectations(), indent=1))
    print(f"\nwrote {mpath} and {a.expectations}")
    print("\nMANUAL STEPS (admin screens, once):")
    for n, step in enumerate(s.manual_checklist(), 1):
        print(f"  {n}. {step}")


if __name__ == "__main__":
    main()
