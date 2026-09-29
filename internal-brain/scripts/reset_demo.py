#!/usr/bin/env python3
"""Clean reset of ISOLATED demo data (audit log, content key, local checkpoints, sync state).

Refuses unless IB_DEMO_MODE=1. A WORM checkpoint store cannot be reset through its API,
by design; for the Docker Compose deployment reset BOTH volumes instead:

    docker compose -f deploy/docker-compose.yml down -v && docker compose -f deploy/docker-compose.yml up -d
"""
import argparse
import os
import shutil
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--yes", action="store_true", help="delete without asking")
    args = parser.parse_args()
    from app import config
    if not config.DEMO_MODE:
        print("refusing: IB_DEMO_MODE is not 1, this is not demo data")
        return 1
    if os.getenv("IB_CHECKPOINT_S3_ENDPOINT"):
        print("refusing: checkpoints are in a WORM store. Reset both volumes with:\n"
              "  docker compose -f deploy/docker-compose.yml down -v")
        return 1
    data = config.DATA_DIR.resolve()
    if data in (config.ROOT.resolve(), Path.home().resolve(), Path("/")) or not data.is_dir():
        print(f"refusing: {data} does not look like an isolated data directory")
        return 1
    items = sorted(data.iterdir())
    print(f"will delete {len(items)} item(s) in {data}:", *[f"  {p.name}" for p in items], sep="\n")
    if not args.yes and input("type 'reset' to continue: ").strip() != "reset":
        print("cancelled")
        return 1
    for p in items:
        shutil.rmtree(p) if p.is_dir() else p.unlink()
    print("demo data reset; the next start rebuilds the index and a new audit chain")
    return 0


if __name__ == "__main__":
    sys.exit(main())
