"""Optional Slack metadata without changing Member 1's SourceDoc contract."""
from dataclasses import dataclass, field

from .base import SourceDoc


@dataclass
class SlackSourceDoc(SourceDoc):
    # Exact Python string offsets into text. ts is message creation time, not
    # the thread's latest activity or edit time. Older root context may remain
    # useful, but cannot be represented as an event in a later query window.
    message_spans: list[dict] = field(default_factory=list)


def thread_text(lines: list[tuple[str, float]]) -> tuple[str, list[dict]]:
    text, spans, cursor = [], [], 0
    for line, created_at in lines:
        spans.append({"start": cursor, "end": cursor + len(line), "ts": float(created_at)})
        text.append(line)
        cursor += len(line) + 1
    return "\n".join(text), spans
