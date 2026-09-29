"""Strict extractive grounding. Citation validity is not semantic entailment.

A returned factual line must be an entire passage from a cited, approved snapshot.
We deliberately reject free paraphrases instead of pretending word overlap proves
truth. The model can choose and order evidence; the server controls factual text.
"""
import re
import unicodedata
from .evidence import passages

NEUTRAL_NO_ANSWER = ("I couldn't find information you have access to that answers this. "
                     "Try rephrasing, or ask the owner of the relevant space, project or channel.")
_CITE = re.compile(r'\[(S\d+)\]')


def normalized(text):
    return ' '.join(unicodedata.normalize('NFKC', text).split()).strip()


def enforce(answer: str, sources: list[dict]) -> tuple[str, dict]:
    by_ref = {s['ref']: {normalized(p['text']) for p in s.get('passages', passages(s['text']))} for s in sources}
    kept, dropped = [], []
    if answer and answer.strip() != 'NO_ANSWER':
        for line in answer.splitlines():
            line = line.strip()
            if not line:
                continue
            refs = _CITE.findall(line)
            claim = normalized(_CITE.sub('', line))
            if claim.startswith('- '):
                claim = claim[2:]
            # A fabricated ref invalidates the whole claim, including otherwise valid refs.
            valid = refs and all(ref in by_ref for ref in refs)
            if valid and all(claim in by_ref[ref] for ref in refs):
                canonical = f"{claim} " + ''.join(f'[{ref}]' for ref in dict.fromkeys(refs))
                if canonical not in kept:
                    kept.append(canonical)
            else:
                dropped.append(line)
    text = '\n'.join(kept) if kept else NEUTRAL_NO_ANSWER
    return text, {'kept': len(kept), 'dropped': len(dropped), 'no_answer': not kept,
                  'dropped_text': dropped, 'method': 'complete_passage_match'}
