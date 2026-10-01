"""HTTP integration of optional live Slack, with no external credentials or calls."""
from unittest.mock import Mock

import pytest
from fastapi.testclient import TestClient
from app import server

from app import main
from app.sources.registry import build_connectors
from app.sources.world import World


def headers(client, username='dana'):
    # An authenticated test principal; live-mode UI login deliberately refuses demo credentials.
    from app import identity
    return {'Authorization': 'Bearer ' + identity.login(username, 'demo')}


@pytest.fixture
def live_app(monkeypatch):
    connector = build_connectors(World())['slack']
    connector.client = Mock()
    receiver = Mock()
    receiver.receive.return_value = {'ok': True, 'duplicate': False}
    worker = Mock()
    worker.stop.return_value = True
    worker.poll.return_value = {'slack': 1}
    worker.status.return_value = {'running': True}
    monkeypatch.setattr(main, 'create_live_slack_from_env', lambda: (connector, receiver))
    monkeypatch.setattr(main, 'SlackMaintenance', lambda *a, **k: worker)
    with TestClient(server.app) as client:
        yield client, receiver, worker
    worker.start.assert_called_once()
    worker.stop.assert_called_once()
    connector.client.close.assert_called_once()


def test_live_session_disables_mutations_and_shared_secret_slack_route(live_app):
    client, receiver, worker = live_app
    assert client.post('/api/login', json={'username':'dana','password':'demo'}).status_code == 403
    auth = headers(client)
    session = client.get('/api/session', headers=auth).json()
    assert session['source_mode'] == 'mixed'
    assert session['demo_mode'] is False
    assert client.post('/api/sim', headers=auth,
        json={'action':'slack_remove_member','target':'eng','value':'jdoe'}).status_code == 404
    assert client.post('/api/webhooks/slack', json={'native_id':'x'},
        headers={'x-webhook-secret':main.WEBHOOK_SECRET}).status_code == 404
    receiver.receive.assert_not_called()


def test_signed_route_passes_raw_bytes_and_only_wakes_after_durable_acceptance(live_app):
    client, receiver, worker = live_app
    raw = b'{ "type": "event_callback" }'
    result = client.post('/api/slack/events', content=raw, headers={'x-slack-signature':'v0=test'})
    assert result.status_code == 200
    assert receiver.receive.call_args.args[0] == raw
    assert receiver.receive.call_args.args[1]['x-slack-signature'] == 'v0=test'
    worker.wake.assert_called_once()
    worker.poll.assert_not_called()


@pytest.mark.parametrize('failure,status', [(ValueError('private detail'),400), (RuntimeError('secret'),503)])
def test_invalid_or_unpersisted_events_are_not_acknowledged(live_app, failure, status):
    client, receiver, worker = live_app
    receiver.receive.side_effect = failure
    result = client.post('/api/slack/events', content=b'{}')
    assert result.status_code == status
    assert 'private detail' not in result.text and 'secret' not in result.text
    worker.wake.assert_not_called()


def test_challenges_do_not_start_source_reads(live_app):
    client, receiver, worker = live_app
    receiver.receive.return_value = {'challenge':'hello'}
    assert client.post('/api/slack/events', content=b'{}').json() == {'challenge':'hello'}
    worker.wake.assert_not_called()


def test_slack_event_size_limit_precedes_signature_and_json(live_app):
    client, receiver, worker = live_app
    assert client.post('/api/slack/events', content=b'x'*1_000_001).status_code == 413
    receiver.receive.assert_not_called()
    worker.wake.assert_not_called()


def test_operational_counts_are_admin_only_and_poll_is_serialized(live_app):
    client, receiver, worker = live_app
    employee = headers(client, 'jdoe')
    assert client.get('/api/freshness', headers=employee).status_code == 403
    assert client.get('/api/slack/maintenance', headers=employee).status_code == 403
    admin = headers(client)
    assert client.post('/api/sync/poll', headers=admin).json() == {'slack':1}
    worker.poll.assert_called_once_with()
    assert client.get('/api/slack/maintenance', headers=admin).json()['running']


def test_unconfigured_slack_endpoint_is_absent(monkeypatch):
    monkeypatch.setattr(main, 'create_live_slack_from_env', lambda: None)
    with TestClient(server.app) as client:
        assert client.post('/api/slack/events', content=b'{}').status_code == 404
        assert client.get('/api/session', headers=headers(client,'jdoe')).json()['source_mode'] == 'simulated'
