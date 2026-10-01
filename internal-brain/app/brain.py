"""Member 2 pipeline built on Member 1's unchanged connector and audit contracts.

Only fresh, live-authorized snapshots reach model selection. Every context source
is checked again at release, including version/content changes. Restricted results
cannot set a global rank cutoff; cross-platform links are expanded only from
approved parents. Citation previews are separately authorized on every request.
"""
from __future__ import annotations
import time
import uuid
from urllib.parse import urlparse

from . import audit, grounding, guard, llm, planner
from .config import CONTEXT_BUDGET_CHARS, PER_PLATFORM_K
from .metrics import Measurement, timed
from .identity import User, principals
from .index import Index, relevance, tokenize
from .evidence import EvidenceCache, EvidenceUnavailable, assemble, fingerprint
from .sources.base import Decision, PermissionResult, SourceDoc, SourceUnavailable
from .sources.registry import build_connectors
from .sources.world import World
from .sync import Syncer
from .sync_state import SyncStateStore

LINK_DECAY = 0.6
MAX_LINK_HOPS = 3
BLOCKED = "This request was blocked by a security policy and has been logged."


class Brain:
    def __init__(self, world: World | None = None, sync_store: SyncStateStore | None = None, *,
                 connectors=None, index=None, event_sink=None):
        self.world = world or World()
        self.connectors = connectors if connectors is not None else build_connectors(self.world)
        self.index = index if index is not None else Index()
        self._log = event_sink if event_sink is not None else audit.log
        self.evidence_cache = EvidenceCache()
        self.syncer = Syncer(self.connectors, self.index, sync_store)
        self.world.listeners.append(self.syncer.on_webhook)
        self.syncer.full_load()

    def ask(self, user: User, question: str) -> dict:
        try:
            with Measurement() as measured:
                result = self._ask(user, question)
        except llm.ModelUnavailable as error:
            self._log(user.username, 'query_performance', query_id=error.query_id,
                      phases_ms=measured.snapshot(), outcome='model_unavailable',
                      scope='pipeline wall time; excludes HTTP checkpoint and delivery')
            raise
        self._log(user.username, 'query_performance', query_id=result['query_id'],
                  phases_ms=measured.snapshot(),
                  scope='pipeline wall time; excludes HTTP checkpoint and delivery')
        return result

    def _ask(self, user: User, question: str) -> dict:
        question = question.strip()
        if not question or len(question) > 2000:
            raise ValueError('Question must contain 1–2000 characters.')
        qid = uuid.uuid4().hex[:12]
        self._log(user.username, 'query_received', query_id=qid, question=question)
        if guard.detect_injection(question):
            self._log(user.username, 'prompt_injection_blocked', severity='alert', query_id=qid)
            self._log(user.username, 'answer_returned', schema='answer_returned/1', query_id=qid,
                      answer=BLOCKED, cited=[], context=[], release='blocked')
            return {'query_id': qid, 'answer': BLOCKED, 'citations': [], 'blocked': True,
                    'status': 'blocked', 'quality': {'mode': 'extractive', 'rejected_claims': 0}}
        plan = planner.plan(question)
        self._log(user.username, 'query_planned', query_id=qid, platforms=sorted(plan.platforms),
                  window=plan.window_label, routed_by=plan.routed_by)
        candidates = self._retrieve(user, qid, question, plan)
        authorized = self._authorize_and_refresh(user, qid, candidates, question=question, plan=plan)
        # Links are followed only from live-authorized parents. Linked targets have their own gates.
        frontier, visited = authorized, set(candidates)
        for _ in range(MAX_LINK_HOPS):
            linked = self._linked_candidates(user, qid, frontier, plan)
            linked = {uid: item for uid, item in linked.items() if uid not in visited}
            if not linked:
                break
            visited.update(linked)
            frontier = self._authorize_and_refresh(user, qid, linked, plan=plan)
            authorized += frontier
        # Do not answer a request for a specific fact with generic project progress.
        # These explicit attributes require direct evidence; this is an auditable
        # abstention heuristic, not a claim of general semantic understanding.
        requested = set(tokenize(question)) & {'budget', 'approval', 'salary', 'password', 'revenue', 'profit', 'cost'}
        available = set(tokenize(' '.join(doc.text for _, doc in authorized)))
        if requested - available:
            authorized = []
        sources = assemble(question, authorized, CONTEXT_BUDGET_CHARS, PER_PLATFORM_K,
                           since=plan.since, until=plan.until)
        # Do not substitute tangential linked tickets when a requested procedure
        # is too large to deliver completely within the evidence budget.
        from .evidence import procedure_request
        if (any(procedure_request(question, d.title) for _, d in authorized)
                and not any(s.get('complete_procedure') for s in sources)):
            sources = []
        release, quality, used_context = 'released', {}, []
        for attempt in (1, 2):
            used_context = list(sources)
            self._log(user.username, 'context_assembled', schema='context_assembled/1', query_id=qid,
                      attempt=attempt, context=[{'uid': s['uid'], 'version': s['version'],
                        'fingerprint': s['fingerprint'], 'passage_ids': [p['id'] for p in s['passages']]} for s in sources])
            answer, citations, gstats, n_red, quality = self._generate(user, qid, question, sources)
            revoked = self._release_check(user, qid, sources, attempt)
            if not revoked:
                break
            self._log(user.username, 'answer_discarded', schema='answer_discarded/1', severity='warning',
                      query_id=qid, attempt=attempt, revoked=revoked, discarded_answer=answer)
            sources = [s for s in sources if s['uid'] not in revoked]
            if attempt == 2:
                answer, citations, release = grounding.NEUTRAL_NO_ANSWER, [], 'withheld'
            else:
                release = 'released_after_rebuild'
        self._log(user.username, 'answer_returned', schema='answer_returned/1', query_id=qid,
                  answer=answer, release=release, cited=[c['uid'] for c in citations],
                  context=[s['uid'] for s in used_context], redactions=n_red,
                  grounding={k:v for k,v in gstats.items() if k != 'dropped_text'}, generation=quality)
        cited_refs = {c['ref'] for c in citations}
        self.evidence_cache.put(user.username, qid, [s for s in sources if s['ref'] in cited_refs])
        return {'query_id': qid, 'answer': answer, 'citations': citations, 'blocked': False,
                'status': 'answered' if citations else 'no_answer', 'quality': quality,
                'plan': {'platforms': sorted(plan.platforms), 'window': plan.window_label}}

    @timed('generation_and_grounding_ms')
    def _generate(self, user, qid, question, sources):
        # Keep llm.complete's established interface for teammate tests and model adapters.
        try:
            raw = llm.complete(question, sources, f'{user.name} ({user.title})')
        except llm.ModelUnavailable as error:
            error.query_id = qid
            self._log(user.username, 'model_measurement', query_id=qid, **error.measurement)
            raise
        answer, stats = grounding.enforce(raw, sources)
        answer, n_red = guard.redact(answer)
        if stats['dropped']:
            self._log(user.username, 'ungrounded_claims_removed', severity='warning', query_id=qid,
                      dropped=stats.get('dropped_text', [])[:20])
        self._log(user.username, 'model_measurement', query_id=qid,
                  **getattr(raw, 'measurement', {'mode': 'custom_adapter', 'remote_attempts': 0}))
        mode = getattr(raw, 'mode', 'extractive')
        if getattr(raw, 'reason', None):
            self._log(user.username, 'generation_fallback', query_id=qid, reason=raw.reason)
        refs = set(grounding._CITE.findall(answer))
        citations = [{k:s[k] for k in ('ref','platform','title','url','container','updated_iso','uid','version')}
                     for s in sources if s['ref'] in refs]
        return answer, citations, stats, n_red, {'mode': mode, 'rejected_claims': stats['dropped'],
                                                'grounding': 'complete_source_passages'}

    @timed('retrieval_ms')
    def _retrieve(self, user, qid, question, plan):
        mine, candidates = principals(user), {}
        # No top-k/relative cutoff before live authorization. Hidden candidates cannot crowd out visible ones.
        for score, entry in self.index.search(question, plan.platforms, plan.since):
            if not (mine & entry.acl_hint):
                self._record(user, qid, entry.doc, 'prefilter', None, code='prefilter_acl_hint',
                             reason='not in document ACL hint at last sync')
                continue
            candidates[entry.doc.uid] = (score, entry)
        return candidates

    def _linked_candidates(self, user, qid, authorized, plan):
        candidates, mine, per_source = {}, principals(user), {}
        for score, doc in sorted(authorized, key=lambda item:(-item[0], item[1].uid)):
            if per_source.get(doc.platform, 0) >= PER_PLATFORM_K:
                continue
            per_source[doc.platform] = per_source.get(doc.platform, 0) + 1
            for uid in doc.links:
                entry = self.index.get(uid)
                if not entry or entry.doc.platform not in plan.platforms:
                    continue
                if not (mine & entry.acl_hint):
                    self._record(user, qid, entry.doc, 'prefilter', None, code='prefilter_acl_hint',
                                 reason='linked document not in ACL hint at last sync')
                    continue
                old = candidates.get(uid)
                if old is None or old[0] < score * LINK_DECAY:
                    candidates[uid] = (score * LINK_DECAY, entry)
        return candidates

    @staticmethod
    def _fetch(conn, user, native_id):
        # Slack and future adapters can supply an identity-scoped read without changing Member 1's base.
        reader = getattr(conn, 'read_authorized', None)
        return reader(user, native_id) if reader else conn.fetch(native_id)

    @timed('authorization_and_read_ms')
    def _authorize_and_refresh(self, user, qid, candidates, question=None, plan=None):
        output = []
        for uid, (score, entry) in candidates.items():
            doc = entry.doc
            conn = self.connectors[doc.platform]
            result = conn.check(user, doc.native_id)
            self._record(user, qid, doc, 'live', result, phase='before_read')
            if not result.allowed:
                continue
            try:
                fresh = self._fetch(conn, user, doc.native_id)
                if fresh is None:
                    # A user-scoped miss needn't mean global deletion; sync owns tombstones.
                    if not hasattr(conn, 'read_authorized'):
                        self.index.remove(uid)
                    continue
                if fresh.uid != uid or fresh.platform != doc.platform or fresh.tenant != doc.tenant:
                    raise SourceUnavailable('source identity mismatch')
                final = conn.check(user, doc.native_id)
                self._record(user, qid, fresh, 'live', final, phase='after_read')
                if not final.allowed or (final.resource_version and final.resource_version != fresh.version):
                    continue
                if fingerprint(fresh) != fingerprint(doc):
                    # Do not persist a user-scoped Slack view as a global ingestion snapshot.
                    if not hasattr(conn, 'read_authorized'):
                        self.index.upsert(fresh, conn.acl_hint(doc.native_id))
                    self.syncer.record_read_through(doc.platform, doc.native_id, fresh.version)
                    self._log(user.username, 'read_through_refresh', query_id=qid, platform=doc.platform,
                              container=doc.container, doc_uid=uid, indexed_version=doc.version, live_version=fresh.version)
                doc = fresh
            except Exception as err:
                # Connector errors are private. Never expose raw exception text, tokens or object existence.
                self._record(user, qid, doc, 'fetch', None, decision=Decision.UNAVAILABLE,
                             code='fetch_failed', reason=type(err).__name__)
                continue
            if plan:
                lower, upper = plan.since.get(doc.platform, float('-inf')), plan.until.get(doc.platform, float('inf'))
                if doc.platform == 'slack' and getattr(doc, 'message_spans', None):
                    if not any(lower <= span['ts'] <= upper for span in doc.message_spans):
                        continue
                elif not lower <= doc.updated_at <= upper:
                    continue
            if urlparse(doc.url).scheme != 'https' or guard.detect_injection(doc.title + '\n' + doc.text):
                self._log(user.username, 'poisoned_content_quarantined', severity='alert', query_id=qid,
                          platform=doc.platform, container=doc.container, doc_uid=uid)
                continue
            if question is not None:
                score = relevance(question, doc.title, doc.text, doc.native_id)
                if score <= 0:
                    continue
            output.append((score, doc))
        return output

    @timed('release_authorization_ms')
    def _release_check(self, user, qid, sources, attempt):
        revoked = []
        for source in sources:
            conn = self.connectors[source['platform']]
            res = conn.check(user, source['native_id'])
            self._record(user, qid, source['doc'], 'release', res, attempt=attempt, phase='before_read')
            if not res.allowed:
                revoked.append(source['uid'])
                continue
            try:
                fresh = self._fetch(conn, user, source['native_id'])
                if fresh is None or fingerprint(fresh) != source['fingerprint']:
                    revoked.append(source['uid'])
                    continue
                final = conn.check(user, source['native_id'])
                self._record(user, qid, source['doc'], 'release', final, attempt=attempt, phase='after_read')
                if not final.allowed or (final.resource_version and final.resource_version != fresh.version):
                    revoked.append(source['uid'])
            except Exception:
                revoked.append(source['uid'])
        return revoked

    def evidence(self, user, query_id, ref):
        source = self.evidence_cache.get(user.username, query_id, ref)
        conn = self.connectors[source['platform']]
        result = conn.check(user, source['native_id'])
        self._record(user, query_id, source['doc'], 'release', result, evidence_preview=True)
        try:
            if not result.allowed:
                raise EvidenceUnavailable()
            fresh = self._fetch(conn, user, source['native_id'])
            if fresh is None or fingerprint(fresh) != source['fingerprint']:
                raise EvidenceUnavailable()
            final = conn.check(user, source['native_id'])
            self._record(user, query_id, source['doc'], 'release', final,
                         evidence_preview=True, phase='after_read')
            if not final.allowed or (final.resource_version and final.resource_version != fresh.version):
                raise EvidenceUnavailable()
        except Exception:
            self.evidence_cache.discard(user.username, query_id)
            raise EvidenceUnavailable('Evidence is not available. Ask the question again.') from None
        self._log(user.username, 'evidence_viewed', schema='evidence_viewed/1', query_id=query_id,
                  doc_uid=source['uid'], platform=source['platform'], version=source['version'],
                  passage_ids=[p['id'] for p in source['passages']])
        output = {k:source[k] for k in ('ref','title','platform','url','version','updated_iso')}
        output['passages'] = [{'id': p['id'], 'text': guard.redact(p['text'])[0]} for p in source['passages']]
        return output

    def _record(self, user: User, qid: str, doc: SourceDoc, stage: str, res: PermissionResult | None, *,
                decision: Decision | None = None, code: str = "", reason: str = "", **extra):
        """Permission decision records include each check phase and attempt.
        stage: prefilter | live | fetch | release"""
        dec = res.decision if res else (decision or Decision.DENIED)
        self._log(user.username, "authz_decision", schema="authz_decision/1",
                  severity="info" if dec is Decision.ALLOWED else "warning",
                  query_id=qid, platform=doc.platform, container=doc.container, doc_uid=doc.uid,
                  decision=dec.value, stage=stage,
                  reason_code=res.reason_code if res else code,
                  reason=res.reason if res else reason,
                  checked_at=res.checked_at if res else time.time(),
                  platform_account=res.platform_account if res else "",
                  resource_version=(res.resource_version if res and res.resource_version else doc.version),
                  title=doc.title, **extra)

    def freshness(self, interval_s):
        return {"indexed_docs": len(self.index), "platforms": self.syncer.status(interval_s), "checked_at": time.time()}
