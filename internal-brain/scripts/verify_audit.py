#!/usr/bin/env python3
"""Standalone audit verifier, run by an auditor independently of the web application.

It reads the audit database and the protected checkpoint store (with the READ-ONLY
checkpoint credential) and prints a JSON report.

    IB_AUDIT_DB=/path/audit.db IB_CHECKPOINT_S3_ENDPOINT=http://127.0.0.1:9000 \
    IB_CHECKPOINT_READER_KEY=... IB_CHECKPOINT_READER_SECRET=... python scripts/verify_audit.py

Without IB_AUDIT_CONTENT_KEY, sealed text is counted as "unchecked" rather than opened.
Exit status: 0 verified, 1 failed (tampering detected), 2 unverifiable.
"""
import argparse
import json
import os
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--db", help="audit database (default: IB_AUDIT_DB or data/audit.db)")
    args = parser.parse_args()
    if args.db:
        os.environ["IB_AUDIT_DB"] = args.db
    from app import audit
    if not Path(audit.AUDIT_DB).exists():
        print(json.dumps({"status": "unverifiable", "problem": f"audit database not found: {audit.AUDIT_DB}"}))
        return 2
    report = audit.verify_report()
    print(json.dumps(report, indent=2))
    return {"verified": 0, "failed": 1}.get(report["status"], 2)


if __name__ == "__main__":
    sys.exit(main())
