"""Mandatory Slack lifecycle contract; uses the same public adapter boundary.
Live fixtures can override slack_environment with a disposable test installation.
"""
import pytest
from app.identity import USERS
from app.sources.registry import build_connectors
from app.sources.world import World


@pytest.fixture
def slack_environment():
    world=World()
    return world,build_connectors(world)['slack']


def test_message_edit_and_delete_change_version_and_remove_old_content(slack_environment):
    fixture,c=slack_environment
    nid='T0COMPANYA/db-migration/2001'
    original=c.fetch(nid)
    cursor=c.start_cursor()
    fixture.slack_edit_message(nid,0,'Replacement message: migration not approved.',push=False)
    edited=c.fetch(nid)
    assert edited.version!=original.version
    assert 'Replacement message' in edited.text and '40s' not in edited.text
    fixture.slack_delete_message(nid,1,push=False)
    remaining=c.fetch(nid)
    assert remaining.version!=edited.version and 'prototype' not in remaining.text
    changes=c.changes_since(cursor).changes
    assert len(changes)==2 and all(ch.native_id==nid for ch in changes)
    fixture.slack_delete_message(nid,0,push=False)
    assert c.fetch(nid) is None
    assert not c.check(USERS['jdoe'],nid).allowed


def test_retention_drops_individual_messages_then_whole_thread(slack_environment):
    import time
    fixture,c=slack_environment
    nid='T0COMPANYA/db-migration/2001'
    fixture.channels['db-migration']['retention_days']=1
    now=time.time()
    fixture.threads[nid]['msgs']=[('ravi',now-2*86400,'Expired private fact'),('jdoe',now,'Current reply')]
    assert 'Expired' not in c.fetch(nid).text
    assert 'Current reply' in c.fetch(nid).text
    fixture.threads[nid]['msgs'].pop()
    assert c.fetch(nid) is None
    assert not c.check(USERS['jdoe'],nid).allowed


def test_default_fixture_ids_are_workspace_scoped(slack_environment):
    _,c=slack_environment
    token=None
    while True:
        ids,token=c.list_page(token,2)
        for nid in ids:
            doc=c.fetch(nid)
            assert nid.startswith(doc.tenant+'/')
            assert doc.uid=='slack:'+nid
        if not token:
            break

# The same actor/scope/lifecycle assertions exercise both implementations. The
# HTTP fixture controls a fake workspace; it is contract evidence, not a live run.
@pytest.fixture(params=['simulated','live_http','multi_workspace_http'])
def slack_contract(request,tmp_path):
    import dataclasses
    import httpx
    from types import SimpleNamespace
    from app.sources.slack_live import SlackLiveConnector
    from app.sources.slack_multi import SlackWorkspaces
    from app.sources.slack_events import SlackEventStore
    from tests.test_slack_member2 import FakeSlack,message
    if request.param=='simulated':
        w=World();c=build_connectors(w)['slack'];now=__import__('time').time()
        w.channels['dm-contract']=dict(workspace='T0COMPANYA',private=True,is_im=True,
            member_accounts={'T0COMPANYA/U0JDOE'},retention_days=1)
        w.threads['T0COMPANYA/dm-contract/1']=dict(ts=now,msgs=[('jdoe',now,'Migration is not approved.')])
        w.channels['public-contract']=dict(workspace='T0COMPANYA',private=False,public_read=True,
            workspace_accounts={'T0COMPANYA/U0JDOE'},member_accounts=set(),retention_days=1)
        w.threads['T0COMPANYA/public-contract/1']=dict(ts=now,msgs=[('jdoe',now,'Migration is not approved.')])
        def edit(nid): w.slack_edit_message(nid,0,'Migration is approved.',push=False)
        def delete(nid): w.slack_delete_message(nid,0,push=False)
        def expire(nid): w.threads[nid]['msgs']=[('jdoe',now-172800,'Expired secret')]
        def revoke(nid):
            ch=w.channels[nid.split('/')[1]];ch['member_accounts']=set();ch['workspace_accounts']=set()
        return SimpleNamespace(c=c,allowed=USERS['jdoe'],denied=USERS['kim'],ids=['T0COMPANYA/dm-contract/1','T0COMPANYA/public-contract/1'],edit=edit,delete=delete,expire=expire,revoke=revoke)
    fake=FakeSlack()
    c=SlackLiveConnector('TTEAM',['CDEMO','DDEMO'],'xoxp-ingestion',lambda account:'xoxp-asker' if account=='TTEAM/UJANE' else None,
        SlackEventStore(tmp_path/'contract.db'),client=httpx.Client(transport=httpx.MockTransport(fake)))
    if request.param=='multi_workspace_http': c=SlackWorkspaces([c])
    user=dataclasses.replace(USERS['jdoe'],accounts=(('slack:TTEAM','TTEAM/UJANE'),))
    def edit(nid): fake.reply_pages=[[message(text='Migration is approved.')]]
    def delete(nid): fake.reply_pages=[[]] # Slack omits deleted/retention-expired content.
    def revoke(nid): fake.denied=True
    return SimpleNamespace(c=c,allowed=user,denied=USERS['kim'],ids=['TTEAM/DDEMO/1700000000.000001','TTEAM/CDEMO/1700000000.000001'],edit=edit,delete=delete,expire=delete,revoke=revoke)

@pytest.mark.parametrize('kind',[0,1],ids=['dm','public_by_scope'])
def test_shared_slack_dm_and_public_scope_contract(slack_contract,kind):
    f=slack_contract;nid=f.ids[kind]
    assert f.c.check(f.allowed,nid).allowed
    assert not f.c.check(f.denied,nid).allowed
    assert f.c.read_authorized(f.denied,nid) is None
    f.revoke(nid)
    assert not f.c.check(f.allowed,nid).allowed
    assert f.c.read_authorized(f.allowed,nid) is None

def test_shared_slack_message_edit_delete_contract(slack_contract):
    f=slack_contract;nid=f.ids[0]
    before=f.c.read_authorized(f.allowed,nid)
    f.edit(nid)
    after=f.c.read_authorized(f.allowed,nid)
    assert after.version!=before.version and 'not approved' not in after.text
    assert 'approved' in after.text
    f.delete(nid)
    assert f.c.read_authorized(f.allowed,nid) is None
    assert not f.c.check(f.allowed,nid).allowed

def test_shared_slack_retention_expiry_contract(slack_contract):
    f=slack_contract;nid=f.ids[0]
    assert f.c.read_authorized(f.allowed,nid)
    f.expire(nid)
    assert f.c.read_authorized(f.allowed,nid) is None
    assert not f.c.check(f.allowed,nid).allowed
