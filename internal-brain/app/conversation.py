"""Conversational turns and answer presentation.

Small talk ("hi", "thanks", "what can you do?") gets a short, persona-aware reply instead of the
no-answer message, without touching any source. Detection is strict: the whole message must be
small talk, so "hi, what's blocking MIG-1?" is still a question.

present() lays grounded answer lines out for people: a one-line lead saying where the answer
comes from, then one paragraph per source. It never changes a grounded line; it only adds the
lead and groups lines, so every factual sentence is still an exact, cited source passage.
"""
from __future__ import annotations

import re

_SMALL_TALK = {
    "greeting": re.compile(r"^(hi+|hey+|hello+|hiya|yo|howdy|good (morning|afternoon|evening)|greetings)"
                           r"( there| yieldgpt| brain)?[!. ]*$"),
    "thanks": re.compile(r"^(thanks?( you)?( so much| a lot)?|thank u|thx|ty|cheers|great|ok(ay)?|cool|nice)"
                         r"( thanks?)?[!. ]*$"),
    "help": re.compile(r"^((hi|hello|hey)[, ]+)?(help|\?+|what can you do|what do you do|who are you|what are you|"
                       r"how does this work|how do i use (this|you)|what can i ask( you)?)\??[!. ]*$"),
}

_SUGGESTIONS = {
    "jdoe": ["What's the status of the database migration, and what's blocking it?",
             "Why did we choose the new auth service design?"],
    "ravi": ["What's the latest runbook for the payment-service incident?",
             "What caused the payment outage last quarter, and what follow-ups were created?"],
    "asha": ["Show me all security vulnerabilities",
             "What happened in the Q3 breach?"],
    "kim": ["How do I set up the payouts API sandbox?"],
    "priya": ["What's the status of the database migration?"],
    "dana": ["What's the status of the database migration?"],
}
_DEFAULT = ["What's the status of the database migration?", "What caused the payment outage last quarter?"]

_PLATFORM = {"confluence": ("Confluence page", "Confluence pages"), "jira": ("Jira ticket", "Jira tickets"),
             "slack": ("Slack thread", "Slack threads"), "gdrive": ("Drive file", "Drive files")}
_CITE = re.compile(r"\[(S\d+)\]")


def small_talk(question: str) -> str | None:
    text = re.sub(r"\s+", " ", question.strip().casefold())
    for kind, pattern in _SMALL_TALK.items():
        if pattern.match(text):
            return kind
    return None


def reply(kind: str, user) -> str:
    first = (user.name or user.username).split()[0]
    examples = _SUGGESTIONS.get(user.username, _DEFAULT)
    tries = "\n\n".join(f"• {q}" for q in examples)
    if kind == "thanks":
        return f"You're welcome, {first}. Ask me anything else about Company A's work."
    if kind == "greeting":
        return (f"Hi {first}! I can answer questions from Confluence, Jira, Slack and Google Drive, "
                f"using only what you're allowed to open, with a link to every source.\n\nTry:\n\n{tries}")
    return ("I search Confluence, Jira, Slack and Google Drive for you and answer in one place. "
            "I only use sources you can open yourself, and every line links back to where it came from. "
            "If something is restricted, I won't show it or hint that it exists."
            f"\n\nQuestions you could ask:\n\n{tries}")


def present(answer: str, citations: list[dict]) -> str:
    """Lead line plus one paragraph per source. Grounded lines are kept verbatim and in order."""
    lines = [l for l in answer.splitlines() if l.strip()]
    if not lines or not citations:
        return answer
    groups: dict[str, list[str]] = {}
    for line in lines:
        refs = _CITE.findall(line)
        groups.setdefault(refs[0] if refs else "", []).append(line)
    counts: dict[str, int] = {}
    for c in citations:
        counts[c["platform"]] = counts.get(c["platform"], 0) + 1
    parts = [f"{n} {_PLATFORM.get(p, (p, p + 's'))[0 if n == 1 else 1]}" for p, n in counts.items()]
    where = ", ".join(parts[:-1]) + (" and " if len(parts) > 1 else "") + parts[-1]
    lead = f"Here's what I found in {where} you can access:"
    return "\n\n".join([lead] + ["\n".join(g) for g in groups.values()])
