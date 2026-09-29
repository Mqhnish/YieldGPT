"""Unified search index across all four platforms.

Stores each SourceDoc plus its platform-specific acl_hint. Scoring is a small
TF-IDF so the project runs with no external services.

TODO for production: embeddings + Tencent Cloud VectorDB (or pgvector), with
`platform`, `container`, `updated_at` and `acl_hint` as filterable metadata so
the prefilter runs inside the vector query.
"""
import math
import re
import threading
import time
from collections import Counter
from dataclasses import dataclass

from .sources.base import SourceDoc

_WORD = re.compile(r"[a-z0-9]+")
STOP = set("""the a an and or of to in on for is are was were be been with by at as it this that what how who
which any all me show did do does there their from into about last week we our was were i you""".split())


def _stem(w: str) -> str:
    """Very light plural folding: blockers -> blocker, vulnerabilities -> vulnerability."""
    if len(w) > 4 and w.endswith("ies"):
        return w[:-3] + "y"
    if len(w) > 3 and w.endswith("s") and not w.endswith("ss") and not w.endswith("us"):
        return w[:-1]
    return w


def tokenize(text: str) -> list[str]:
    return [_stem(w) for w in _WORD.findall(text.lower()) if w not in STOP and len(w) > 1]


@dataclass
class Entry:
    doc: SourceDoc
    acl_hint: set[str]
    indexed_at: float
    tokens: Counter


class Index:
    def __init__(self):
        self._docs: dict[str, Entry] = {}
        self._lock = threading.Lock()

    def upsert(self, doc: SourceDoc, acl_hint: set[str]):
        toks = Counter(tokenize(doc.title) * 2 + tokenize(doc.text))  # title counts double
        with self._lock:
            self._docs[doc.uid] = Entry(doc, set(acl_hint), time.time(), toks)

    def remove(self, uid: str):
        with self._lock:
            self._docs.pop(uid, None)

    def get(self, uid: str) -> Entry | None:
        return self._docs.get(uid)

    def __len__(self):
        return len(self._docs)

    def search(self, query: str, platforms: set[str], since: dict[str, float] | None = None):
        """Returns [(score, Entry)] for matching docs in the given platforms, best first.
        `since` optionally maps platform -> min updated_at (e.g. Slack 'last week')."""
        q = set(tokenize(query))
        if not q:
            return []
        with self._lock:
            entries = [e for e in self._docs.values() if e.doc.platform in platforms]
        n = max(len(self._docs), 1)
        df = Counter()
        for e in self._docs.values():
            df.update(q & set(e.tokens))
        out = []
        need = min(2, len(q))  # a doc must match at least 2 distinct query terms
        for e in entries:
            if since and e.doc.platform in since and e.doc.updated_at < since[e.doc.platform]:
                continue
            matched = [w for w in q if e.tokens[w]]
            if len(matched) < need:
                continue
            s = sum((1 + math.log(e.tokens[w])) * math.log(1 + n / (1 + df[w])) for w in matched)
            out.append((s, e))
        out.sort(key=lambda x: -x[0])
        return out
