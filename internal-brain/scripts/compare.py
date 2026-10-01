#!/usr/bin/env python3
"""Paired current/frozen lexical pipeline evaluation in separate processes."""
import argparse
import json
from pathlib import Path
import subprocess
import sys
ROOT=Path(__file__).resolve().parents[1]

def main():
    p=argparse.ArgumentParser(description=__doc__)
    p.add_argument('--output-dir',default='evaluation/reports')
    args=p.parse_args();out=Path(args.output_dir).resolve();out.mkdir(parents=True,exist_ok=True)
    reports=[]
    for name,extra in [('baseline',['--baseline']),('current',[])]:
        path=out/(name+'.json')
        result=subprocess.run([sys.executable,str(ROOT/'scripts/evaluate.py'),*extra,'--json',str(path),'--markdown',str(out/(name+'.md'))],cwd=ROOT,capture_output=True,text=True)
        if result.returncode not in (0,1) or not path.exists():
            print('Comparison setup failed for '+name+': '+result.stderr,file=sys.stderr);return 2
        reports.append(json.loads(path.read_text()))
    before,after=reports
    if before['case_sha256']!=after['case_sha256']: raise RuntimeError('Case sets differ')
    metrics={k:{'before':before['summary'][k],'after':after['summary'][k]} for k in ('passed','total','source_recall','unauthorized_citations','unauthorized_context_sources','no_answer_correct','no_answer_cases')}
    metrics['grounding_accuracy']={k:r['grounding']['passed']/r['grounding']['total'] for k,r in [('before',before),('after',after)]}
    metrics['grounding_false_accepts']={k:r['grounding']['false_accepts'] for k,r in [('before',before),('after',after)]}
    prior={c['id']:c for c in before['cases']}
    summary={'schema':'internal-brain.comparison/1','case_sha256':after['case_sha256'],'metrics':metrics,
        'improved':[c['id'] for c in after['cases'] if c['passed'] and not prior[c['id']]['passed']],
        'regressed':[c['id'] for c in after['cases'] if not c['passed'] and prior[c['id']]['passed']],
        'method':'Frozen original Member 1 lexical pipeline vs current pipeline, both rerun on identical current fixtures and expectations with offline generators. Controlled reconstruction, not a historical live-model measurement.'}
    (out/'comparison.json').write_text(json.dumps(summary,indent=2)+'\n')
    lines=['# Measured before/after comparison','',summary['method'],'','| Metric | Before | After |','|---|---:|---:|']
    lines += [f"| {k} | {v['before']} | {v['after']} |" for k,v in metrics.items()]
    lines+=['','Improved cases: '+', '.join(summary['improved']),'','Regressed cases: '+(', '.join(summary['regressed']) or 'none'),'', 'Token costs are unknown offline. Full per-case evidence and current stage timings are in current.json. Grounding is measured separately on 28 labeled edge cases.','']
    (out/'comparison.md').write_text('\n'.join(lines));print(json.dumps(summary,indent=2))
    return 0 if after['summary']['passed']==after['summary']['total'] and after['grounding']['passed']==after['grounding']['total'] else 1
if __name__=='__main__': raise SystemExit(main())
