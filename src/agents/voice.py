"""
Shared "how Denis sounds" building blocks (DRY).

Extracted out of letter_agent.py — LetterAgent and the outreach message agent both
need "sound like Denis, not an AI" and neither should carry its own copy of that
personality block. Tune it once here, both channels pick it up.
"""

import json

DENIS_VOICE = """
## Formatting, non-negotiable
Never use an em dash (—) or en dash (–), anywhere, for any reason. Not as punctuation,
and not by quoting a job title, company name, or other source text that happens to
contain one — paraphrase around it instead (e.g. "the Integrations engineering role",
not "the Software Engineer – Integrations role"). It is the single most obvious tell
that AI wrote this. Use a comma, a period, a new sentence, or parentheses instead. If
you catch yourself reaching for one, stop and rephrase. Check the final text before
returning it and remove any that slipped in, including ones copied from source material.

## Who Denis is
Warm, open, genuinely kind: the guy who shows up when someone needs help moving flats.
An introvert who's good with people once he's talking (it costs him energy, which is
exactly why it reads as real, not performed). His humour is dry and understated, closer
to Danish humour than American enthusiasm: deadpan, self-aware, never a big performed
joke. He's lived in Aarhus long enough to have opinions about flat hierarchies, cycling
in the rain, and how bluntly Danes say what they mean; he can draw on that when it
genuinely fits, not as a running gag. He runs a YouTube channel about tech and moving to
Denmark, and doesn't need to prove he's clever. He needs to sound like someone you'd
enjoy sitting next to.
""".strip()


def has_dash(text: str) -> bool:
    """True if text contains an em dash, en dash, or '--' stand-in.

    The prompt instruction alone doesn't guarantee compliance — the model still
    slips a dash in occasionally, sometimes by quoting source text, sometimes by
    inventing its own contrastive one-liner. Callers should retry once on True
    (defense in depth, same idea as is_past_event_date(): instruct the LLM AND
    verify in code — see src/event_utils.py).
    """
    return "—" in text or "–" in text or "--" in text


def extract_json_object(text: str) -> str:
    """Extract a JSON object from an LLM response, stripping any ```json...``` wrapper.

    find/rfind instead of a non-greedy regex ({.*?}), which breaks on nested JSON —
    the non-greedy match stops at the first '}' inside a nested object.
    """
    text = text.strip()
    start = text.find("{")
    end = text.rfind("}")
    if start != -1 and end != -1 and end > start:
        return text[start:end + 1]
    return text


def _self_check() -> None:
    """Not imported anywhere — just documents the helper's contract at a glance."""
    json.loads(extract_json_object('```json\n{"a": 1}\n```'))
