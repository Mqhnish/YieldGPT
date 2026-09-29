"""Version-bound complete passages, bounded context, and actor-scoped citation cache."""
from __future__ import annotations

import copy
import dataclasses
import hashlib
import json
import re
import threading
import time
from collections import OrderedDict
from datetime import datetime, timezone

from .index import tokenize


def fingerprint(doc) -> str:
    values = [doc.uid, doc.tenant, doc.version, doc.title, doc.text, doc.url, doc.container, doc.updated_at]
    return hashlib.sha256(json.dumps(values, ensure_ascii=False).encode()).hexdigest()


def passages(text: str, uid: str = '', version: str = '', max_chars: int = 1200) -> list[dict]:
    """Keep complete sentences/lines. Never trim a negation or qualifier to fit a budget.

    Extremely long unpunctuated sentences are omitted, not silently truncated.
    Offsets refer to the connector's exact text snapshot.
    """
    result = []
    pattern = re.compile(r'[^\n]+')
    for line in pattern.finditer(text):
        # Decimal numbers and issue identifiers are not sentence boundaries.
        cuts = [0] + [m.end() for m in re.finditer(r'(?<=[.!?])\s+(?=[A-Z@0-9])', line.group())] + [len(line.group())]
        for start, end in zip(cuts, cuts[1:]):
            raw = line.group()[start:end]
            value = raw.strip()
            if not value or len(value) > max_chars:
                continue
            offset = line.start() + start + len(raw) - len(raw.lstrip())
            ident = hashlib.sha256(f'{uid}\0{version}\0{offset}\0{value}'.encode()).hexdigest()[:16]
            result.append({'id': 'p-' + ident, 'text': value, 'start': offset, 'end': offset + len(value)})
    return result


def passage_score(question: str, passage: dict) -> float:
    q = set(tokenize(question))
    words = set(tokenize(passage['text']))
    cadence = ('how often' in question.casefold() or 'frequency' in question.casefold()) and re.search(
        r'\bevery\b|\bdaily\b|\bnightly\b|\bweekly\b', passage['text'], re.I)
    return len(q & words) + (2 if cadence else 0) + (0.5 if re.match(r'Step \d', passage['text'], re.I) else 0)


def model_source(source: dict) -> dict:
    return {key: source[key] for key in ('ref', 'platform', 'title', 'version', 'updated_iso', 'passages')}


def procedure_request(question: str, title: str) -> bool:
    return (any(word in title.casefold() for word in ('runbook', 'checklist', 'procedure'))
            and any(word in question.casefold() for word in ('runbook', 'step', 'failover', 'checklist', 'procedure')))


def assemble(question: str, scored: list, budget: int = 7000, per_platform: int = 4, max_sources: int = 8,
             since: dict | None = None, until: dict | None = None):
    """Pack only live-approved records, preserving diversity within a relevant shortlist.

    budget limits the UTF-8 JSON evidence payload measured in characters, not model tokens.
    Question/system instructions have their own limits. No source text is silently cut.
    """
    if budget < 128:
        return []
    scored = sorted(scored, key=lambda pair: (-pair[0], pair[1].uid))
    if not scored:
        return []
    # All scores here concern authorized, fresh documents. A hidden record cannot set this threshold.
    # Query matching already excluded incidental single-word hits. Keep relevant
    # cross-source evidence even when an exact ticket ID gives one hit a big boost.
    eligible = [(score, doc) for score, doc in scored if score > 0]
    # Give requested procedures enough room before optional linked background.
    eligible.sort(key=lambda pair: not procedure_request(question, pair[1].title))
    first, remaining, seen = [], [], set()
    for item in eligible:
        if item[1].platform not in seen:
            first.append(item)
            seen.add(item[1].platform)
        else:
            remaining.append(item)
    ordered = first + remaining
    sources, counts = [], {}
    for score, d in ordered:
        if len(sources) >= max_sources or counts.get(d.platform, 0) >= per_platform:
            continue
        ps = passages(d.text, d.uid, d.version)
        if d.platform == 'slack' and getattr(d, 'message_spans', None) and (since or until):
            spans = [m for m in d.message_spans if (since or {}).get('slack', float('-inf')) <= m['ts']
                     <= (until or {}).get('slack', float('inf'))]
            ps = [p for p in ps if any(m['start'] <= p['start'] and p['end'] <= m['end'] for m in spans)]
            if (ps and not any(passage_score(question, p) > 0 for p in ps)
                    and d.container.casefold() not in question.casefold()):
                continue
        if not ps:
            continue
        ranked = sorted(ps, key=lambda p: (-passage_score(question, p), p['start']))
        # Jira head carries its issue status; a selected runbook keeps ordered steps.
        if d.platform == 'jira':
            ranked = [ps[0]] + [p for p in ranked if p['id'] != ps[0]['id']]
        is_runbook = procedure_request(question, d.title)
        if is_runbook:
            # If any overlong sentence was omitted, this cannot be presented as
            # a complete procedure. Likewise, a budget must never truncate steps.
            if ' '.join(d.text.split()) != ' '.join(p['text'] for p in ps):
                continue
            ranked = ps
        chosen, size = [], 0
        for p in ranked:
            if not is_runbook and (size + len(p['text']) > 1800 or len(chosen) >= 8):
                continue
            chosen.append(p)
            size += len(p['text'])
        chosen.sort(key=lambda p: p['start'])
        source = {'ref': f'S{len(sources)+1}', 'uid': d.uid, 'platform': d.platform,
                  'native_id': d.native_id, 'tenant': d.tenant, 'container': d.container,
                  'title': d.title, 'url': d.url, 'version': d.version, 'updated_at': d.updated_at,
                  'updated_iso': datetime.fromtimestamp(d.updated_at, timezone.utc).strftime('%Y-%m-%d %H:%M UTC'),
                  'score': round(score, 4), 'doc': d, 'fingerprint': fingerprint(d),
                  'complete_procedure': is_runbook}
        # Budget includes metadata, offsets and passage identifiers. Remove whole low-relevance passages.
        while chosen:
            source['passages'] = chosen
            source['text'] = '\n'.join(p['text'] for p in chosen)
            payload = [model_source(s) for s in sources] + [model_source(source)]
            if len(json.dumps(payload, ensure_ascii=False)) <= budget:
                sources.append(source)
                counts[d.platform] = counts.get(d.platform, 0) + 1
                break
            if is_runbook:
                break
            worst = min(chosen, key=lambda p: (passage_score(question, p), -p['start']))
            chosen = [p for p in chosen if p['id'] != worst['id']]
    return sources


class EvidenceUnavailable(LookupError):
    pass


class EvidenceCache:
    """Bounded, expiring per-actor snapshots. This is not an authorization cache."""
    def __init__(self, ttl=300, max_queries=256, clock=time.monotonic):
        self.ttl, self.max_queries, self.clock = ttl, max_queries, clock
        self._lock = threading.Lock()
        self._entries = OrderedDict()

    def put(self, actor, query_id, sources):
        with self._lock:
            self._expire()
            bounded = {}
            for source in sources:
                item = dict(source)
                if 'doc' in item:
                    # Audit needs document metadata, not another copy of an arbitrarily large body.
                    item['doc'] = dataclasses.replace(item['doc'], text='', links=[])
                    if hasattr(item['doc'], 'message_spans'):
                        item['doc'].message_spans = []
                bounded[item['ref']] = copy.deepcopy(item)
            self._entries[(actor, query_id)] = (self.clock(), bounded)
            while len(self._entries) > self.max_queries:
                self._entries.popitem(last=False)

    def get(self, actor, query_id, ref):
        with self._lock:
            self._expire()
            item = self._entries.get((actor, query_id))
            if not item or ref not in item[1]:
                raise EvidenceUnavailable('Evidence is not available. Ask the question again.')
            return copy.deepcopy(item[1][ref])

    def discard(self, actor, query_id):
        with self._lock:
            self._entries.pop((actor, query_id), None)

    def _expire(self):
        now = self.clock()
        for key in [k for k, (created, _) in self._entries.items() if now-created > self.ttl]:
            del self._entries[key]
