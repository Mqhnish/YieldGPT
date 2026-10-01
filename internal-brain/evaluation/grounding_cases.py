"""Measured grounding labels specify exact support, not lexical similarity."""
import hashlib
import json
PAIRS = [
 ('negation-approval','The migration is not approved.','The migration is approved.'),
 ('negation-required','Do not disable certificate verification.','Disable certificate verification.'),
 ('negation-completion','The rollout has never completed.','The rollout has completed.'),
 ('number-duration','The incident lasted 47 minutes.','The incident lasted 74 minutes.'),
 ('number-percent','Migration progress is 70%.','Migration progress is 100%.'),
 ('number-decimal','The error rate is 0.5%.','The error rate is 5%.'),
 ('number-accounts','37 employee accounts were affected.','73 employee accounts were affected.'),
 ('date-cutover','Cutover is planned for 20 October 2026.','Cutover is planned for 21 October 2026.'),
 ('date-deadline','The licence expires on 25 October.','The licence expires on 25 November.'),
 ('uncertainty','The delay may affect the launch.','The delay will affect the launch.'),
 ('short-yes','Yes.','No.'),('short-status','Blocked.','Approved.')]
CASES=[]
for name,truth,falsehood in PAIRS:
    source={'ref':'S1','text':truth,'title':'Evidence'}
    CASES.append({'id':name+'-supported','category':'grounding','sources':[source],'answer':truth+' [S1]','accept':True})
    CASES.append({'id':name+'-altered','category':'grounding','sources':[source],'answer':falsehood+' [S1]','accept':False})
CASES += [
 {'id':'contradiction-preserved','category':'grounding','sources':[{'ref':'S1','title':'Before','text':'Migration is approved.'},{'ref':'S2','title':'After','text':'Migration is not approved.'}],'answer':'Migration is approved. [S1]\nMigration is not approved. [S2]','accept':True},
 {'id':'contradiction-wrong-citation','category':'grounding','sources':[{'ref':'S1','title':'Before','text':'Migration is approved.'},{'ref':'S2','title':'After','text':'Migration is not approved.'}],'answer':'Migration is approved. [S2]','accept':False},
 {'id':'unknown-ref-alongside-valid','category':'grounding','sources':[{'ref':'S1','title':'Evidence','text':'Migration is approved.'}],'answer':'Migration is approved. [S1][S99]','accept':False},
 {'id':'uncited-short-claim','category':'grounding','sources':[{'ref':'S1','title':'Evidence','text':'Migration is approved.'}],'answer':'Migration is approved. [S1]\nBudget approved.','accept':False}]

def evaluate_grounding(enforce):
    rows=[]
    for case in CASES:
        _,detail=enforce(case['answer'],case['sources'])
        accepted=not detail['dropped'] and detail['kept']==len(case['answer'].splitlines())
        rows.append({'id':case['id'],'expected_accept':case['accept'],'accepted':accepted,'passed':accepted==case['accept']})
    return {'category':'grounding','total':len(rows),'passed':sum(r['passed'] for r in rows),
        'false_accepts':sum(r['accepted'] and not r['expected_accept'] for r in rows),
        'false_rejects':sum(not r['accepted'] and r['expected_accept'] for r in rows),
        'case_sha256':hashlib.sha256(json.dumps(CASES,sort_keys=True).encode()).hexdigest(),'cases':rows,
        'scope':'Exact supported passage decisions. Not broad semantic entailment or contradictory evidence retrieval.'}
