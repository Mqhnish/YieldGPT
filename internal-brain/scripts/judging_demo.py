#!/usr/bin/env python3
"""Execute all five brief scenarios in an isolated fictional company and save evidence."""
import argparse
from datetime import datetime, timezone
import hashlib
import json
import os
from pathlib import Path
import sys
import tempfile

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))


def run(scratch):
    os.environ['IB_DATA_DIR'] = str(scratch)
    os.environ['IB_AUDIT_DB'] = str(scratch / 'audit.db')
    os.environ['IB_ANCHOR_PATH'] = str(scratch / 'anchors.jsonl')
    os.environ['IB_LLM_PROVIDER'] = 'stub'
    from app import audit, audit_policy
    from app.brain import Brain
    from app.grounding import NEUTRAL_NO_ANSWER
    from app.identity import USERS
    from app.sync_state import SqliteSyncStateStore
    audit.init()
    brain = Brain(sync_store=SqliteSyncStateStore(scratch / 'sync.db'))
    examples, checks = [], {}

    def ask(user, question):
        response = brain.ask(USERS[user], question)
        context = [c for e in audit.search(query_id=response['query_id'], event='context_assembled')
                   for c in e['detail']['context']]
        for item in context:
            platform, native_id = item['uid'].split(':',1)
            assert brain.connectors[platform].check(USERS[user], native_id).allowed
        return {'user':user, 'question':question, **response, 'authorized_context':context}

    migration = ask('jdoe', "What's the status of the database migration project and were there any blockers raised in Slack last week?")
    ids = {c['uid'] for c in migration['citations']}
    checks['unified_jira_slack_drive'] = {'jira:MIG-1','slack:db-migration/2001','gdrive:DRV-2'} <= ids
    checks['private_channel_excluded'] = 'slack:mig-leads/2101' not in ids and 'licence' not in migration['answer']
    examples.append({'scenario':1,'title':'Unified natural-language query','requests':[migration]})

    runbook_q = "What's the latest runbook for the payment-service incident?"
    before = ask('ravi', runbook_q)
    step = 'Step 5: If the certificate cannot be renewed within 10 minutes, fail over payment-service to the secondary card network gateway.'
    brain.world.confluence_update('CONF-101', step, push=False)
    checks['missed_webhook_fixture_is_stale'] = step not in brain.index.get('confluence:CONF-101').doc.text
    after = ask('ravi',runbook_q)
    checks['fresh_runbook_contains_new_failover_step'] = step in after['answer']
    checks['read_through_recorded'] = bool(audit.search(query_id=after['query_id'], event='read_through_refresh'))
    examples.append({'scenario':2,'title':'Fresh runbook after a missed webhook','requests':[before,after],
                     'action':'Append critical failover step at the source; deliberately omit webhook and polling.'})

    restricted = ask('kim','Show me the security incident report from the Q3 breach.')
    absent = ask('kim','Show me the unicorn migration to Mars report.')
    checks['restricted_and_absent_same_response'] = restricted['answer'] == absent['answer'] == NEUTRAL_NO_ANSWER
    checks['negative_has_no_metadata'] = restricted['citations'] == absent['citations'] == []
    examples.append({'scenario':3,'title':'Negative case without a metadata disclosure','requests':[restricted,absent]})

    private_q = 'What did payments-oncall say about the gateway certificate?'
    pre = ask('ravi',private_q)
    brain.world.slack_remove_member('payments-oncall','ravi',push=False)
    post = ask('ravi',private_q)
    uid = 'slack:payments-oncall/3001'
    checks['private_revocation_effective_next_question'] = (uid in {c['uid'] for c in pre['citations']}
        and uid not in {c['uid'] for c in post['citations']})
    checks['revoked_content_excluded_from_model'] = uid not in {s['uid'] for s in post['authorized_context']}
    examples.append({'scenario':4,'title':'Live private-channel revocation','requests':[pre,post],
                     'action':'Remove Ravi from private payments-oncall; omit webhook and polling; ask again.'})

    ask('jdoe',runbook_q)
    ask('jdoe',"What's the payment gateway architecture?")
    inquiry = "Show me everything user 'jdoe' accessed related to the 'payment-gateway' Confluence space in the last 30 days."
    filters = audit.parse_question(inquiry)
    stories = audit_policy.reconstruct(USERS['priya'],filters)
    checks['audit_reconstructs_identity_question_answer_time_decisions'] = bool(stories) and all(
        s['actor'] == 'jdoe' and s['ts'] and s['question'] and s['answer'] and s['decisions'] for s in stories)
    checks['audit_inquiry_is_itself_logged'] = bool(audit.search(actor='priya',event='audit_accessed'))
    examples.append({'scenario':5,'title':'Compliance audit inquiry','viewer':'priya','question':inquiry,
                     'filters':filters,'stories':stories})
    assert all(checks.values()), checks
    return {'generated_at':datetime.now(timezone.utc).isoformat(),
            'mode':'fictional Company A; offline source selection; no live cloud calls',
            'implementation':{p.name:hashlib.sha256(p.read_bytes()).hexdigest()
                for p in (ROOT/'app').glob('*.py')}, 'checks':checks, 'examples':examples}


def markdown(report):
    lines = ['# Five worked examples from the challenge brief','',f"Generated: {report['generated_at']}",'',
        'Executed against fictional Company A using the offline evidence selector. All assembled context was independently checked against the current user permissions. This demonstrates application behavior, not live cloud service certification.','',
        f"**{sum(report['checks'].values())}/{len(report['checks'])} scenario checks passed.**",'']
    for example in report['examples']:
        lines += [f"## {example['scenario']}. {example['title']}",'']
        if example.get('action'): lines += [f"Action: {example['action']}",'']
        for index, r in enumerate(example.get('requests',[]),1):
            lines += [f"### Request {index} — {r['user']}",'',r['question'],'',
                f"Query: `{r['query_id']}` · Generation: `{r['quality']['mode']}`",'',r['answer'],'',
                '| Reference | Source | Version |','|---|---|---|']
            for c in r['citations']:
                lines += [f"| {c['ref']} | [{c['uid']}]({c['url']}) | {c['version']} |"]
            if not r['citations']: lines += ['| — | No source metadata returned | — |']
            lines += ['']
        if 'stories' in example:
            lines += [f"Compliance viewer: `{example['viewer']}`",'',example['question'],'',
                '| Actor | Query | Time (UTC) | Decisions | Answer recorded |',
                '|---|---|---|---:|---|']
            for s in example['stories']:
                stamp = datetime.fromtimestamp(s['ts'],timezone.utc).isoformat()
                lines += [f"| {s['actor']} | {s['query_id']} | {stamp} | {len(s['decisions'])} | Yes |"]
            lines += ['', 'Full questions, source decisions, context versions, timestamps and answers are preserved in the accompanying JSON report.','']
    lines += ['## Reproduce','', '```sh', 'python scripts/judging_demo.py --markdown docs/WORKED_EXAMPLES.md --json evaluation/reports/judging-scenarios.json', '```','',
        'The script creates temporary audit/sync data and does not use or overwrite your running demo database. Source links point to fictional fixture locations. Source APIs, SSO, external audit protection and the real model require separate team integration.','']
    return '\n'.join(lines)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--json')
    parser.add_argument('--markdown')
    args = parser.parse_args()
    with tempfile.TemporaryDirectory(prefix='internal-brain-brief-') as directory:
        report = run(Path(directory))
    for destination, text in ((args.json,json.dumps(report,indent=2)),(args.markdown,markdown(report))):
        if destination:
            path = Path(destination)
            path.parent.mkdir(parents=True,exist_ok=True)
            path.write_text(text,encoding='utf-8')
    print(f"PASS: {len(report['checks'])} checks across all five brief scenarios")


if __name__ == '__main__':
    main()
