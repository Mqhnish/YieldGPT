"""LLM safety in a permissioned world: nothing leaves without a source.

Even with perfect retrieval filtering, a model can "fill in" facts it was never
given (from training data, or by confident guessing). So after generation we
check every claim:

  - it must cite at least one source ref that was actually provided
  - its content words must substantially overlap with the cited source text

Claims that fail are removed. If nothing survives, the user gets the same
neutral message they'd get for "no results", which also closes the
"does a restricted doc exist?" side channel.
"""
import re

from .index import tokenize

NEUTRAL_NO_ANSWER = ("I couldn't find information you have access to that answers this. "
                     "Try rephrasing, or ask the owner of the relevant space, project or channel.")
MIN_OVERLAP = 0.5
_CITE = re.compile(r"\[(S\d+)\]")
_SPLIT = re.compile(r"\n+|(?<=\[S\d\])[ \t]+(?=\S)|(?<=\[S\d\d\])[ \t]+(?=\S)")


def enforce(answer: str, sources: list[dict]) -> tuple[str, dict]:
    if not answer or answer.strip() == "NO_ANSWER":
        return NEUTRAL_NO_ANSWER, {"kept": 0, "dropped": 0, "no_answer": True}

    by_ref = {s["ref"]: set(tokenize(s["text"] + " " + s["title"])) for s in sources}
    kept, dropped = [], []
    for seg in (x.strip() for x in _SPLIT.split(answer)):
        if not seg:
            continue
        refs = [r for r in _CITE.findall(seg) if r in by_ref]
        words = set(tokenize(_CITE.sub("", seg)))
        if not refs:
            # allow short connective text ("Here's what I found:"), drop uncited claims
            (kept if len(words) <= 4 else dropped).append(seg)
            continue
        support = set().union(*(by_ref[r] for r in refs))
        overlap = len(words & support) / max(len(words), 1)
        (kept if overlap >= MIN_OVERLAP else dropped).append(seg)

    if not any(_CITE.search(k) for k in kept):
        return NEUTRAL_NO_ANSWER, {"kept": 0, "dropped": len(dropped), "no_answer": True}
    text = "\n".join(kept)
    if dropped:
        text += "\n(Some generated statements were removed because they weren't supported by your sources.)"
    return text, {"kept": len(kept), "dropped": len(dropped), "no_answer": False, "dropped_text": dropped}
