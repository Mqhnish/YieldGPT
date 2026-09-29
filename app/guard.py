"""Security guards on the way in (question), mid-way (retrieved content) and out (answer)."""
import re

INJECTION_PATTERNS = [
    r"ignore (all |any )?(previous|prior|above|earlier) (instructions|rules|guidance)",
    r"disregard (all |any )?(previous|prior|above|earlier)",
    r"note to (ai|llm|the assistant|assistants|ai assistants)",
    r"you are now",
    r"pretend (to be|you are)",
    r"act as (an? )?(admin|administrator|root|security team)",
    r"(reveal|show|print) (the |your )?(system prompt|hidden instructions)",
    r"(bypass|override) (the )?(rbac|access control|permissions?)",
]

REDACTIONS = [
    (re.compile(r"\b[STFGM]\s?\d{7}\s?[A-Z]\b"), "[NRIC]"),                  # Singapore NRIC/FIN
    (re.compile(r"\b(?:\d[ -]?){13,19}\b"), "[CARD/ACCOUNT]"),
    (re.compile(r"[\w.+-]+@[\w-]+\.[\w.]+"), "[EMAIL]"),
    (re.compile(r"(?:\+65[ -]?)?\b[689]\d{3}[ -]?\d{4}\b"), "[PHONE]"),
    (re.compile(r"\b(?:sk|pk|api|key)[-_][A-Za-z0-9]{16,}\b"), "[SECRET]"),
]


def detect_injection(text: str) -> list[str]:
    t = text.lower()
    return [p for p in INJECTION_PATTERNS if re.search(p, t)]


def redact(text: str) -> tuple[str, int]:
    count = 0
    for pat, repl in REDACTIONS:
        text, n = pat.subn(repl, text)
        count += n
    return text, count
