"""Encrypted, actor/workspace-bound delegated installations and OAuth state.
No token is returned through a browser API. Scopes remain read-only.
"""
from contextlib import contextmanager
import base64
import hashlib
import json
import os
from pathlib import Path
import re
import secrets
import sqlite3
import threading
import time
from urllib.parse import urlencode, urlparse

import httpx
from cryptography.hazmat.primitives.ciphers.aead import AESGCM
from .config import DATA_DIR


class OAuthUnavailable(RuntimeError):
    pass


class InstallationStore:
    def __init__(self,path,key,clock=time.time):
        try:
            key=base64.urlsafe_b64decode(key)
            if len(key)!=32:
                raise ValueError()
        except Exception:
            raise ValueError('Slack token encryption requires a base64-encoded 32-byte key') from None
        self.path,self.aes,self.clock=Path(path),AESGCM(key),clock
        self.path.parent.mkdir(parents=True,exist_ok=True)
        fd=os.open(self.path,os.O_CREAT|os.O_RDWR,0o600);os.close(fd)
        with self.db() as c:
            c.executescript('''CREATE TABLE IF NOT EXISTS installations(
              actor TEXT, team TEXT, account TEXT UNIQUE, nonce BLOB, sealed BLOB,
              PRIMARY KEY(actor,team));
              CREATE TABLE IF NOT EXISTS oauth_states(digest TEXT PRIMARY KEY, actor TEXT, team TEXT, expires REAL);''')
    @contextmanager
    def db(self):
        connection = sqlite3.connect(self.path, timeout=10)
        try:
            with connection:
                yield connection
        finally:
            connection.close()
    def issue_state(self,actor,team):
        value=secrets.token_urlsafe(32)
        with self.db() as c:
            c.execute('DELETE FROM oauth_states WHERE expires<?',(self.clock(),))
            c.execute('INSERT INTO oauth_states VALUES(?,?,?,?)',(hashlib.sha256(value.encode()).hexdigest(),actor,team,self.clock()+300))
        return value
    def consume_state(self,value):
        if not isinstance(value,str) or not 20<=len(value)<=200:
            raise OAuthUnavailable('OAuth state is invalid or expired')
        digest=hashlib.sha256(value.encode()).hexdigest()
        with self.db() as c:
            c.execute('BEGIN IMMEDIATE')
            row=c.execute('SELECT actor,team,expires FROM oauth_states WHERE digest=?',(digest,)).fetchone()
            c.execute('DELETE FROM oauth_states WHERE digest=?',(digest,))
        if not row or row[2]<self.clock():
            raise OAuthUnavailable('OAuth state is invalid or expired')
        return row[0],row[1]
    def put(self,actor,team,account,credential):
        if not re.fullmatch(r'T[A-Z0-9]+/[UW][A-Z0-9]+',account) or not account.startswith(team+'/'):
            raise OAuthUnavailable('Invalid delegated account')
        nonce=secrets.token_bytes(12)
        aad=json.dumps([actor,team,account]).encode()
        sealed=self.aes.encrypt(nonce,json.dumps(credential).encode(),aad)
        try:
            with self.db() as c:
                c.execute('INSERT INTO installations VALUES(?,?,?,?,?) ON CONFLICT(actor,team) DO UPDATE SET account=excluded.account,nonce=excluded.nonce,sealed=excluded.sealed',
                          (actor,team,account,nonce,sealed))
        except sqlite3.IntegrityError:
            raise OAuthUnavailable('Delegated account is already linked') from None
    def account(self,actor,team):
        with self.db() as c:
            row=c.execute('SELECT account FROM installations WHERE actor=? AND team=?',(actor,team)).fetchone()
        return row[0] if row else None
    def get(self,account):
        with self.db() as c:
            row=c.execute('SELECT actor,team,nonce,sealed FROM installations WHERE account=?',(account,)).fetchone()
        if not row:
            return None
        try:
            credential=json.loads(self.aes.decrypt(row[2],row[3],json.dumps([row[0],row[1],account]).encode()))
            return row[0],row[1],credential
        except Exception:
            raise OAuthUnavailable('Delegated credential could not be decrypted') from None
    def revoke(self,actor,team):
        with self.db() as c:
            row = c.execute('SELECT account FROM installations WHERE actor=? AND team=?',(actor,team)).fetchone()
        if row:
            # Retain the binding as a tombstone so environment credentials cannot revive it.
            self.put(actor, team, row[0], {'revoked': True})


class SlackOAuth:
    def __init__(self,store,teams,client_id,client_secret,redirect_uri,client=None):
        parsed=urlparse(redirect_uri)
        if (not client_id or not client_secret or not parsed.hostname or parsed.username or parsed.password
            or parsed.query or parsed.fragment or (parsed.scheme!='https' and not (parsed.scheme=='http' and parsed.hostname in {'127.0.0.1','localhost'}))):
            raise ValueError('Invalid Slack OAuth configuration')
        self.store,self.teams=store,frozenset(teams)
        self.client_id,self._secret,self.redirect_uri=client_id,client_secret,redirect_uri
        self.client=client or httpx.Client(timeout=10,follow_redirects=False)
        self._lock=threading.RLock()
    def start(self,actor,team):
        if team not in self.teams:
            raise OAuthUnavailable('Workspace is not configured')
        state=self.store.issue_state(actor,team)
        return 'https://slack.com/oauth/v2/authorize?'+urlencode({'client_id':self.client_id,'redirect_uri':self.redirect_uri,
            'state':state,'team':team,'user_scope':'channels:history,groups:history,im:history,mpim:history'})
    def _post(self,method,data=None,token=None):
        try:
            r=self.client.post('https://slack.com/api/'+method,data=data or {},
                headers={'Authorization':'Bearer '+token} if token else {},timeout=10,follow_redirects=False)
            r.raise_for_status();payload=r.json()
            if not isinstance(payload,dict) or payload.get('ok') is not True:
                raise ValueError()
            return payload
        except Exception:
            raise OAuthUnavailable('Slack OAuth request failed') from None
    def _verified(self,token,team,user):
        if not isinstance(token,str) or not token.startswith(('xoxp-','xoxe.xoxp-')):
            raise OAuthUnavailable('A delegated user token is required')
        got=self._post('auth.test',token=token)
        if got.get('team_id')!=team or got.get('user_id')!=user or got.get('bot_id'):
            raise OAuthUnavailable('Slack delegated identity does not match')
    def _credential(self,value):
        expires=value.get('expires_in')
        if expires is not None and (type(expires) is not int or expires<=0):
            raise OAuthUnavailable('Invalid Slack token expiry')
        return {'access_token':value['access_token'],'refresh_token':value.get('refresh_token'),
                'expires_at':self.store.clock()+expires if expires else None}
    def finish(self,code,state):
        actor,team=self.store.consume_state(state)
        if team not in self.teams or not isinstance(code,str) or not 1<=len(code)<=2000:
            raise OAuthUnavailable('Invalid OAuth response')
        payload=self._post('oauth.v2.access',{'client_id':self.client_id,'client_secret':self._secret,'code':code,'redirect_uri':self.redirect_uri})
        user=payload.get('authed_user') or {}
        if (payload.get('team') or {}).get('id')!=team or not re.fullmatch(r'[UW][A-Z0-9]+',str(user.get('id',''))):
            raise OAuthUnavailable('Slack installation workspace does not match')
        self._verified(user.get('access_token'),team,user['id'])
        self.store.put(actor,team,team+'/'+user['id'],self._credential(user))
        return actor,team
    def credential(self,account):
        with self._lock:
            row=self.store.get(account)
            if row is None:
                return None
            actor,team,credential=row
            if credential.get('revoked'):
                raise OAuthUnavailable('Slack connection has been revoked')
            if credential.get('expires_at') and credential['expires_at']<=self.store.clock()+60:
                refresh=credential.get('refresh_token')
                if not refresh:
                    raise OAuthUnavailable('Delegated credential expired; reconnect Slack')
                value=self._post('oauth.v2.access',{'client_id':self.client_id,'client_secret':self._secret,
                    'grant_type':'refresh_token','refresh_token':refresh})
                self._verified(value.get('access_token'),team,account.split('/')[1])
                if not value.get('refresh_token'):
                    raise OAuthUnavailable('Slack token rotation response is incomplete')
                credential=self._credential(value)
                self.store.put(actor,team,account,credential)
            return credential['access_token']


RUNTIME=None


def configure(teams):
    global RUNTIME
    RUNTIME=None
    key=os.getenv('IB_SLACK_TOKEN_KEY','')
    if not key:
        return None
    store=InstallationStore(os.getenv('IB_SLACK_INSTALL_DB',str(DATA_DIR/'slack-installations.db')),key)
    RUNTIME=SlackOAuth(store,teams,os.getenv('IB_SLACK_CLIENT_ID',''),os.getenv('IB_SLACK_CLIENT_SECRET',''),
                       os.getenv('IB_SLACK_REDIRECT_URI',''))
    return RUNTIME
