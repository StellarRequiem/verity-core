"""verity.markdown — the README / model-card claim extractor.

The launch hook: *"your README says 95% — did anyone check?"* A model card or
project README routinely asserts a headline number (``accuracy: 0.95``) that no
one ever ran through a gate. This surface pulls the machine-checkable claims out
of a markdown document and runs each through ``verity.verify`` — so a CI step (or
an agent reading the doc) can REFUSE a README whose own stated number doesn't
clear the bar.

DETERMINISTIC by construction — and that determinism is the whole point of trust:

  * ``extract_claims`` reads ONLY fenced ```` ```json ```` code blocks and
    ``json.loads`` each one. It NEVER fuzzy-parses prose ("we hit 95% accuracy"):
    guessing a number out of a sentence is exactly the unreliable NLP this project
    refuses to do — a regex that scrapes "95%" from English would mis-read as often
    as it read right, and a verifier you cannot trust is worse than none. A claim
    has to be written as a structured JSON block, on purpose, to be checked.
  * A fence with NO ``json`` info string is ignored (it is documentation, not a
    claim). A ``json`` fence whose body does not parse is SKIPPED, never raised —
    one malformed block must not take the extractor (or the CI gate) down. Only a
    parsed JSON *object* is a result-claim (a bare array / scalar is not a claim
    in this codebase, where every claim is a dict); non-object parses are skipped.

``verify_markdown`` is the thin orchestrator: extract, then run each claim through
the SAME ``verify`` every other surface uses (one gate, one vocabulary). ``truth``
is a *resolved* truth dict or ``None`` (``verify`` loads the packaged default) —
this module does no truth I/O of its own, mirroring ``verify``'s no-I/O contract.
"""
from __future__ import annotations

import json
import re

from .verify import verify

# A fenced code block whose info string is exactly ``json`` (case-insensitive, with optional
# surrounding whitespace — e.g. ```` ```json ````, ```` ```JSON ````, ```` ``` json ````). Anchored
# at line starts (MULTILINE) so an indistinct mid-line "```json" inside prose can't false-match, and
# DOTALL so the captured body may span many lines. The closing fence is a line that is only
# backticks. Group 1 is the block body. We deliberately match ONLY the ``json`` language so a plain
# ```` ``` ```` fence (or any other language tag) is never read as a claim — that exact distinction is
# what keeps extraction deterministic instead of "parse anything that looks like data".
_JSON_FENCE = re.compile(
    r"^[ \t]*```[ \t]*json[ \t]*\r?\n"   # opening fence + `json` info string, to end of line
    r"(.*?)"                              # (1) the block body — non-greedy, may span lines (DOTALL)
    r"\r?\n[ \t]*```[ \t]*\r?$",          # closing fence: a line of only backticks (CRLF-tolerant)
    re.IGNORECASE | re.MULTILINE | re.DOTALL,
)


def extract_claims(md_text: str) -> list[dict]:
    """Extract result-claims from the ```` ```json ```` fenced blocks of a markdown document.

    Returns the list of claim dicts, in document order. DETERMINISTIC: only fenced ``json``
    blocks are read (never prose); a block that does not ``json.loads`` is skipped (never raised),
    and only a parsed JSON object counts as a claim — a non-object parse (array / number / string)
    is skipped too. A non-string input yields ``[]`` rather than crashing (an input that can take
    the extractor down is a way to bypass the gate).
    """
    if not isinstance(md_text, str):
        return []
    claims: list[dict] = []
    for m in _JSON_FENCE.finditer(md_text):
        body = m.group(1)
        try:
            obj = json.loads(body)
        except ValueError:
            continue                      # malformed JSON in a json fence — skip, never crash
        if isinstance(obj, dict):         # a claim is an object; a bare array/scalar is not one
            claims.append(obj)
    return claims


def verify_markdown(md_text: str, truth: dict | None = None) -> list[dict]:
    """Extract every fenced-``json`` claim from ``md_text`` and verify each through ``verity.verify``.

    Returns one entry per extracted claim, in document order::

        [{"claim": <the parsed claim dict>,
          "verdict": "REFUSE"|"WARN"|"PASS",
          "issues":  [ ...the flattened issues from verify... ]}, ...]

    ``truth`` is a resolved truth dict (thresholds + facts) or ``None`` — passed straight to
    ``verify``, which loads the packaged default when it is ``None``. A document with no json
    blocks yields ``[]`` (nothing claimed → nothing to refuse); the CALLER decides what an empty
    result means for its exit code.
    """
    out: list[dict] = []
    for claim in extract_claims(md_text):
        res = verify(claim, truth=truth)
        out.append({"claim": claim, "verdict": res["verdict"], "issues": res["issues"]})
    return out
