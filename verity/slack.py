"""verity → Slack — post a verdict where the team will actually see it.

The hook: a gate that REFUSEs a number in a CI log no one reads is half a gate.
This surface runs ``verity.verify`` on a claim and pushes the verdict to a Slack
**incoming webhook**, color-coded so a REFUSE is unmissable in the channel — red
REFUSE / yellow WARN / green PASS, with the offending issues listed inline.

STDLIB ONLY — ``urllib.request`` for the POST, ``json`` for the payload. No
``slack_sdk``, no ``requests``. The webhook URL is **always a parameter**, never
hard-coded: a webhook is a credential, and a credential baked into source is a
leak. Pass it from the environment / a secret store at the call site.

DETERMINISTIC and injectable like every other verity surface:

  * ``format_slack_message`` is a **pure** function — claim + verdict in, a Slack
    payload dict out. No I/O, no clock, no network; same input → byte-identical
    output. That is what makes the payload itself testable.
  * ``notify_slack`` takes an injectable ``transport`` (defaulting to a real
    urllib POST). A test passes a fake sender and asserts the EXACT payload that
    *would* go on the wire — **without touching the network** — mirroring how
    ``verify`` treats sources as caller-supplied (never crawled) and how the HTTP
    server binds an ephemeral port: the side-effecting edge is always swappable so
    the contract can be pinned offline.

One gate, one vocabulary: the colors and issue lines are rendered straight from
``verify``'s ``{"verdict","dimensions","issues"}`` — this module adds no verdict
logic and no second severity ladder.
"""
from __future__ import annotations

import json
import urllib.request

from .verify import verify

# Slack attachment bar colors, keyed by verdict. Hex from Slack's own brand palette
# (aubergine-red / yellow / green) rather than the legacy named "danger/warning/good"
# so the bar renders identically across Slack clients that no longer special-case the
# names. An unknown verdict falls back to neutral grey — we never guess a color we
# can't justify (the same "default to uncertain" stance the gate takes on inputs).
_VERDICT_COLOR = {
    "REFUSE": "#E01E5A",   # red — a fabrication-class / CRITICAL claim; do not believe it
    "WARN":   "#ECB22E",   # yellow — clears the floor but with rigor gaps; treat with caution
    "PASS":   "#2EB67D",   # green — clears THESE hygiene checks (not "profitable")
}
_NEUTRAL_COLOR = "#717274"

# A short headline glyph per verdict — pure decoration for the channel, never parsed.
_VERDICT_EMOJI = {"REFUSE": ":no_entry:", "WARN": ":warning:", "PASS": ":white_check_mark:"}


def _claim_label(claim) -> str:
    """A short, crash-proof display name for a claim (dict or not).

    Mirrors ``gate._claim_label`` so the Slack surface names a claim exactly the way the
    VERIFIED block does — name, else text, else a type tag. Never raises on a non-dict claim
    (an input that can crash the notifier is an input that silences the alert)."""
    if isinstance(claim, dict):
        return str(claim.get("name", claim.get("text", "?")))
    return f"<{type(claim).__name__}>"


def format_slack_message(claim, result: dict) -> dict:
    """Render a verified ``claim`` + its ``verify`` ``result`` as a Slack webhook payload dict.

    PURE — no I/O. Returns a Slack message with one colored ``attachment`` (the bar color is
    the verdict color) carrying ``blocks``:

      * a header line — ``<emoji> verity <VERDICT>`` — so the verdict is legible at a glance;
      * the claim's label and (when present) its per-dimension verdicts;
      * one bullet per issue — ``[SEVERITY] source:check — detail`` — so the channel sees
        *why* a claim was refused, not just that it was. A clean PASS says so explicitly.

    ``result`` is ``verify``'s own dict (``{"verdict","dimensions","issues"}``); a malformed /
    partial result degrades gracefully (missing keys default to ``UNKNOWN`` / empty) rather than
    raising — the alert must still post. ``text`` is set as a notification fallback (what shows
    in a push / notification preview) so the message is not silently blank on older clients.
    """
    result = result if isinstance(result, dict) else {}
    verdict = str(result.get("verdict", "UNKNOWN"))
    issues = result.get("issues") or []
    color = _VERDICT_COLOR.get(verdict, _NEUTRAL_COLOR)
    emoji = _VERDICT_EMOJI.get(verdict, ":grey_question:")
    label = _claim_label(claim)

    blocks: list[dict] = [
        {"type": "header",
         "text": {"type": "plain_text", "text": f"{emoji} verity {verdict}"[:150]}},
        {"type": "section",
         "text": {"type": "mrkdwn", "text": f"*Claim:* {label}"}},
    ]

    # Per-dimension verdicts (empirical / evidence / consistency / grounding), when verify ran
    # them — a compact context line so a reader sees WHICH dimension tripped.
    dims = result.get("dimensions")
    if isinstance(dims, dict) and dims:
        dim_line = "  ".join(
            f"{name}: {(body or {}).get('verdict', '?') if isinstance(body, dict) else '?'}"
            for name, body in dims.items())
        blocks.append({"type": "context",
                       "elements": [{"type": "mrkdwn", "text": f"*Dimensions:* {dim_line}"}]})

    if issues:
        lines = []
        for i in issues:
            i = i if isinstance(i, dict) else {}
            sev = i.get("severity", "?")
            src = i.get("check") or i.get("source", "?")
            detail = i.get("detail", "")
            lines.append(f"• [{sev}] {src} — {detail}")
        # Slack hard-caps a single text object at 3000 chars; keep well under so a claim with a
        # long issue list can't produce an over-length block that Slack rejects (a rejected
        # payload is a dropped alert). Truncate with an explicit marker, never silently.
        body = "\n".join(lines)
        if len(body) > 2900:
            body = body[:2900].rsplit("\n", 1)[0] + "\n• … (truncated)"
        blocks.append({"type": "section", "text": {"type": "mrkdwn", "text": body}})
    else:
        blocks.append({"type": "section",
                       "text": {"type": "mrkdwn",
                                "text": "_No issues — claim clears the bar (these checks only, "
                                        "not a profit signal)._"}})

    # The notification-preview fallback text. Plain, scannable, and bounded.
    n = len(issues)
    fallback = f"verity {verdict}: {label} — {n} issue(s)" if n else f"verity {verdict}: {label}"

    return {"text": fallback,
            "attachments": [{"color": color, "blocks": blocks}]}


def _urllib_post(webhook_url: str, payload: dict, *, timeout: float = 10.0) -> dict:
    """Default transport: POST ``payload`` as JSON to a Slack incoming webhook via urllib (STDLIB).

    Returns a small ``{"status", "body"}`` dict — Slack answers an incoming webhook with the
    literal text ``ok`` and HTTP 200 on success. We do NOT raise on a non-200 here; the caller
    gets the status/body and decides. (A failed alert post should not, by itself, blow up the
    pipeline that was merely *trying* to warn you — but it must be visible, hence the returned
    status.) Network/timeout errors propagate as the usual ``urllib.error.URLError``."""
    data = json.dumps(payload).encode("utf-8")
    req = urllib.request.Request(
        webhook_url, data=data, method="POST",
        headers={"Content-Type": "application/json"})
    with urllib.request.urlopen(req, timeout=timeout) as resp:   # nosec B310 — caller-supplied https webhook
        return {"status": resp.status, "body": resp.read().decode("utf-8", "replace")}


def notify_slack(webhook_url: str, claim, truth: dict | None = None, *,
                 evidence: dict | None = None, prior: dict | None = None,
                 sources: list | None = None, transport=None) -> dict:
    """Verify ``claim`` and POST the color-coded verdict to a Slack incoming webhook.

    Runs the SAME ``verity.verify`` every other surface runs (empirical always; evidence /
    consistency / grounding when you supply ``evidence`` / ``prior`` / ``sources``), formats the
    result with ``format_slack_message``, and sends it.

    ``webhook_url`` is **always a parameter** — a Slack webhook is a secret; pass it from the
    environment / a secret store, never hard-code it.

    ``transport`` is the injectable sender: a callable ``(webhook_url, payload) -> response``.
    It defaults to a real ``urllib`` POST. Tests pass a fake that records the payload and returns
    a stub, so the wire contract is asserted **without any network**. Returns::

        {"verdict": "REFUSE"|"WARN"|"PASS"|...,
         "result":   <the full verify() dict>,
         "payload":  <the exact Slack payload that was sent>,
         "response": <whatever the transport returned>}

    so a caller (or a test) can inspect the verdict, the payload on the wire, and the send result
    in one shot. Pure orchestration: no verdict logic of its own.
    """
    send = transport if transport is not None else _urllib_post
    result = verify(claim, evidence=evidence, prior=prior, sources=sources, truth=truth)
    payload = format_slack_message(claim, result)
    response = send(webhook_url, payload)
    return {"verdict": result["verdict"], "result": result,
            "payload": payload, "response": response}
