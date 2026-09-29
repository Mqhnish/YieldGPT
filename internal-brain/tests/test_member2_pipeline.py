"""Security and quality regressions at Member 1/2/3 integration boundaries."""
import copy
import dataclasses
import json
from concurrent.futures import ThreadPoolExecutor
from unittest.mock import Mock

import httpx
import pytest
from fastapi.testclient import TestClient

from app import audit, grounding, llm, main, planner
from app.evidence import EvidenceCache, EvidenceUnavailable, assemble, model_source, passages
from app.identity import USERS
from app.index import Index
from app.sources.base import Decision, PermissionResult, SourceDoc, SourceUnavailable

Q = "What's the status of the database migration project and were there any blockers raised in Slack last week?"


def doc(uid='confluence:test', text='Database migration is not approved.', **kwargs):
    defaults = dict(uid=uid, platform=uid.split(':')[0], native_id=uid.split(':',1)[1], tenant='company-a',
                    container='eng', title='Database migration', text=text, url='https://company.example/test',
                    version='1', updated_at=1790000000.0)
    defaults.update(kwargs)
    return SourceDoc(**defaults)


def test_exact_identifier_works_even_without_two_words(ask):
    response = ask('jdoe', 'MIG-7')
    assert any(c['uid'] == 'jira:MIG-7' for c in response['citations'])
    assert '40 seconds' in response['answer']


def test_one_incidental_word_does_not_retrieve_unrelated_runbook(ask):
    response = ask('jdoe', Q)
    assert not any(c['uid'] == 'confluence:CONF-101' for c in response['citations'])


def test_planner_searches_all_sources_unless_explicitly_limited():
    assert planner.plan('Show the migration ticket').platforms == planner.ALL
    assert planner.plan('search only Slack for database migration').platforms == {'slack'}
    assert planner.plan('only in Jira MIG-7').platforms == {'jira'}


def test_time_window_is_deterministic_and_does_not_expire_manuals():
    result = planner.plan('migration discussions in the past 2 days', now=1000000)
    assert result.since == {'slack': 827200}
    assert result.until == {'slack': 1000000}
    assert 'confluence' not in result.since


def test_explicit_source_limit_also_applies_to_link_expansion(ask):
    response = ask('jdoe', 'search only Jira MIG-1 database migration')
    assert response['citations']
    assert {c['platform'] for c in response['citations']} == {'jira'}


def test_denied_record_cannot_displace_authorized_results(brain):
    before = brain.ask(USERS['jdoe'], Q)
    brain.world.pages['HIDDEN-1'] = dict(space='security', parent=None, restrict=None, updated=1790000000,
        title='Database migration blockers ' * 80, body=('database migration blockers slack project status ' * 500), links=[])
    brain.syncer.on_webhook('confluence','HIDDEN-1')
    after = brain.ask(USERS['jdoe'], Q)
    assert before['answer'] == after['answer']
    assert before['citations'] == after['citations']


def test_same_question_hidden_present_vs_absent_has_same_visible_result(brain):
    question = 'Show the Q3 breach incident report'
    present = brain.ask(USERS['kim'], question)
    brain.world.delete('confluence','CONF-103',push=True)
    brain.world.delete('jira','SEC-4',push=True)
    absent = brain.ask(USERS['kim'], question)
    for key in ('answer','citations','status','quality','plan'):
        assert present[key] == absent[key]


def test_links_from_denied_parent_are_not_expanded(brain, monkeypatch):
    brain.world.pages['CONF-103']['links'].append('gdrive:DRV-3')
    brain.syncer.on_webhook('confluence','CONF-103')
    seen = []
    original = llm.complete
    monkeypatch.setattr(llm,'complete',lambda q,s,a: (seen.extend(s),original(q,s,a))[1])
    brain.ask(USERS['kim'],'Q3 breach incident report')
    assert not any(s['uid'] == 'gdrive:DRV-3' for s in seen)


def test_update_during_generation_discards_stale_answer(brain, monkeypatch):
    real, calls = llm.complete, []
    def change(q, s, a):
        calls.append(s)
        if len(calls) == 1:
            brain.world.jira_update('MIG-1', status='Done', push=False)
        return real(q,s,a)
    monkeypatch.setattr(llm,'complete',change)
    response = brain.ask(USERS['jdoe'], Q)
    assert all(c['uid'] != 'jira:MIG-1' for c in response['citations'])
    assert audit.search(query_id=response['query_id'], event='answer_discarded')


def test_long_first_source_cannot_bypass_context_budget():
    long = doc(text=('Migration approved. ' * 3000))
    sources = assemble('migration approved', [(10,long)], budget=650)
    payload = json.dumps([model_source(s) for s in sources], ensure_ascii=False)
    assert len(payload) <= 650
    assert all(p['text'] in long.text for s in sources for p in s['passages'])


def test_long_unpunctuated_claim_is_never_silently_clipped():
    assert passages('word ' * 3000) == []


def test_passage_offsets_reference_exact_snapshot():
    text = '  Step 1: No action.\nStep 2: Wait 1.5 seconds. Then proceed.'
    for p in passages(text):
        assert text[p['start']:p['end']] == p['text']


def test_index_upsert_uses_snapshot_and_removes_old_postings():
    index, source = Index(), doc(text='Database migration alpha.')
    index.upsert(source, {'anyone'})
    source.text = 'Database migration beta.'
    assert 'alpha' in index.get(source.uid).doc.text
    index.upsert(source, {'anyone'})
    assert index.search('alpha', {'confluence'}) == []
    assert index.search('beta', {'confluence'})
    index.remove(source.uid)
    assert index.search('beta', {'confluence'}) == []


def test_index_concurrent_reads_and_writes():
    index = Index()
    def work(i):
        d = doc(uid=f'confluence:doc-{i}', text=f'Database migration batch {i}.')
        index.upsert(d, {'anyone'})
        index.search('database migration', {'confluence'})
        if i % 2:
            index.remove(d.uid)
    with ThreadPoolExecutor(max_workers=4) as pool:
        list(pool.map(work, range(60)))
    assert len(index) == 30


@pytest.mark.parametrize('claim', [
    'The migration is approved. [S1]',
    'The migration is not approved. [S9]',
    'The migration is not approved. [S1][S9]',
    'Revenue doubled.\nThe migration is approved. [S1]',
    'Migration approved. [S1]',
])
def test_grounding_rejects_negation_loss_and_unknown_refs(claim):
    source = {'ref':'S1','title':'Approval','text':'The migration is not approved.'}
    answer, stats = grounding.enforce(claim,[source])
    assert answer == grounding.NEUTRAL_NO_ANSWER
    assert stats['dropped']


def test_grounding_removes_short_uncited_claim_even_next_to_valid_one():
    answer, _ = grounding.enforce('Revenue doubled.\nThe migration is not approved. [S1]',
        [{'ref':'S1','text':'The migration is not approved.','title':'Approval'}])
    assert answer == 'The migration is not approved. [S1]'


@pytest.mark.parametrize('claim', ['The outage lasted 74 minutes. [S1]', 'Cutover is on 21 October. [S1]'])
def test_grounding_rejects_changed_numbers_dates(claim):
    answer, _ = grounding.enforce(claim, [{'ref':'S1','title':'Plan',
        'text':'The outage lasted 47 minutes. Cutover is on 20 October.'}])
    assert answer == grounding.NEUTRAL_NO_ANSWER


def test_grounding_keeps_contradictions_attributed_instead_of_reconciling():
    sources = [{'ref':'S1','text':'The migration is approved.','title':'Old note'},
               {'ref':'S2','text':'The migration is not approved.','title':'New note'}]
    text, stats = grounding.enforce('The migration is approved. [S1]\nThe migration is not approved. [S2]', sources)
    assert stats['kept'] == 2 and '[S1]' in text and '[S2]' in text


def test_evidence_actor_scope_revocation_and_version_recheck(brain):
    result = brain.ask(USERS['jdoe'], Q)
    ref = next(c['ref'] for c in result['citations'] if c['uid'] == 'slack:db-migration/2001')
    assert brain.evidence(USERS['jdoe'],result['query_id'],ref)['passages']
    with pytest.raises(EvidenceUnavailable):
        brain.evidence(USERS['kim'],result['query_id'],ref)
    brain.world.slack_remove_member('db-migration','jdoe',push=False)
    with pytest.raises(EvidenceUnavailable):
        brain.evidence(USERS['jdoe'],result['query_id'],ref)


def test_evidence_does_not_serve_old_version(brain):
    result = brain.ask(USERS['jdoe'], 'MIG-1')
    ref = next(c['ref'] for c in result['citations'] if c['uid'] == 'jira:MIG-1')
    brain.world.jira_update('MIG-1', status='Done', push=False)
    with pytest.raises(EvidenceUnavailable):
        brain.evidence(USERS['jdoe'],result['query_id'],ref)


def test_evidence_cache_expiry_and_size():
    clock = [0]
    cache = EvidenceCache(ttl=5, max_queries=1, clock=lambda:clock[0])
    cache.put('jane','q1',[{'ref':'S1'}])
    cache.put('jane','q2',[{'ref':'S1'}])
    with pytest.raises(EvidenceUnavailable): cache.get('jane','q1','S1')
    clock[0] = 6
    with pytest.raises(EvidenceUnavailable): cache.get('jane','q2','S1')


def test_model_payload_contains_only_approved_evidence_no_internal_objects(brain,monkeypatch):
    original = llm.complete
    payloads = []
    def inspect(q,s,a):
        payloads.append(llm.build_messages(q,s,a))
        return original(q,s,a)
    monkeypatch.setattr(llm,'complete',inspect)
    brain.ask(USERS['jdoe'],Q)
    serialized = json.dumps(payloads)
    assert 'licence' not in serialized and 'mig-leads' not in serialized
    assert 'platform_account' not in serialized and 'PermissionResult' not in serialized


def test_model_failure_is_explicit_fallback(monkeypatch):
    monkeypatch.setattr(llm,'LLM_PROVIDER','openai_compatible')
    monkeypatch.setattr(llm,'LLM_API_KEY','')
    source = assemble('migration',[(1,doc())])
    value = llm.complete('migration',source,'Jane')
    assert value.mode == 'extractive_fallback' and 'not approved' in value


def _mock_model(monkeypatch, response_factory):
    real_client = httpx.Client
    transport = httpx.MockTransport(response_factory)
    monkeypatch.setattr(llm.httpx,'Client',lambda **kw:real_client(transport=transport,**kw))
    for name,value in [('LLM_PROVIDER','openai_compatible'),('LLM_BASE_URL','https://model.example/v1'),
                       ('LLM_MODEL','test-model'),('LLM_API_KEY','SECRET')]:
        monkeypatch.setattr(llm,name,value)


def test_live_model_selects_passages_and_server_renders_facts(monkeypatch):
    sources = assemble('migration',[(1,doc())])
    def reply(request):
        payload = json.loads(request.content)
        assert payload['model'] == 'test-model'
        evidence = json.loads(payload['messages'][1]['content'])['sources'][0]
        selection = {'selections':[{'source':evidence['ref'],'passage':evidence['passages'][0]['id']}]}
        return httpx.Response(200,json={'choices':[{'message':{'content':json.dumps(selection)}}]})
    _mock_model(monkeypatch,reply)
    value = llm.complete('migration',sources,'Jane')
    assert value.mode == 'model_selected' and value == 'Database migration is not approved. [S1]'


@pytest.mark.parametrize('content', ['{"selections":[{"source":"S999","passage":"p-x"}]}',
                                    '{"answer":"Migration approved"}', 'not json'])
def test_invalid_model_response_cannot_invent_claims(monkeypatch,content):
    _mock_model(monkeypatch,lambda r:httpx.Response(200,json={'choices':[{'message':{'content':content}}]}))
    value = llm.complete('migration',assemble('migration',[(1,doc())]),'Jane')
    assert value.mode == 'extractive_fallback'
    assert 'not approved' in value and 'SECRET' not in value


def test_api_limits_session_evidence_and_cache_headers():
    with TestClient(main.app) as client:
        token = client.post('/api/login',json={'username':'jdoe','password':'demo'}).json()['token']
        headers = {'Authorization':'Bearer '+token}
        for question in (' ', 'a'*2001):
            assert client.post('/api/ask',json={'question':question},headers=headers).status_code == 422
        assert client.get('/api/session',headers=headers).json()['user']['username'] == 'jdoe'
        response = client.post('/api/ask',json={'question':Q},headers=headers)
        assert response.headers['cache-control'] == 'no-store, private'
        value = response.json()
        citation = value['citations'][0]
        endpoint = f"/api/evidence/{value['query_id']}/{citation['ref']}"
        assert client.get(endpoint,headers=headers).status_code == 200
        assert client.get(endpoint).status_code == 401
        assert client.get('/api/evidence/nonexistent/S1',headers=headers).status_code == 404


def test_audit_failure_prevents_answer_delivery(brain, monkeypatch):
    original = brain._log
    def fail_on_answer(actor,event,**kw):
        if event == 'answer_returned': raise OSError('audit unavailable')
        return original(actor,event,**kw)
    brain._log = fail_on_answer
    with pytest.raises(OSError): brain.ask(USERS['jdoe'],Q)
