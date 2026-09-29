"""Thread-safe lexical index. Candidate ranking is independent of hidden corpus data.

The index is NOT an authorization service. Brain checks Member 1's connector before
using a candidate, then ranks current authorized snapshots. No global document
frequency or hidden-document top-k cutoff can displace an accessible result.
"""
from __future__ import annotations

import copy
import math
import re
import threading
import time
from collections import Counter, defaultdict
from dataclasses import dataclass

from .sources.base import SourceDoc

_WORD = re.compile(r"[a-z0-9]+(?:-[a-z0-9]+)*")
_IDENT = re.compile(r"\b[a-z][a-z0-9]*-\d+\b", re.I)
STOP = set('''the a an and or of to in on for is are was were be been with by at as it this that
what how who why which any all me show did do does there their from into about last week we our
was were i you please tell summarize summarise summary latest current status information know
explain give find looking look need want can could would should has have had when happened
raised around new since days day sprint weeks next its it's what's'''.split())
# Small, auditable retrieval vocabulary. This never rewrites evidence or generated claims.
ALIASES = {
    'db': 'database', 'postgres': 'database', 'postgresql': 'database', 'pg16': 'database',
    'migrate': 'migration', 'migrating': 'migration', 'migrated': 'migration',
    'blocker': 'blocker', 'blocked': 'blocker', 'blocking': 'blocker', 'hold': 'blocker',
    'delay': 'blocker', 'delaying': 'blocker', 'delayed': 'blocker',
    'auth': 'auth', 'authentication': 'auth', 'cert': 'certificate',
    'expired': 'expiry', 'expires': 'expiry', 'expire': 'expiry', 'expiration': 'expiry',
    'renewal': 'renew', 'renewed': 'renew', 'renewing': 'renew',
    'failed': 'fail', 'failing': 'fail', 'failure': 'fail',
    'outages': 'outage', 'downtime': 'outage', 'incident': 'incident',
    'remediation': 'remediation', 'remediate': 'remediation',
    'conversation': 'discussion', 'discussed': 'discussion', 'discuss': 'discussion',
    'onboarding': 'onboard', 'onboard': 'onboard', 'credential': 'credential',
    'choose': 'decision', 'chosen': 'decision', 'decided': 'decision', 'choice': 'decision',
    'posted': 'post', 'posting': 'post', 'upgrade': 'migration',
    'approved': 'approval', 'approve': 'approval', 'approving': 'approval',
    'license': 'licence', 'licensed': 'licence',
}
GENERIC = {'slack', 'jira', 'confluence', 'drive', 'gdrive', 'doc', 'document', 'page', 'ticket',
           'issue', 'thread', 'channel', 'file', 'report', 'project', 'update', 'team'}


def _stem(w: str) -> str:
    if '-' in w:
        return w
    if len(w) > 4 and w.endswith('ies'):
        return w[:-3] + 'y'
    if len(w) > 3 and w.endswith('s') and not w.endswith(('ss', 'us')):
        return w[:-1]
    return w


def tokenize(text: str) -> list[str]:
    result = []
    for word in _WORD.findall(text.casefold()):
        if word in STOP:
            continue
        word = ALIASES.get(word, ALIASES.get(_stem(word), _stem(word)))
        if len(word) > 1 or word.isdigit():
            result.append(word)
    return result


def relevance(query: str, title: str, text: str, native_id: str = '') -> float:
    """Bounded term frequency + title coverage + exact identifiers; no corpus statistics."""
    q = set(tokenize(query))
    if not q:
        return 0.0
    body = Counter(tokenize(text))
    head = set(tokenize(title + ' ' + native_id))
    matched = q & (head | set(body))
    significant = q - GENERIC
    exact = set(_IDENT.findall(query.casefold()))
    doc_ids = set(_IDENT.findall((title + ' ' + native_id).casefold()))
    exact_hit = bool(exact & doc_ids)
    compound_hit = any('-' in word and word in head for word in q)
    # A single distinctive concept is sufficient; incidental platform words aren't.
    need = min(2, len(significant))
    if not exact_hit and not compound_hit and (not significant or len(matched & significant) < need):
        return 0.0
    score = sum((0.35 if w in GENERIC else 1.0) *
                (1.0 + 0.35 * math.log1p(min(body[w], 8)) + (1.6 if w in head else 0))
                for w in matched)
    coverage = len(matched & significant) / max(len(significant), 1)
    return score * (0.65 + 0.35 * coverage) + (16.0 if exact_hit else 0)


@dataclass(frozen=True)
class Entry:
    doc: SourceDoc
    acl_hint: frozenset[str]
    indexed_at: float
    tokens: Counter


class Index:
    def __init__(self):
        self._docs: dict[str, Entry] = {}
        self._postings: dict[str, set[str]] = defaultdict(set)
        self._lock = threading.RLock()

    def upsert(self, doc: SourceDoc, acl_hint: set[str]):
        snapshot = copy.deepcopy(doc)
        toks = Counter(tokenize(snapshot.title + ' ' + snapshot.native_id + ' ' + snapshot.text))
        entry = Entry(snapshot, frozenset(acl_hint), time.time(), toks)
        with self._lock:
            self._remove_locked(doc.uid)
            self._docs[doc.uid] = entry
            for term in toks:
                self._postings[term].add(doc.uid)

    def _remove_locked(self, uid):
        old = self._docs.pop(uid, None)
        if old:
            for term in old.tokens:
                self._postings[term].discard(uid)
                if not self._postings[term]:
                    del self._postings[term]

    def remove(self, uid: str):
        with self._lock:
            self._remove_locked(uid)

    def get(self, uid: str) -> Entry | None:
        with self._lock:
            e = self._docs.get(uid)
            return copy.deepcopy(e) if e else None

    def __len__(self):
        with self._lock:
            return len(self._docs)

    def search(self, query: str, platforms: set[str], since: dict[str, float] | None = None):
        terms = set(tokenize(query))
        with self._lock:
            ids = set().union(*(self._postings.get(t, set()) for t in terms)) if terms else set()
            entries = [self._docs[uid] for uid in ids if self._docs[uid].doc.platform in platforms]
        results = []
        for e in entries:
            if since and e.doc.updated_at < since.get(e.doc.platform, float('-inf')):
                continue
            score = relevance(query, e.doc.title, e.doc.text, e.doc.native_id)
            if score > 0:
                results.append((score, copy.deepcopy(e)))
        return sorted(results, key=lambda item: (-item[0], item[1].doc.uid))
