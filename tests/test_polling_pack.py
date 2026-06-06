"""The POLLING domain pack (truths/polling.yaml) loads and behaves: a probability-sampled, margin-of-
error-disclosed, neutrally-worded, nonresponse-weighted poll PASSES, while the four canonical survey
failures fire at the right severity — a self-selected sample sold as representative REFUSEs (CRITICAL),
a margin-of-error omission and a push poll WARN (HIGH), and an undisclosed/unweighted nonresponse WARNs
(MEDIUM).

The pack verifies a-survey-is-actually-a-survey: a sample that can speak for the population (a
probability sample, not an opt-in straw poll), a stated margin of error, neutral wording, and
disclosed nonresponse handling. Thresholds are binomial-CI grounded — hard_min_sample 300 is the
±5.66% MOE floor at p=0.5, min_sample 1000 the ±3.10% industry standard, and min_effect_size 0.03
encodes "a lead within the MOE is not a lead." These tests also pin the things easy to get wrong:
  * a survey SHARE is not ML accuracy — ``suspicious_accuracy`` is 1.0, so an honest 82% approval is
    not auto-suspected, and OOS / leakage are waived (a survey is a one-shot population measurement);
  * the substring trap — bare canonical "probability sample" / "confidence interval" / "nonresponse
    weighting" would each be a SUBSTRING of a forbidden phrase ("non-probability sample" / "no
    confidence interval" / "no nonresponse weighting") and silently suppress it, so the pack uses the
    specific "probability-based sample" / "confidence interval stated" / "nonresponse-weighted". The
    ``test_polling_pack_substring_trap_is_defused`` case proves the forbidden term still REFUSEs.

Each bad-claim test asserts the SPECIFIC ground-truth check id fired — exactly what canonical
suppression would hide.
"""
from pathlib import Path

from verity import check, load_truth

PACKS = Path(__file__).resolve().parent.parent / "truths"


def _truth():
    return load_truth(PACKS / "polling.yaml")


def _ground_checks(claim, t):
    """The set of ground-truth check ids the pack raised for ``claim`` (what fired, by name)."""
    return {i["check"] for i in check(claim, t)["issues"] if i["source"] == "ground_truth"}


def test_polling_pack_passes_honest_probability_poll():
    """A probability-based, MOE-disclosed, neutrally-worded, nonresponse-weighted poll clears the bar.

    Sampling frame, margin of error, question wording, and nonresponse facts all satisfied; sample
    well over the 1000 floor (1500), p strongly significant (0.004 ≤ 0.01), a disclosed effect that
    clears the minimum detectable effect at the sample size, and a confidence interval present.
    """
    t = _truth()
    good = {
        "name": "national-tracking-poll",
        "sample_size": 1500, "p_value": 0.004, "effect_size": 0.12, "base_rate": 0.0,
        "accuracy": 0.52, "ci_95": [0.49, 0.55],
        "text": ("a probability-based sample via random-digit-dial and address-based sampling, "
                 "weighted to the population; margin of error reported (+/-2.5%), the lead is "
                 "outside the margin of error; neutral wording on a balanced question, split-sample "
                 "tested; response rate disclosed (aapor rr3), nonresponse-weighted and raked to "
                 "benchmarks"),
    }
    res = check(good, t)
    assert res["verdict"] == "PASS", res["issues"]


def test_polling_pack_refuses_self_selected_claimed_representative():
    """An opt-in, self-selected web panel sold as representative is fabrication-class — REFUSE.

    Forbidden tells of fact 1 (non-probability / self-selected / opt-in web panel) with NO fact-1
    canonical present, so the contradiction must SURFACE. The assert pins that the sampling_frame
    fact fired (suppression is precisely what would make this set empty).
    """
    t = _truth()
    bad = {
        "name": "web-straw-poll",
        "sample_size": 4000, "p_value": 0.001, "effect_size": 0.10, "base_rate": 0.0,
        "accuracy": 0.60, "ci_95": [0.58, 0.62],
        "text": ("an opt-in web panel of self-selected respondents on our website, a non-probability "
                 "sample presented as representative of all voters"),
    }
    res = check(bad, t)
    assert res["verdict"] == "REFUSE", res["issues"]
    assert "sampling_frame" in _ground_checks(bad, t)                # fired, not suppressed


def test_polling_pack_warns_no_margin_of_error():
    """A bare point estimate with no margin of error is incomplete — WARN via the margin_of_error fact.

    Forbidden tells of fact 2 (no margin of error / no confidence interval) with no fact-2 canonical;
    HIGH severity → WARN (a disclosure gap, not noise-floor REFUSE). The structural
    require_confidence_interval check also bites on a claim that discloses no error bar.
    """
    t = _truth()
    bad = {
        "name": "headline-lead",
        "sample_size": 1200, "p_value": 0.01, "effect_size": 0.05, "base_rate": 0.0,
        "accuracy": 0.50,
        "text": ("the poll of polled voters shows a 5-point lead but with no margin of error and no "
                 "confidence interval; a bare percentage estimate"),
    }
    res = check(bad, t)
    assert res["verdict"] == "WARN", res["issues"]
    assert "margin_of_error" in _ground_checks(bad, t)               # fired, not suppressed


def test_polling_pack_warns_push_poll_leading_question():
    """A push poll with a leading, loaded, one-sided question WARNs via the question_wording fact.

    Forbidden tells of fact 3 (push poll / leading question / loaded wording / one-sided framing)
    with no fact-3 canonical present; HIGH → WARN.
    """
    t = _truth()
    bad = {
        "name": "push-poll",
        "sample_size": 1100, "p_value": 0.02, "effect_size": 0.04, "base_rate": 0.0,
        "accuracy": 0.50, "ci_95": [0.48, 0.52],
        "text": ("a push poll using a leading question with loaded wording and one-sided framing "
                 "asked of respondents in the survey"),
    }
    res = check(bad, t)
    assert res["verdict"] == "WARN", res["issues"]
    assert "question_wording" in _ground_checks(bad, t)              # fired, not suppressed


def test_polling_pack_warns_undisclosed_unweighted_nonresponse():
    """An undisclosed response rate with no nonresponse weighting WARNs (MEDIUM) via fact 4.

    Forbidden tells of fact 4 (undisclosed response rate / no nonresponse weighting) with no fact-4
    canonical; MEDIUM severity → WARN, a quality gap rather than fabrication-class.
    """
    t = _truth()
    bad = {
        "name": "unweighted-poll",
        "sample_size": 1100, "p_value": 0.02, "effect_size": 0.05, "base_rate": 0.0,
        "accuracy": 0.50, "ci_95": [0.48, 0.52],
        "text": ("a survey of contacted respondents with an undisclosed response rate and no "
                 "nonresponse weighting applied to the completion data"),
    }
    res = check(bad, t)
    assert res["verdict"] == "WARN", res["issues"]
    gc = _ground_checks(bad, t)
    assert "nonresponse_weighting" in gc                             # fired, not suppressed
    assert gc == {"nonresponse_weighting"}                           # ONLY the MEDIUM fact, not REFUSE


def test_polling_pack_substring_trap_is_defused():
    """The whole point of "probability-based sample": a non-probability claim with NO real canonical
    must STILL REFUSE. A bare "probability sample" canonical would substring-match the forbidden
    "non-probability sample" and silently suppress it — this proves it does not."""
    t = _truth()
    trap = {
        "name": "nonprob-only",
        "sample_size": 5000, "p_value": 0.001, "effect_size": 0.10, "base_rate": 0.0,
        "accuracy": 0.60, "ci_95": [0.58, 0.62],
        "text": "a survey on a non-probability sample of respondents reported as representative",
    }
    res = check(trap, t)
    assert res["verdict"] == "REFUSE", res["issues"]
    assert "sampling_frame" in _ground_checks(trap, t)               # the trap stayed closed


def test_polling_pack_share_is_not_auto_suspected():
    """A high survey SHARE (here 0.82 approval) is not an ML accuracy — ``suspicious_accuracy`` is
    1.0, so an honest probability-sampled claim does NOT trip the auto-suspect rule the trading pack
    uses."""
    t = _truth()
    high_share = {
        "name": "approval-rating",
        "sample_size": 1500, "accuracy": 0.82, "base_rate": 0.0, "effect_size": 0.30,
        "p_value": 0.001, "ci_95": [0.79, 0.85],
        "text": ("a probability-based sample weighted to the population; margin of error reported, "
                 "neutral wording, response rate disclosed and nonresponse-weighted"),
    }
    res = check(high_share, t)
    assert res["verdict"] == "PASS", res["issues"]
    assert not any(i["check"] == "suspicious_accuracy" for i in res["issues"])


def test_polling_pack_sample_floor_still_bites():
    """OOS/leakage are waived, but the binomial sample floor is not: below 300 (±5.7% MOE) is anecdote."""
    t = _truth()
    thin = {
        "name": "tiny-poll",
        "sample_size": 150, "p_value": 0.04, "effect_size": 0.10, "base_rate": 0.0,
        "accuracy": 0.60, "ci_95": [0.55, 0.65],
        "text": ("a probability-based sample weighted to the population; margin of error reported, "
                 "neutral wording, response rate disclosed and nonresponse-weighted"),
    }
    res = check(thin, t)
    assert res["verdict"] == "REFUSE", res["issues"]
    assert any(i["check"] == "sample_size" and i["severity"] == "CRITICAL" for i in res["issues"])


def test_polling_pack_lead_within_moe_is_not_a_lead():
    """The effect-size floor encodes "a lead within the MOE is not a lead": a sub-3-point lead at
    n≈1000 is within the margin of error — a statistical tie. A disclosed effect of 0.02 < 0.03 trips
    the effect_size rigor check (HIGH → WARN), even on an otherwise-clean probability-sampled poll."""
    t = _truth()
    within_moe = {
        "name": "within-moe-lead",
        "sample_size": 1000, "p_value": 0.02, "effect_size": 0.02, "base_rate": 0.0,
        "accuracy": 0.50, "ci_95": [0.48, 0.52],
        "text": ("a probability-based sample weighted to the population; margin of error reported, "
                 "neutral wording, response rate disclosed and nonresponse-weighted; a 2-point lead"),
    }
    res = check(within_moe, t)
    assert res["verdict"] == "WARN", res["issues"]
    assert any(i["check"] == "effect_size" and i["severity"] == "HIGH" for i in res["issues"])
