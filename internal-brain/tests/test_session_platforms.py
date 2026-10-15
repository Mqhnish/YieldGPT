"""/api/session tells the UI which platforms are real, so it links only to pages that exist."""
from app import main


def test_platform_modes_follow_configuration(monkeypatch):
    monkeypatch.setattr(main.config, 'ATLASSIAN_MODE', 'live')
    modes = main._platform_modes(None, None)
    assert modes == {'confluence': 'live', 'jira': 'live', 'slack': 'demo', 'gdrive': 'demo'}
    assert main._source_mode(modes) == 'mixed'
    monkeypatch.setattr(main.config, 'ATLASSIAN_MODE', 'fixture')
    assert main._source_mode(main._platform_modes(None, None)) == 'simulated'
    assert main._source_mode(main._platform_modes(object(), object())) == 'mixed'
    monkeypatch.setattr(main.config, 'ATLASSIAN_MODE', 'live')
    assert main._source_mode(main._platform_modes(object(), object())) == 'live'


def test_session_reports_platforms():
    from fastapi.testclient import TestClient
    from app import server
    with TestClient(server.app) as client:
        token = client.post('/api/login', json={'username': 'jdoe', 'password': 'demo'}).json()['token']
        session = client.get('/api/session', headers={'Authorization': f'Bearer {token}'}).json()
    assert set(session['platforms']) == {'confluence', 'jira', 'slack', 'gdrive'}
    assert set(session['platforms'].values()) <= {'live', 'demo'}
