#!/usr/bin/env python3
"""List what the knowledge index holds: uid, title, container, who the ACL hint admits.

    python scripts/show_index.py            # table of all indexed documents
    python scripts/show_index.py DRV-2      # full text of matching documents
Uses an isolated temp data dir, so it never touches the real audit log.
"""
import os
import sys
import tempfile
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
tmp = tempfile.mkdtemp()
os.environ.update(IB_DATA_DIR=tmp, IB_AUDIT_DB=f"{tmp}/audit.db", IB_SLACK_CONFIG="", IB_DEMO_MODE="1")

from app import audit  # noqa: E402
from app.brain import Brain  # noqa: E402
from app.sources.world import World  # noqa: E402

audit.init()
index = Brain(World()).index
entries = sorted(index._docs.values(), key=lambda e: e.doc.uid)
if len(sys.argv) > 1:
    for e in (e for e in entries if sys.argv[1].lower() in e.doc.uid.lower()):
        print(f"== {e.doc.uid}  {e.doc.title}\n   acl: {sorted(e.acl_hint)}\n{e.doc.text}\n")
else:
    print(f"{len(entries)} documents\n{'uid':28} {'container':16} {'title':44} acl_hint")
    for e in entries:
        print(f"{e.doc.uid:28} {e.doc.container[:16]:16} {e.doc.title[:44]:44} {', '.join(sorted(e.acl_hint))[:50]}")
