"""YieldGPT: one question, end to end.

   question
     | 1 input guard          injection check on the question
     | 2 plan                 which platforms, what time window
     | 3 fan-out search       per-platform search over the unified index
     | 4 prefilter            cheap ACL-hint check (drops most unauthorised docs early)
     | 5 link expansion       Jira ticket -> linked Slack thread / Confluence doc / Drive file
     | 6 LIVE authz           each candidate re-checked with the platform's native rules, right now
     | 7 read-through fresh   if the source has a newer version than the index, use + re-index it
     | 8 poison scan          drop retrieved content that tries to instruct the model
     | 9 rank + assemble      per-platform score normalisation, context budget
     | 10 LLM                 sees ONLY chunks that passed 6-8
     | 11 grounding check     drop any claim not supported by a cited, provided source
     | 12 output redaction    NRIC, card numbers, emails, phones, secrets
     | 13 audit               every step above, hash-chained
   answer + citations

Every allow/deny decision is logged, but only allowed documents ever appear in
the response, and a fully-denied query returns the same text as a query with no
matches at all, so the response can't be used to probe for restricted content.
"""
import time
import uuid
from datetime import datetime, timezone

from . import audit, grounding, guard, llm, planner
from .config import CONTEXT_BUDGET_CHARS, PER_PLATFORM_K
from .identity import User, principals
from .index import Index
from .sources.base import Decision, PermissionResult, SourceDoc, SourceUnavailable
from .sources.registry import build_connectors
from .sources.world import World
from .sync import Syncer
from .sync_state import SyncStateStore

LINK_DECAY = 0.6
MIN_RELATIVE_SCORE = 0.3
BLOCKED = "This request was blocked by a security policy and has been logged."


class Brain:
    def __init__(self, world: World | None = None, sync_store: SyncStateStore | None = None):
        self.world = world or World()
        self.connectors = build_connectors(self.world)
        self.index = Index()
        self.syncer = Syncer(self.connectors, self.index, sync_store)
        self.world.listeners.append(self.syncer.on_webhook)  # simulated platform webhooks
        self.syncer.full_load()

    # ------------------------------------------------------------------ ask
    def ask(self, user: User, question: str) -> dict:
        qid = uuid.uuid4().hex[:12]
        audit.log(user.username, "query_received", query_id=qid, question=question)

        hits = guard.detect_injection(question)
        if hits:
            audit.log(user.username, "prompt_injection_blocked", severity="alert", query_id=qid, patterns=hits)
            audit.log(user.username, "answer_returned", query_id=qid, answer=BLOCKED, cited=[], context=[],
                      release="blocked")
            return {"query_id": qid, "answer": BLOCKED, "citations": [], "blocked": True}

        plan = planner.plan(question)
        audit.log(user.username, "query_planned", query_id=qid, platforms=sorted(plan.platforms),
                  window=plan.window_label, routed_by=plan.routed_by)

        cands = self._retrieve(user, qid, question, plan)
        sources = self._assemble(self._authorize_and_refresh(user, qid, cands))

        # Generate, then re-authorize EVERY document that was in the model's context
        # (not just the cited ones: uncited context can still shape the wording).
        # If access changed while we were generating, discard and rebuild once
        # without the revoked docs. If it changes again, withhold entirely.
        release = "released"
        for attempt in (1, 2):
            audit.log(user.username, "context_assembled", schema="context_assembled/1", query_id=qid, attempt=attempt,
                      context=[{"uid": s["uid"], "version": s["version"]} for s in sources])
            answer, citations, gstats, n_red = self._generate(user, qid, question, sources)
            revoked = self._release_check(user, qid, sources, attempt)
            if not revoked:
                break
            audit.log(user.username, "answer_discarded", schema="answer_discarded/1", severity="warning", query_id=qid, attempt=attempt,
                      revoked=revoked, discarded_answer=answer)
            sources = [s for s in sources if s["uid"] not in revoked]
            if attempt == 2:
                answer, citations, release = grounding.NEUTRAL_NO_ANSWER, [], "withheld"
            else:
                release = "released_after_rebuild"

        audit.log(user.username, "answer_returned", schema="answer_returned/1", query_id=qid, answer=answer, release=release,
                  cited=[c["uid"] for c in citations], context=[s["uid"] for s in sources],
                  redactions=n_red, grounding={k: v for k, v in gstats.items() if k != "dropped_text"})
        return {"query_id": qid, "answer": answer, "citations": citations, "blocked": False,
                "plan": {"platforms": sorted(plan.platforms), "window": plan.window_label}}

    def _generate(self, user, qid, question, sources):
        raw = llm.complete(question, sources, f"{user.name} ({user.title})")
        answer, gstats = grounding.enforce(raw, sources)
        answer, n_red = guard.redact(answer)
        if gstats["dropped"]:
            audit.log(user.username, "ungrounded_claims_removed", severity="warning", query_id=qid,
                      dropped=gstats.get("dropped_text", []))
        cited_refs = set(grounding._CITE.findall(answer))
        citations = [{k: s[k] for k in ("ref", "platform", "title", "url", "container", "updated_iso", "uid", "version")}
                     for s in sources if s["ref"] in cited_refs]
        return answer, citations, gstats, n_red

    def _release_check(self, user, qid, sources, attempt) -> list[str]:
        revoked = []
        for s in sources:
            conn = self.connectors[s["platform"]]
            res = conn.check(user, s["native_id"])
            self._record(user, qid, s["doc"], "release", res, attempt=attempt)
            if not res.allowed:
                revoked.append(s["uid"])
        return revoked

    # ------------------------------------------------------------ retrieval
    def _retrieve(self, user, qid, question, plan):
        mine = principals(user)
        by_platform: dict[str, list] = {}
        results = self.index.search(question, plan.platforms, plan.since)
        gmax = results[0][0] if results else 1
        for score, e in results:
            if score < MIN_RELATIVE_SCORE * gmax:
                break  # too weak to be worth fetching, checking or logging
            lst = by_platform.setdefault(e.doc.platform, [])
            if len(lst) >= PER_PLATFORM_K:
                continue
            if not (mine & e.acl_hint):
                self._record(user, qid, e.doc, "prefilter", None, code="prefilter_acl_hint",
                             reason="not in document ACL hint at last sync")
                continue
            lst.append((score, e))

        # blend per-platform normalisation (so a chatty source can't drown out the
        # others) with global relevance (so a weak best-in-platform hit stays weak)
        cands: dict[str, tuple[float, object]] = {}
        for lst in by_platform.values():
            top = lst[0][0] if lst else 1
            for s, e in lst:
                cands[e.doc.uid] = (0.5 * s / top + 0.5 * s / gmax, e)

        # cross-platform stitching: follow links out of the strongest hits
        for uid, (s, e) in list(cands.items()):
            for link in e.doc.links:
                if link in cands:
                    continue
                le = self.index.get(link)
                if not le:
                    continue
                if not (mine & le.acl_hint):
                    self._record(user, qid, le.doc, "prefilter", None, code="prefilter_acl_hint",
                                 reason="linked doc not in ACL hint at last sync")
                    continue
                cands[link] = (s * LINK_DECAY, le)
        return cands

    def _authorize_and_refresh(self, user, qid, cands):
        out = []
        for uid, (score, e) in cands.items():
            conn = self.connectors[e.doc.platform]
            res = conn.check(user, e.doc.native_id)                   # live, native semantics, fail-closed
            self._record(user, qid, e.doc, "live", res)
            if not res.allowed:
                continue
            doc = e.doc
            try:
                fresh = conn.fetch(doc.native_id)
            except SourceUnavailable as err:
                self._record(user, qid, doc, "fetch", None, decision=Decision.UNAVAILABLE,
                             code="fetch_failed", reason=str(err))
                continue
            if fresh is None:
                self.index.remove(uid)
                continue
            if fresh.version != doc.version or fresh.text != doc.text:
                self.index.upsert(fresh, conn.acl_hint(doc.native_id))
                self.syncer.record_read_through(doc.platform, doc.native_id, fresh.version)
                audit.log(user.username, "read_through_refresh", query_id=qid, platform=doc.platform,
                          container=doc.container, doc_uid=uid, indexed_version=doc.version,
                          live_version=fresh.version)
                doc = fresh
            if guard.detect_injection(doc.text):
                audit.log(user.username, "poisoned_content_quarantined", severity="alert", query_id=qid,
                          platform=doc.platform, container=doc.container, doc_uid=uid)
                continue
            out.append((score, doc))
        return out

    def _assemble(self, scored):
        scored.sort(key=lambda x: -x[0])
        sources, used = [], 0
        for score, d in scored:
            if used + len(d.text) > CONTEXT_BUDGET_CHARS and sources:
                break
            used += len(d.text)
            sources.append({"ref": f"S{len(sources) + 1}", "uid": d.uid, "platform": d.platform,
                            "native_id": d.native_id, "container": d.container, "title": d.title,
                            "text": d.text, "url": d.url, "version": d.version, "updated_at": d.updated_at,
                            "updated_iso": datetime.fromtimestamp(d.updated_at, timezone.utc).strftime("%Y-%m-%d %H:%M UTC"),
                            "score": round(score, 3), "doc": d})
        return sources

    @staticmethod
    def _record(user: User, qid: str, doc: SourceDoc, stage: str, res: PermissionResult | None, *,
                decision: Decision | None = None, code: str = "", reason: str = "", **extra):
        """THE permission decision record. One per (query, document, stage).
        stage: prefilter | live | fetch | release"""
        dec = res.decision if res else (decision or Decision.DENIED)
        audit.log(user.username, "authz_decision", schema="authz_decision/1",
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
