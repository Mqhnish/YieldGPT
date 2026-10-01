"""Regressions discovered while checking the complete challenge brief."""
import json

import httpx

from app import audit, llm
from app.evidence import assemble
from app.grounding import NEUTRAL_NO_ANSWER
from app.identity import USERS


def test_three_link_hops_stitch_all_four_platforms(brain, monkeypatch):
    # Only the seed mentions MIG-1. Each additional item requires another hop.
    brain.world.issues['MIG-1']['links'] = ['confluence:CONF-102']
    brain.world.pages['CONF-102']['links'] = ['gdrive:DRV-3']
    brain.world.files['DRV-3']['links'] = ['slack:T0VENDOR/vendor-collab/5001']
    brain.syncer.full_load()
    response = brain.ask(USERS['jdoe'], 'MIG-1')
    contexts = audit.search(query_id=response['query_id'], event='context_assembled')
    uids = {s['uid'] for e in contexts for s in e['detail']['context']}
    assert {'jira:MIG-1','confluence:CONF-102','gdrive:DRV-3','slack:T0VENDOR/vendor-collab/5001'} <= uids
    assert {c['platform'] for c in response['citations']} == {'jira','confluence','gdrive','slack'}


def test_denied_intermediate_stops_link_traversal(brain):
    brain.world.issues['MIG-1']['links'] = ['confluence:CONF-102']
    brain.world.pages['CONF-102']['links'] = ['gdrive:DRV-3']
    brain.world.pages['CONF-102']['restrict'] = {'user:asha'}
    brain.world.files['DRV-3']['links'] = ['slack:T0VENDOR/vendor-collab/5001']
    brain.syncer.full_load()
    response = brain.ask(USERS['jdoe'], 'MIG-1')
    contexts = audit.search(query_id=response['query_id'], event='context_assembled')
    uids = {s['uid'] for e in contexts for s in e['detail']['context']}
    assert not uids & {'confluence:CONF-102','gdrive:DRV-3','slack:T0VENDOR/vendor-collab/5001'}


def extended_runbook(brain):
    for i in range(5,13):
        brain.world.confluence_update('CONF-101', f'Step {i}: Verify recovery checkpoint {i}.', push=False)
    brain.world.confluence_update('CONF-101', 'Step 13: Fail over to the secondary gateway if recovery fails.', push=False)


def test_missed_update_late_runbook_steps_survive_context_and_answer_caps(brain):
    extended_runbook(brain)
    response = brain.ask(USERS['ravi'], "What's the latest runbook for the payment-service incident?")
    for i in range(1,14):
        assert f'Step {i}:' in response['answer']
    assert response['answer'].index('Step 1:') < response['answer'].index('Step 13:')
    assert 'secondary gateway' in response['answer']


def test_model_cannot_drop_late_steps_from_requested_procedure(brain, monkeypatch):
    extended_runbook(brain)
    source = brain.connectors['confluence'].fetch('CONF-101')
    sources = assemble('Show the runbook steps', [(10,source)])
    selection = {'selections':[{'source':'S1','passage':sources[0]['passages'][0]['id']}]}
    transport = httpx.MockTransport(lambda r: httpx.Response(200,
        json={'choices':[{'message':{'content':json.dumps(selection)}}]}))
    Client = httpx.Client
    monkeypatch.setattr(llm.httpx, 'Client', lambda **kw: Client(transport=transport, **kw))
    monkeypatch.setattr(llm, 'LLM_PROVIDER', 'openai_compatible')
    monkeypatch.setattr(llm, 'LLM_BASE_URL', 'https://model.example/v1')
    monkeypatch.setattr(llm, 'LLM_API_KEY', 'test-key')
    monkeypatch.setattr(llm, 'LLM_MODEL', 'test-model')
    answer = llm.complete('Show the runbook steps', sources, 'ravi')
    assert answer.mode == 'model_selected'
    assert 'Step 13:' in answer
    assert answer.index('Step 1:') < answer.index('Step 13:')


def test_oversized_procedure_abstains_instead_of_silently_omitting_actions(brain):
    for i in range(5,100):
        brain.world.confluence_update('CONF-101', f'Step {i}: Check recovery checkpoint {i} before proceeding.', push=False)
    response = brain.ask(USERS['ravi'], 'Show every step of the payment-service incident runbook')
    assert response['answer'] == NEUTRAL_NO_ANSWER
    assert response['citations'] == []


def test_final_preview_permission_check_is_audited(brain):
    response = brain.ask(USERS['jdoe'], 'MIG-1')
    brain.evidence(USERS['jdoe'], response['query_id'], response['citations'][0]['ref'])
    events = audit.search(query_id=response['query_id'], event='authz_decision')
    assert any(e['detail'].get('evidence_preview') and e['detail'].get('phase') == 'after_read' for e in events)
