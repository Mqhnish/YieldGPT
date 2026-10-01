"""Regression checks for the integrated Member 2 + Member 3 delivery."""
import base64
import dataclasses
import json
import sqlite3
from urllib.parse import parse_qs, urlparse
import httpx
import pytest
from fastapi.testclient import TestClient
from app import audit, env, history, llm, main, server, slack_oauth
from app.identity import USERS, account_for
from app.slack_oauth import InstallationStore, SlackOAuth, OAuthUnavailable
from app.sources.slack_multi import SlackWorkspaces
from app.sources.slack_live import SlackLiveConnector
from app.sources.slack_events import SlackEventStore
from .test_member3_ops import auth
from .test_member3_audit import DownStore
from .test_slack_member2 import FakeSlack, message

@pytest.fixture
def client():
    with TestClient(server.app) as c: yield c

def test_direct_server_bypass_refused():
    with pytest.raises(RuntimeError,match='app.server'):
        with TestClient(main.app): pass

def test_env_values_are_literal_and_process_env_wins(tmp_path,monkeypatch):
    path=tmp_path/'.env';path.write_text('IB_TEST_LITERAL="$(touch /tmp/never-executed)"\nIB_TEST_OVERRIDE=file\n')
    monkeypatch.setenv('IB_TEST_OVERRIDE','process');monkeypatch.delenv('IB_TEST_LITERAL',raising=False)
    env.load_env(path)
    import os
    assert os.getenv('IB_TEST_OVERRIDE')=='process'
    assert os.getenv('IB_TEST_LITERAL')=='$(touch /tmp/never-executed)'
    monkeypatch.delenv('IB_TEST_LITERAL')
    path.write_text('invalid value')
    with pytest.raises(ValueError): env.load_env(path)

def test_history_rechecks_revocation_and_survives_preview_expiry(client):
    headers=auth(client,'jdoe')
    old=client.post('/api/ask',json={'question':'What was discussed in the Slack auth-design thread last sprint?'},headers=headers).json()
    assert old['citations'] and any(c['platform']=='slack' for c in old['citations'])
    entries=client.get('/api/history',headers=headers).json()['items']
    assert entries and set(entries[0])=={'query_id','created_at'}
    # A fresh Brain loses its five-minute preview cache. Audit history survives.
    from app.brain import Brain
    b=Brain();main.state['brain']=b
    b.world.slack_remove_member('auth-design','jdoe',push=False)
    result=client.post('/api/history/'+old['query_id']+'/replay',headers=headers)
    assert result.status_code==200
    assert result.json()['query_id']!=old['query_id']
    assert not result.json()['citations']
    assert audit.search(event='question_replayed',query_id=result.json()['query_id'])
    # Stored source text and the old answer are never returned by the list API.
    assert 'JWT' not in client.get('/api/history',headers=headers).text

def test_history_owner_expiry_and_checkpoint_gate(client,monkeypatch):
    headers=auth(client,'ravi')
    result=client.post('/api/ask',json={'question':'What is PAY-101?'},headers=headers).json()
    url='/api/history/'+result['query_id']+'/replay'
    assert client.post(url,headers=auth(client,'kim')).status_code==404
    monkeypatch.setattr(audit,'_store',lambda:DownStore())
    response=client.post(url,headers=headers)
    assert response.status_code==503 and 'certificate' not in response.text
    assert audit.search(event='response_withheld')
    # Expired/crypto-shredded question content makes replay unavailable.
    original=audit.search
    def expired(**kw):
        rows=original(**kw)
        if kw.get('event')=='query_received':
            for row in rows: row['detail'].pop('question',None)
        return rows
    monkeypatch.setattr(audit,'search',expired)
    with pytest.raises(history.HistoryUnavailable): history.replay(main.brain(),USERS['ravi'],result['query_id'])

def test_preview_delivery_cannot_resurrect_withheld_answer():
    qid='a'*12
    audit.log('jdoe','query_received',query_id=qid,question='What is MIG-1?')
    audit.log('jdoe','response_delivered',query_id=qid,route='/api/evidence/'+qid+'/S1')
    assert history.list_history('jdoe')==[]
    with pytest.raises(history.HistoryUnavailable): history.replay(None,USERS['jdoe'],qid)

def test_measurements_are_audit_only(client):
    headers=auth(client,'jdoe')
    result=client.post('/api/ask',json={'question':'What is MIG-1?'},headers=headers).json()
    phases=audit.search(query_id=result['query_id'],event='query_performance')[0]['detail']['phases_ms']
    assert phases['total_ms']>0 and phases['authorization_and_read_ms']>0
    assert phases['release_authorization_ms']>0
    assert 'phases_ms' not in result
    assert audit.search(query_id=result['query_id'],event='model_measurement')[0]['detail']['usage'] is None

@pytest.mark.parametrize('usage,rates,amount',[
 ({'prompt_tokens':1000,'completion_tokens':500},('2','4'),'0.004'),
 (None,('2','4'),None),({'prompt_tokens':1000,'completion_tokens':500},('bad','4'),None)])
def test_model_cost_is_configured_not_guessed(monkeypatch,usage,rates,amount):
    monkeypatch.setenv('IB_LLM_INPUT_PER_MILLION',rates[0]);monkeypatch.setenv('IB_LLM_OUTPUT_PER_MILLION',rates[1])
    value=llm.estimated_cost(usage)
    assert (value['amount'] if value else None)==amount

def test_strict_live_mode_does_not_silently_fallback(monkeypatch):
    monkeypatch.setenv('IB_LLM_REQUIRE_LIVE','1')
    with pytest.raises(llm.ModelUnavailable) as caught:
        llm.complete('Status?', [{'ref':'S1','text':'Ready.'}], 'Jane')
    assert caught.value.measurement['mode']=='failed'
    assert caught.value.measurement['remote_attempts']==0

def test_live_measurement_counts_http_tokens_and_failed_retry(monkeypatch):
    monkeypatch.setattr(llm,'LLM_PROVIDER','openai_compatible')
    monkeypatch.setattr(llm,'LLM_BASE_URL','https://model.example/v1')
    monkeypatch.setattr(llm,'LLM_MODEL','test');monkeypatch.setattr(llm,'LLM_API_KEY','fake')
    monkeypatch.setenv('IB_LLM_INPUT_PER_MILLION','2');monkeypatch.setenv('IB_LLM_OUTPUT_PER_MILLION','4')
    real=httpx.Client;requests=[]
    def respond(req):
        requests.append(req)
        if len(requests)==1: return httpx.Response(503)
        data=json.loads(req.content);source=json.loads(data['messages'][1]['content'])['sources'][0]
        return httpx.Response(200,json={'usage':{'prompt_tokens':100,'completion_tokens':20},'choices':[{'message':{'content':json.dumps({'selections':[{'source':source['ref'],'passage':source['passages'][0]['id']}]})}}]})
    monkeypatch.setattr(llm.httpx,'Client',lambda **kw:real(transport=httpx.MockTransport(respond),**kw))
    result=llm.complete('Status?', [{'ref':'S1','text':'Ready.'}],'Jane')
    m=result.measurement
    assert result.mode=='model_selected' and m['remote_attempts']==2
    assert len(m['attempts'])==2 and m['provider_http_ms']>0
    assert m['model_elapsed_ms']>=m['provider_http_ms']
    assert m['usage'] is None and m['estimated_cost'] is None # failed retry billing unknown

@pytest.fixture
def installation(tmp_path):
    clock=[1000.0]
    return InstallationStore(tmp_path/'install.db',base64.urlsafe_b64encode(b'x'*32),lambda:clock[0]),clock

def test_oauth_state_single_use_expiry_and_encrypted_binding(installation):
    store,clock=installation
    state=store.issue_state('jdoe','TONE');assert store.consume_state(state)==('jdoe','TONE')
    with pytest.raises(OAuthUnavailable): store.consume_state(state)
    state=store.issue_state('jdoe','TONE');clock[0]+=301
    with pytest.raises(OAuthUnavailable): store.consume_state(state)
    store.put('jdoe','TONE','TONE/UJANE',{'access_token':'xoxp-private-test'})
    assert b'xoxp-private-test' not in store.path.read_bytes()
    assert store.account('kim','TONE') is None
    with pytest.raises(OAuthUnavailable): store.put('kim','TONE','TONE/UJANE',{'access_token':'xoxp-other'})
    with sqlite3.connect(store.path) as c: c.execute("UPDATE installations SET sealed=x'00'")
    with pytest.raises(OAuthUnavailable): store.get('TONE/UJANE')

def test_oauth_rotation_workspace_identity_and_revoke(installation,monkeypatch):
    store,clock=installation;calls=[]
    def reply(req):
        calls.append(req)
        if req.url.path.endswith('auth.test'): return httpx.Response(200,json={'ok':True,'team_id':'TONE','user_id':'UJANE'})
        return httpx.Response(200,json={'ok':True,'access_token':'xoxe.xoxp-new','refresh_token':'rotated','expires_in':3600})
    runtime=SlackOAuth(store,['TONE'],'123','secret','https://brain.example/api/slack/oauth/callback',httpx.Client(transport=httpx.MockTransport(reply)))
    store.put('jdoe','TONE','TONE/UJANE',{'access_token':'xoxp-old','refresh_token':'old-refresh','expires_at':1001})
    monkeypatch.setattr(slack_oauth,'RUNTIME',runtime)
    assert account_for(USERS['jdoe'],'slack','TONE')=='TONE/UJANE'
    assert account_for(USERS['kim'],'slack','TONE') is None
    assert runtime.credential('TONE/UJANE')=='xoxe.xoxp-new'
    assert len(calls)==2 and store.get('TONE/UJANE')[2]['refresh_token']=='rotated'
    store.revoke('jdoe','TONE')
    assert store.account('jdoe','TONE')=='TONE/UJANE'
    with pytest.raises(OAuthUnavailable): runtime.credential('TONE/UJANE')

@pytest.mark.parametrize('returned_team,identity_team,success',[('TONE','TONE',True),('TTWO','TONE',False),('TONE','TTWO',False)])
def test_oauth_callback_validates_team_and_delegated_identity(installation,returned_team,identity_team,success):
    store,_=installation
    def reply(req):
        if req.url.path.endswith('auth.test'): return httpx.Response(200,json={'ok':True,'team_id':identity_team,'user_id':'UJANE'})
        return httpx.Response(200,json={'ok':True,'team':{'id':returned_team},'authed_user':{'id':'UJANE','access_token':'xoxp-private'}})
    oauth=SlackOAuth(store,['TONE'],'id','secret','https://brain.example/callback',httpx.Client(transport=httpx.MockTransport(reply)))
    state=parse_qs(urlparse(oauth.start('jdoe','TONE')).query)['state'][0]
    if success:
        assert oauth.finish('code',state)==('jdoe','TONE')
        assert store.get('TONE/UJANE')[2]['access_token']=='xoxp-private'
    else:
        with pytest.raises(OAuthUnavailable): oauth.finish('code',state)
        assert store.account('jdoe','TONE') is None

def test_multi_workspace_colliding_channel_ids_cannot_cross_read(tmp_path):
    connectors=[]
    for team in ('TONE','TTWO'):
        fake=FakeSlack();fake.team=team;fake.reply_pages=[[message(text=team+' confidential migration')]]
        connectors.append(SlackLiveConnector(team,['CDEMO'],'xoxp-ingestion',lambda account:'xoxp-asker',
            SlackEventStore(tmp_path/(team+'.db')),client=httpx.Client(transport=httpx.MockTransport(fake))))
    c=SlackWorkspaces(connectors)
    user=dataclasses.replace(USERS['jdoe'],accounts=(('slack:TONE','TONE/UJANE'),))
    first='TONE/CDEMO/1700000000.000001';second=first.replace('TONE','TTWO')
    assert 'TONE' in c.read_authorized(user,first).text
    assert not c.check(user,second).allowed and c.read_authorized(user,second) is None
    both=dataclasses.replace(user,accounts=(*user.accounts,('slack:TTWO','TTWO/UJANE')))
    assert 'TTWO' in c.read_authorized(both,second).text
    ids=[];token=None
    while True:
        page,token=c.list_page(token,1);ids+=page
        if token is None: break
    assert set(ids)=={first,second}
    assert not c.check(both,second.replace('TTWO','TOTHER')).allowed
    c.close()

def test_demo_credentials_cannot_access_live_sources(monkeypatch):
    from app import identity
    token=identity.login('jdoe','demo')
    assert identity.verify(token)
    monkeypatch.setenv('IB_SLACK_CONFIG','/configured/live-slack.json')
    assert identity.login('jdoe','demo') is None
    assert identity.verify(token) is None

def test_replay_reads_updated_content_and_preview_withholds(client,monkeypatch):
    headers=auth(client,'ravi')
    old=client.post('/api/ask',json={'question':'What are the steps in the payment-gateway failover runbook?'},headers=headers).json()
    main.brain().world.confluence_update('CONF-101','Final step: confirm recovery with the incident commander.',push=False)
    replayed=client.post('/api/history/'+old['query_id']+'/replay',headers=headers).json()
    assert 'confirm recovery with the incident commander' in replayed['answer']
    ref=replayed['citations'][0]['ref']
    monkeypatch.setattr(audit,'_store',lambda:DownStore())
    preview=client.get('/api/evidence/'+replayed['query_id']+'/'+ref,headers=headers)
    assert preview.status_code==503 and 'commander' not in preview.text

def test_strict_model_failure_is_timed_in_audit(brain,monkeypatch):
    monkeypatch.setenv('IB_LLM_REQUIRE_LIVE','1')
    with pytest.raises(llm.ModelUnavailable): brain.ask(USERS['jdoe'],'What is MIG-1?')
    records=audit.search(event='query_performance')
    assert records[0]['detail']['outcome']=='model_unavailable'
    assert records[0]['detail']['phases_ms']['total_ms']>0
    assert audit.search(event='model_measurement')[0]['detail']['mode']=='failed'

def test_workspace_configuration_and_shared_feed_are_isolated(tmp_path,monkeypatch):
    from .test_slack_runtime import config
    from app.slack_runtime import create_live_slack_from_env
    row,path=config(tmp_path,monkeypatch)
    second={**row,'team_id':'TSECOND','user_token_envs':{'TSECOND/UJANE':'TEST_SLACK_JANE'}}
    path.write_text(json.dumps({'workspaces':[row,second]}))
    c,receiver=create_live_slack_from_env()
    assert set(c.connectors)=={'TTEAM','TSECOND'}
    assert set(receiver.receivers)=={'TTEAM','TSECOND'}
    store=c.connectors['TTEAM'].store
    cursor=c.start_cursor()
    # Events for two installations share storage but not child connector feeds.
    with store._db() as db:
        db.execute('INSERT INTO slack_changes(native_id,kind,at) VALUES(?,?,?)',('TTEAM/CDEMO/1','upsert',1))
        db.execute('INSERT INTO slack_changes(native_id,kind,at) VALUES(?,?,?)',('TSECOND/CDEMO/1','upsert',1))
    seen=[]
    for _ in range(5):
        page=c.changes_since(cursor,1);cursor=page.next_cursor;seen.extend(ch.native_id for ch in page.changes)
        if not page.has_more: break
    assert sorted(seen)==['TSECOND/CDEMO/1','TTEAM/CDEMO/1']
    c.close()

def test_placeholder_live_evaluator_is_not_offline_success(tmp_path):
    import os,subprocess,sys
    from pathlib import Path
    root=Path(__file__).resolve().parents[1]
    config_file=tmp_path/'.env';config_file.write_text('IB_LLM_PROVIDER=openai_compatible\nIB_LLM_API_KEY=YOUR_KEY\nIB_LLM_MODEL=YOUR_MODEL\nIB_LLM_BASE_URL=YOUR_URL\n')
    environment={k:v for k,v in os.environ.items() if not k.startswith('IB_LLM_')}
    environment['IB_ENV_FILE']=str(config_file)
    report=tmp_path/'live.json'
    result=subprocess.run([sys.executable,str(root/'scripts/evaluate.py'),'--mode','live','--json',str(report)],env=environment,capture_output=True,text=True,timeout=20)
    assert result.returncode==2
    value=json.loads(report.read_text())
    assert value['status']=='not_run_missing_credentials' and not value['cases']

def test_multi_workspace_signature_cannot_be_reused_for_another_installation(tmp_path):
    import hashlib,hmac,time
    from app.sources.slack_multi import SlackWorkspaceEvents
    from app.sources.slack_events import SlackEventReceiver
    store=SlackEventStore(tmp_path/'signed.db');stamp=str(int(time.time()))
    receivers=[SlackEventReceiver(store,'secret-one','TONE',['CDEMO']),SlackEventReceiver(store,'secret-two','TTWO',['CDEMO'])]
    router=SlackWorkspaceEvents(receivers)
    body=json.dumps({'type':'event_callback','team_id':'TTWO','event_id':'EvONE','event':{'type':'message','channel':'CDEMO','ts':'1700000000.000001','text':'fixture'}}).encode()
    def headers(secret):
        return {'x-slack-request-timestamp':stamp,'x-slack-signature':'v0='+hmac.new(secret.encode(),b'v0:'+stamp.encode()+b':'+body,hashlib.sha256).hexdigest()}
    with pytest.raises(ValueError): router.receive(body,headers('secret-one'))
    assert store.changes_since('0').changes==[]
    router.receive(body,headers('secret-two'))
    assert all(ch.native_id.startswith('TTWO/') for ch in store.changes_since('0').changes)

def test_live_adversarial_cases_include_actual_answerable_model_calls():
    from evaluation.live_cases import LIVE_CASES
    answerable=[c for c in LIVE_CASES if c['category']=='live_adversarial' and not c['no_answer'] and not c.get('expected_blocked')]
    assert len(answerable)>=4 and all(c['expected_all'] for c in answerable)
