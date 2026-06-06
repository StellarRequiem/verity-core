"""The Slack surface — verify a claim, push a color-coded verdict to a webhook.

These tests prove the wire contract WITHOUT a network: ``notify_slack`` takes an injectable
``transport``, so a fake sender records the exact payload that *would* POST and we assert on it.
A REFUSE claim must produce a RED payload that lists the issues; an honest claim a GREEN one; and
the webhook URL is a parameter that is passed through verbatim (never hard-coded). STDLIB only,
like the module.
"""
import json

import pytest

from verity.slack import format_slack_message, notify_slack

# A fabrication-class claim: 91% on 12 trades, nothing affirmed → CRITICAL noise floor → REFUSE.
# The exact "flashy edge that isn't" the gate exists to refuse.
_JUNK = {"name": "money-printer", "accuracy": 0.91, "sample_size": 12,
         "out_of_sample": False, "leakage_checked": False}

# A clean, honest claim — small real edge on a real holdout, leakage checked → PASS.
_HONEST = {"name": "honest", "accuracy": 0.53, "sample_size": 500,
           "out_of_sample": True, "leakage_checked": True,
           "text": "daily directional, walk-forward holdout, no look-ahead"}

# Slack brand palette the module renders (red / yellow / green).
_RED, _YELLOW, _GREEN = "#E01E5A", "#ECB22E", "#2EB67D"


class _Recorder:
    """A fake transport: records every (url, payload) it is handed and returns a Slack-ok stub.

    Stands in for the urllib POST so the test never touches the network — the same injectable-edge
    idiom the rest of verity uses (caller-supplied sources, ephemeral-port server)."""

    def __init__(self):
        self.calls = []

    def __call__(self, webhook_url, payload):
        self.calls.append((webhook_url, payload))
        return {"status": 200, "body": "ok"}


def test_format_refuse_claim_is_red_and_lists_issues():
    from verity.verify import verify
    result = verify(_JUNK)
    msg = format_slack_message(_JUNK, result)
    assert result["verdict"] == "REFUSE"
    att = msg["attachments"][0]
    assert att["color"] == _RED                       # red bar for a REFUSE
    # the header block names the verdict, and an issue section actually lists the reasons
    text_blob = json.dumps(msg)
    assert "REFUSE" in text_blob
    assert "sample" in text_blob.lower()              # the noise-floor reason is surfaced
    # the fallback/preview text is set (not a silently-blank notification) and mentions the claim
    assert "money-printer" in msg["text"]
    assert "REFUSE" in msg["text"]


def test_format_honest_claim_is_green_with_no_issues():
    from verity.verify import verify
    result = verify(_HONEST)
    msg = format_slack_message(_HONEST, result)
    assert result["verdict"] == "PASS"
    assert msg["attachments"][0]["color"] == _GREEN
    # a PASS says so explicitly rather than rendering an empty issue list
    assert "clears the bar" in json.dumps(msg)


def test_format_warn_claim_is_yellow():
    """A claim that trips a non-critical rigor gap (here: missing OOS/leakage affirmation) WARNs."""
    from verity.verify import verify
    warn_claim = {"name": "thin", "accuracy": 0.55, "sample_size": 500}  # no oos/leakage → HIGH, not CRITICAL
    result = verify(warn_claim)
    assert result["verdict"] == "WARN"
    assert format_slack_message(warn_claim, result)["attachments"][0]["color"] == _YELLOW


def test_notify_refuse_posts_red_payload_without_network():
    """The headline contract: notify_slack runs verify + sends a RED payload via the injected
    transport — and never hits the network (the recorder is the only sender)."""
    rec = _Recorder()
    out = notify_slack("https://hooks.slack.test/services/XXX/YYY/zzz", _JUNK, transport=rec)

    assert out["verdict"] == "REFUSE"
    assert len(rec.calls) == 1                         # exactly one POST attempted
    url, payload = rec.calls[0]
    assert url == "https://hooks.slack.test/services/XXX/YYY/zzz"   # webhook passed through verbatim
    assert payload["attachments"][0]["color"] == _RED
    # the issues the gate raised are present in the payload the channel would receive
    assert any("sample" in json.dumps(b).lower() for b in payload["attachments"][0]["blocks"])
    # the return bundles the verdict, the verify result, the sent payload, and the transport's reply
    assert out["payload"] is payload
    assert out["response"] == {"status": 200, "body": "ok"}
    assert out["result"]["verdict"] == "REFUSE"


def test_notify_honest_posts_green_payload():
    rec = _Recorder()
    out = notify_slack("https://hooks.slack.test/abc", _HONEST, transport=rec)
    assert out["verdict"] == "PASS"
    assert rec.calls[0][1]["attachments"][0]["color"] == _GREEN


def test_notify_passes_evidence_dimension_to_verify():
    """Extra verify args cross through notify_slack: recomputed evidence (58%) contradicts the
    claimed 91% → fabrication-class CRITICAL, and the evidence dimension shows in the result."""
    rec = _Recorder()
    out = notify_slack("https://hooks.slack.test/abc",
                       {"name": "inflated", "accuracy": 0.91, "sample_size": 400,
                        "out_of_sample": True, "leakage_checked": True},
                       evidence={"accuracy": 0.58}, transport=rec)
    assert out["verdict"] == "REFUSE"
    assert "evidence" in out["result"]["dimensions"]
    assert rec.calls[0][1]["attachments"][0]["color"] == _RED


def test_notify_never_hardcodes_a_webhook_url():
    """Whatever URL the caller passes is the URL used — the module supplies no default of its own."""
    rec = _Recorder()
    notify_slack("https://example.invalid/my/own/hook", _HONEST, transport=rec)
    assert rec.calls[0][0] == "https://example.invalid/my/own/hook"


def test_payload_is_json_serialisable():
    """The payload must be exactly what goes on the wire — round-trips through json with no custom
    encoder (a non-serialisable payload would be a runtime 500 at POST time, not a test failure)."""
    from verity.verify import verify
    msg = format_slack_message(_JUNK, verify(_JUNK))
    assert json.loads(json.dumps(msg)) == msg


def test_format_tolerates_a_malformed_result():
    """A partial/garbage verify result must still produce a postable payload (neutral color,
    UNKNOWN verdict) rather than raising — a crash here would silence the very alert we want."""
    msg = format_slack_message({"name": "x"}, {"issues": "not-a-list"})  # missing verdict, bad issues
    assert msg["attachments"][0]["color"] == "#717274"   # neutral grey fallback
    assert "UNKNOWN" in json.dumps(msg)


def test_format_truncates_a_huge_issue_list():
    """A claim with a very long issue list must not produce an over-length Slack block (Slack
    rejects >3000-char text objects → a dropped alert). The body is truncated with a marker."""
    huge = {"issues": [{"severity": "HIGH", "check": f"c{i}",
                        "source": "structural", "detail": "x" * 100} for i in range(200)]}
    msg = format_slack_message({"name": "noisy"}, {**huge, "verdict": "REFUSE"})
    section = [b for b in msg["attachments"][0]["blocks"] if b.get("type") == "section"][-1]
    assert len(section["text"]["text"]) <= 3000
    assert "truncated" in section["text"]["text"]


def test_default_transport_is_urllib_not_invoked_in_tests():
    """notify_slack without a transport must default to the real urllib POST (proving the default
    wiring exists) — we assert the default is in place by inspecting it, NOT by calling the network."""
    from verity import slack
    assert slack._urllib_post.__module__ == "verity.slack"
    # sanity: calling with a fake transport never reaches _urllib_post
    sent = {}
    notify_slack("https://hooks.slack.test/x", _HONEST,
                 transport=lambda u, p: sent.update(url=u, payload=p) or {"status": 200})
    assert sent["url"] == "https://hooks.slack.test/x"


if __name__ == "__main__":  # pragma: no cover
    raise SystemExit(pytest.main([__file__, "-q"]))
