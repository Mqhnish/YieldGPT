#!/usr/bin/env python3
"""Read-only live Slack acceptance checks; never edits or deletes workspace data.
A workspace owner prepares a disposable fixture and performs transitions between
runs. A phase without credentials is NOT RUN (exit 2), never an offline pass.
"""
import argparse
from datetime import datetime, timezone
import hashlib
import json
import os
from pathlib import Path
import sys
import time
ROOT=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT))

def main():
    p=argparse.ArgumentParser(description=__doc__)
    p.add_argument('--manifest',default='examples/slack-live-checks.example.json')
    p.add_argument('--phase',choices=['initial','edited','revoked','deleted','expired'],default='initial')
    p.add_argument('--json',default='evaluation/reports/live-slack.json')
    args=p.parse_args()
    from app.env import load_env
    load_env()
    report={'schema':'internal-brain.live-slack/1','generated_at':datetime.now(timezone.utc).isoformat(),
            'phase':args.phase,'status':'not_run_missing_credentials','cases':[],
            'scope':'Read-only current native permissions and content expectations; manual fixture transitions. No source contents or credentials saved.'}
    connector=None
    code=2
    try:
        if not os.getenv('IB_SLACK_CONFIG'):
            report['reason']='IB_SLACK_CONFIG is unset'
        else:
            from app.slack_runtime import create_live_slack_from_env
            from app.identity import USERS
            connector,_=create_live_slack_from_env()
            manifest=json.loads(Path(args.manifest).read_text())
            report['manifest_sha256']=hashlib.sha256(json.dumps(manifest,sort_keys=True).encode()).hexdigest()
            selected=[r for r in manifest['checks'] if args.phase in r['phases']]
            if not selected: raise ValueError('empty phase')
            for row in selected:
                started=time.perf_counter();expected=row['phases'][args.phase];passed=False;error=None
                try:
                    user=USERS[row['user']]
                    decision=connector.check(user,row['native_id'])
                    doc=connector.read_authorized(user,row['native_id'])
                    passed=decision.allowed==expected['allowed'] and bool(doc)==expected['allowed']
                    if doc:
                        passed=passed and all(t in doc.text for t in expected.get('contains',[])) and not any(t in doc.text for t in expected.get('absent',[]))
                    # A source outage is never a successful denial/revocation test.
                    if decision.decision.value=='unavailable' or decision.reason_code in {'no_linked_account','workspace_mismatch'}: passed=False
                except Exception as e: error=type(e).__name__
                report['cases'].append({'id':row['id'],'passed':passed,'error_type':error,'elapsed_ms':round((time.perf_counter()-started)*1000,3)})
            report['status']='passed' if all(r['passed'] for r in report['cases']) else 'failed'
            code=0 if report['status']=='passed' else 1
    except Exception as e:
        report['status']='not_run_configuration_error';report['error_type']=type(e).__name__
    finally:
        if connector: connector.client.close()
        from app import slack_oauth
        if slack_oauth.RUNTIME: slack_oauth.RUNTIME.client.close()
    target=Path(args.json);target.parent.mkdir(parents=True,exist_ok=True)
    target.write_text(json.dumps(report,indent=2)+'\n');print(json.dumps(report,indent=2))
    return code
if __name__=='__main__': raise SystemExit(main())
