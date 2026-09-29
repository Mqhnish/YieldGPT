"""Query planner: which platforms to fan out to, and any time window.

Heuristic keyword routing so it runs offline. With a real LLM, swap `plan()`
for a function-calling step that returns the same structure.
"""
import re
import time
from dataclasses import dataclass, field

DAY = 86400
ALL = {"confluence", "jira", "slack", "gdrive"}

ROUTES = {
    "slack": {"slack", "thread", "threads", "channel", "discussion", "discussed", "chat", "said", "raised", "message", "messages"},
    "jira": {"jira", "ticket", "tickets", "issue", "issues", "blocker", "blockers", "status", "follow", "epic", "bug", "bugs", "vulnerabilities"},
    "confluence": {"confluence", "runbook", "wiki", "page", "doc", "decision", "adr", "design", "report", "architecture"},
    "gdrive": {"drive", "file", "postmortem", "checklist", "sheet", "deck", "guide", "notes"},
}


@dataclass
class Plan:
    platforms: set[str]
    since: dict[str, float] = field(default_factory=dict)
    window_label: str | None = None
    routed_by: list[str] = field(default_factory=list)


def plan(question: str) -> Plan:
    words = set(re.findall(r"[a-z]+", question.lower()))
    hit = {p for p, kw in ROUTES.items() if words & kw}
    # Broad questions fan out everywhere. Narrow ones still include Jira + Confluence
    # as "systems of record" because answers usually need them for grounding.
    platforms = ALL if not hit else hit | {"jira", "confluence"}

    since, label = {}, None
    m = re.search(r"last (\d+) days?", question.lower())
    if m:
        secs, label = int(m.group(1)) * DAY, f"last {m.group(1)} days"
    elif "last week" in question.lower():
        secs, label = 7 * DAY, "last week"
    elif "last sprint" in question.lower():
        secs, label = 14 * DAY, "last sprint"
    else:
        secs = None
    # Time windows apply to conversational data (Slack). A runbook written a
    # year ago is still the current runbook, so docs aren't time-filtered.
    if secs:
        since["slack"] = time.time() - secs
    return Plan(platforms, since, label, sorted(hit))
