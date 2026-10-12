"""Index.search caches document terms at upsert. Scores and order must not change."""
import math
from collections import Counter

from app.index import _IDENT, GENERIC, Index, relevance, tokenize
from app.seeding.scale import generate
from app.sources.registry import build_connectors

QUESTIONS = [
    "What's the status of the database migration project and were there any blockers raised in Slack last week?",
    "What was the root cause of the payment outage last quarter, and what follow-up tickets were created?",
    "What's the latest runbook for the payment-service incident?",
    "Show me the security incident report from the Q3 breach",
    "Which settlement batch incidents happened recently and who owns the fix?",
    "PAY-110", "ADR-17 decision", "slack jira", "", "the of and",
]
PLATFORMS = {"confluence", "jira", "slack", "gdrive"}


def reference_relevance(query, title, text, native_id=""):
    """The original per-candidate scorer, kept verbatim as the reference."""
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
    need = min(2, len(significant))
    if not exact_hit and not compound_hit and (not significant or len(matched & significant) < need):
        return 0.0
    score = sum((0.35 if w in GENERIC else 1.0) *
                (1.0 + 0.35 * math.log1p(min(body[w], 8)) + (1.6 if w in head else 0))
                for w in matched)
    coverage = len(matched & significant) / max(len(significant), 1)
    return score * (0.65 + 0.35 * coverage) + (16.0 if exact_hit else 0)


def _corpus():
    world = generate(7, pages=600, issues=300, channels=20, threads=300, files=150)
    docs = []
    for c in build_connectors(world, atlassian_mode="sim").values():
        ids, token = c.list_page(None, 500)
        while True:
            docs += [d for d in (c.fetch(i) for i in ids) if d]
            if not token:
                break
            ids, token = c.list_page(token, 500)
    return docs


def test_cached_search_matches_reference_scorer():
    docs = _corpus()
    assert len(docs) > 1000
    index = Index()
    for d in docs:
        index.upsert(d, {"anyone"})
    for q in QUESTIONS:
        expected = sorted(((reference_relevance(q, d.title, d.text, d.native_id), d.uid) for d in docs),
                          key=lambda x: (-x[0], x[1]))
        expected = [x for x in expected if x[0] > 0]
        got = [(s, e.doc.uid) for s, e in index.search(q, PLATFORMS)]
        assert got == expected, q
        for d in docs[:200]:
            assert relevance(q, d.title, d.text, d.native_id) == reference_relevance(q, d.title, d.text, d.native_id)


def test_cached_terms_follow_upserts():
    docs = _corpus()[:50]
    index = Index()
    d = docs[0]
    index.upsert(d, {"anyone"})
    d.text = "zebracorn settlement reconciliation"
    d.title = "zebracorn"
    index.upsert(d, {"anyone"})
    assert [e.doc.uid for _, e in index.search("zebracorn settlement", PLATFORMS)] == [d.uid]
    index.remove(d.uid)
    assert index.search("zebracorn settlement", PLATFORMS) == []


def test_search_results_are_isolated_copies():
    docs = _corpus()[:50]
    index = Index()
    for d in docs:
        index.upsert(d, {"anyone"})
    q = docs[0].title
    (_, e), *_ = [x for x in index.search(q, PLATFORMS) if x[1].doc.uid == docs[0].uid]
    e.doc.text = "tampered"
    assert index.get(docs[0].uid).doc.text != "tampered"
    assert set(e.tokens) == set(tokenize(docs[0].title + " " + docs[0].native_id + " " + docs[0].text))
