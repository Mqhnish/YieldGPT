"""Workspace-isolated Slack dispatch, cursors, and event verification."""
import json
import time
from types import SimpleNamespace
from .base import Connector, Decision, PermissionResult, ChangePage, SourceUnavailable


class SlackWorkspaces(Connector):
    platform = 'slack'
    tenant = 'multi-workspace'

    def __init__(self, connectors):
        self.connectors = {c.tenant:c for c in connectors}
        if len(self.connectors) != len(connectors) or not connectors:
            raise ValueError('Slack workspace IDs must be unique')
        self.teams = tuple(sorted(self.connectors))
        self.client = SimpleNamespace(close=self.close)

    def close(self):
        for c in self.connectors.values():
            c.client.close()

    def _source(self, native_id):
        return self.connectors.get(native_id.split('/',1)[0]) if isinstance(native_id,str) else None

    def check(self, user, native_id):
        c = self._source(native_id)
        if not c:
            return PermissionResult(Decision.DENIED,'not_found','resource unavailable',time.time(),'')
        return c.check(user,native_id)

    def _check(self, user, account, native_id):
        raise NotImplementedError('check delegates to the matching native workspace')

    def fetch(self,native_id):
        c=self._source(native_id)
        return c.fetch(native_id) if c else None

    def read_authorized(self,user,native_id):
        c=self._source(native_id)
        return c.read_authorized(user,native_id) if c else None

    def acl_hint(self,native_id):
        c=self._source(native_id)
        return c.acl_hint(native_id) if c else set()

    def start_cursor(self):
        return json.dumps({'workspaces':{t:self.connectors[t].start_cursor() for t in self.teams},'next':0},sort_keys=True)

    def _cursor(self,cursor):
        try:
            value=json.loads(cursor)
            if set(value['workspaces']) != set(self.teams) or type(value['next']) is not int or not 0 <= value['next'] < len(self.teams):
                raise ValueError()
            return value
        except (ValueError,KeyError,TypeError):
            raise SourceUnavailable('Invalid Slack workspace cursor') from None

    def changes_since(self,cursor,page_size=100):
        state=self._cursor(cursor)
        for offset in range(len(self.teams)):
            index=(state['next']+offset)%len(self.teams)
            team=self.teams[index]
            page=self.connectors[team].changes_since(state['workspaces'][team],page_size)
            state['workspaces'][team]=page.next_cursor
            if page.changes or page.has_more:
                state['next']=(index+1)%len(self.teams)
                # One extra empty pass establishes quiescence across all workspaces.
                return ChangePage(page.changes,json.dumps(state,sort_keys=True),True)
        return ChangePage([],json.dumps(state,sort_keys=True),False)

    def list_page(self,page_token=None,page_size=50):
        if type(page_size) is not int or not 1 <= page_size <= 1000:
            raise ValueError('Invalid Slack page size')
        try:
            state=json.loads(page_token) if page_token else {'team':0,'cursor':None,'teams':list(self.teams)}
            if state['teams'] != list(self.teams) or type(state['team']) is not int or not 0 <= state['team'] < len(self.teams):
                raise ValueError()
        except (ValueError,TypeError,KeyError):
            raise SourceUnavailable('Invalid Slack crawl cursor') from None
        result=[]
        while len(result)<page_size and state['team']<len(self.teams):
            c=self.connectors[self.teams[state['team']]]
            ids,following=c.list_page(state['cursor'],page_size-len(result))
            result.extend(ids)
            if following:
                state['cursor']=following
                break
            state['team']+=1
            state['cursor']=None
        return result,json.dumps(state) if state['team']<len(self.teams) else None

    def reconcile(self):
        total=0
        failures=[]
        for c in self.connectors.values():
            try:
                total+=c.reconcile()
            except Exception:
                failures.append(c.tenant)
        if failures:
            raise SourceUnavailable('One or more Slack reconciliations failed')
        return total


class SlackWorkspaceEvents:
    def __init__(self,receivers):
        self.receivers={r.team_id:r for r in receivers}

    def receive(self,body,headers):
        if len(body)>1_000_000:
            raise ValueError('Slack event too large')
        try:
            value=json.loads(body)
            if not isinstance(value,dict):
                raise ValueError()
        except (ValueError,RecursionError):
            raise ValueError('Invalid Slack event') from None
        # Workspace IDs select a verifier, not authorization. Only that verifier
        # may persist the event after checking its installation-specific signature.
        if value.get('type')=='url_verification':
            for receiver in self.receivers.values():
                try:
                    return receiver.receive(body,headers)
                except ValueError:
                    continue
            raise ValueError('Invalid Slack challenge')
        receiver=self.receivers.get(value.get('team_id'))
        if receiver is None:
            raise ValueError('Unknown Slack installation')
        return receiver.receive(body,headers)
