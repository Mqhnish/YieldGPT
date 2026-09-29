"""Deterministic query planning: broad recall, explicit source limits, dated chat windows."""
from dataclasses import dataclass, field
import re
import time

DAY = 86400
ALL = {'confluence', 'jira', 'slack', 'gdrive'}


@dataclass
class Plan:
    platforms: set[str]
    since: dict[str, float] = field(default_factory=dict)
    window_label: str | None = None
    routed_by: list[str] = field(default_factory=list)
    until: dict[str, float] = field(default_factory=dict)


def plan(question: str, now: float | None = None) -> Plan:
    now = time.time() if now is None else now
    text = question.casefold()
    names = {'confluence': 'confluence', 'jira': 'jira', 'slack': 'slack', 'google drive': 'gdrive', 'drive': 'gdrive'}
    mentioned = {p for w, p in names.items() if re.search(rf'\b{w}\b', text)}
    explicit = re.search(r'\b(?:only (?:in|from|search)|search only) (confluence|jira|slack|google drive|drive)\b', text)
    platforms = {names[explicit.group(1)]} if explicit else set(ALL)
    # A question about messages in one named platform should not be answered by
    # an old wiki merely because it mentions the same incident.
    chat_only = (mentioned == {'slack'} and re.search(r'\b(messages?|threads?|conversations?)\b', text)
                 and not re.search(r'\b(status|tickets?|runbook|follow.up|link|and)\b', text))
    if chat_only and not explicit:
        platforms = {'slack'}
    secs, label = None, None
    m = re.search(r'\b(?:last|past) (\d+) (hours?|days?|weeks?)\b', text)
    if m:
        secs = min(int(m[1]), 3650) * {'hour': 3600, 'day': DAY, 'week': 7 * DAY}[m[2].rstrip('s')]
        label = m[0]
    elif 'last week' in text or 'past week' in text:
        secs, label = 7 * DAY, 'last 7 days'
    elif 'last sprint' in text:
        secs, label = 14 * DAY, 'last 14 days (sprint assumption)'
    elif 'today' in text:
        secs, label = now % DAY, 'today (UTC)'
    since = {'slack': now - secs} if secs is not None else {}
    until = {'slack': now} if secs is not None else {}
    return Plan(platforms, since, label, sorted(mentioned), until)
