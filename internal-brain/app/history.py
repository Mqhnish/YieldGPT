"""Replay questions from successful deliveries, never return stored answer text.

History is actor-scoped metadata. Source content is always rebuilt with current
permissions; encrypted audit question retention governs replay availability.
"""
import re
from . import audit


class HistoryUnavailable(LookupError):
    pass


def _answer_delivery(row):
    route = row['detail'].get('route')
    if route is None:  # Older delivery records have the route on their receipt.
        receipts = audit.search(request_id=row['request_id'], event='request_received', limit=1)
        route = receipts[0]['detail'].get('route', '') if receipts else ''
    return route == '/api/ask' or (route.startswith('/api/history/') and route.endswith('/replay'))


def list_history(actor, limit=30):
    delivered = audit.search(actor=actor, event='response_delivered', limit=500)
    seen, items = set(), []
    for row in delivered:
        qid = row['query_id']
        if not qid or qid in seen or not _answer_delivery(row):
            continue
        seen.add(qid)
        # An evidence preview isn't a newly saved answer.
        questions = audit.search(actor=actor, event='query_received', query_id=qid, limit=1)
        if not questions or not isinstance(questions[0]['detail'].get('question'), str):
            continue
        items.append({'query_id':qid,'created_at':questions[0]['ts']})
        if len(items) >= min(max(limit,1),100):
            break
    audit.log(actor,'history_listed',returned=len(items))
    return items


def replay(service, user, query_id):
    if not re.fullmatch(r'[a-f0-9]{12}',query_id):
        raise HistoryUnavailable()
    delivered = audit.search(actor=user.username,event='response_delivered',query_id=query_id,limit=500)
    questions = audit.search(actor=user.username,event='query_received',query_id=query_id,limit=1)
    if not any(_answer_delivery(row) for row in delivered) or not questions:
        raise HistoryUnavailable()
    question = questions[0]['detail'].get('question')
    if not isinstance(question,str) or not question.strip():
        raise HistoryUnavailable()
    result = service.ask(user,question)
    audit.log(user.username,'question_replayed',query_id=result['query_id'],original_query_id=query_id,
              replay='fresh_retrieval_not_cached_answer')
    return {**result,'replayed_from':query_id}
