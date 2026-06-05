"""Adversarial regressions — every case here is a weakness that was FOUND by trying to
fool the verifier, then FIXED. Two failure classes are guarded:

  * FALSE CONFIDENCE — a claim that should be caught silently PASSed (the worst failure
    for a verifier: it certifies a fabrication). The original bugs: a deceptive string
    boolean (``out_of_sample: "false"`` is truthy → holdout check bypassed), a metric
    outside [0,1], a NaN/inf "number", and a stringified numeric field that crashed the
    threshold compares (so the claim was never scored at all).
  * ROBUSTNESS / DoS — a hostile input that took the gate DOWN (a crash) instead of
    judging it. An input that can crash the verifier is an input that bypasses it. The
    originals: a non-dict claim, a non-JSON-serialisable field value, ``thresholds: None``,
    and a negative tolerance in a (poisoned) truth pack that flagged identical numbers.

Each test asserts the FIX holds AND, where relevant, that an honest variant is still clean
(the fix did not introduce a false alarm). All pure; nothing mocked.
"""
from pathlib import Path

import pytest

from verity.gate import _affirmed, _num, check, format_block, format_verify_block, load_truth
from verity.verify import verify

TRUTH = load_truth(Path(__file__).resolve().parent.parent / "verity" / "truth.yaml")


def _checks(res):
    return {i["check"] for i in res["issues"]}


# ── deceptive string booleans must NOT bypass the affirmation checks ───────────
@pytest.mark.parametrize("denial", ["false", "False", "FALSE", "no", "No", "0", "none", "off", ""])
def test_string_false_does_not_bypass_out_of_sample(denial):
    # "false"/"no"/… are TRUTHY strings; a naive `not claim.get(...)` would silence the check.
    res = check({"accuracy": 0.55, "sample_size": 300,
                 "out_of_sample": denial, "leakage_checked": True}, TRUTH)
    assert "out_of_sample" in _checks(res), f"{denial!r} bypassed the holdout check"


@pytest.mark.parametrize("denial", ["false", "no", "0", "none"])
def test_string_false_does_not_bypass_leakage(denial):
    res = check({"accuracy": 0.55, "sample_size": 300,
                 "out_of_sample": True, "leakage_checked": denial}, TRUTH)
    assert "leakage" in _checks(res), f"{denial!r} bypassed the leakage check"


def test_affirmed_helper_semantics():
    # affirmed: genuine truthy
    assert _affirmed(True) and _affirmed("yes") and _affirmed("done") and _affirmed(1)
    # NOT affirmed: false/denial-shaped/zero/missing
    for v in (False, None, 0, 0.0, "false", "no", "0", "none", "off", "", float("nan")):
        assert not _affirmed(v), v


def test_affirmed_string_false_evidence_still_overrides_when_genuinely_affirmed():
    # an unambiguous yes-string is taken at face value (so we don't over-flag honest claims)
    res = check({"accuracy": 0.51, "sample_size": 300,
                 "out_of_sample": "yes, walk-forward holdout", "leakage_checked": "verified"}, TRUTH)
    assert "out_of_sample" not in _checks(res)
    assert "leakage" not in _checks(res)


# ── impossible / non-finite metrics are caught, not certified ──────────────────
def test_accuracy_above_one_is_critical_refuse():
    res = check({"accuracy": 1.5, "sample_size": 500,
                 "out_of_sample": True, "leakage_checked": True}, TRUTH)
    assert res["verdict"] == "REFUSE"
    assert any(i["check"] == "metric_range" and i["severity"] == "CRITICAL" for i in res["issues"])


def test_accuracy_below_zero_is_critical_refuse():
    res = check({"accuracy": -0.2, "sample_size": 500,
                 "out_of_sample": True, "leakage_checked": True}, TRUTH)
    assert any(i["check"] == "metric_range" and i["severity"] == "CRITICAL" for i in res["issues"])


@pytest.mark.parametrize("bad", [float("nan"), float("inf"), float("-inf")])
def test_non_finite_accuracy_is_flagged_not_passed(bad):
    # a NaN/inf accuracy must NEVER be a silent PASS (NaN > 0.65 is False — the old bypass).
    res = check({"accuracy": bad, "sample_size": 500,
                 "out_of_sample": True, "leakage_checked": True}, TRUTH)
    assert res["verdict"] != "PASS"
    assert "metric_range" in _checks(res)


def test_valid_boundary_metrics_still_pass():
    # exactly 0.0 and 1.0 are valid; 0.0 must not trip the range check (only >1 / <0 do).
    for acc in (0.0, 1.0):
        res = check({"accuracy": acc, "sample_size": 500,
                     "out_of_sample": True, "leakage_checked": True,
                     "text": "walk-forward out-of-sample no look-ahead causal"}, TRUTH)
        assert "metric_range" not in _checks(res), acc


# ── stringified numeric fields are scored, never crash, and still trip the floor ──
def test_string_sample_size_still_trips_the_floor():
    # "5" parses to 5 < hard floor → CRITICAL (previously this raised TypeError).
    res = check({"accuracy": 0.5, "sample_size": "5",
                 "out_of_sample": True, "leakage_checked": True}, TRUTH)
    assert res["verdict"] == "REFUSE"
    assert "sample_size" in _checks(res)


def test_string_accuracy_is_scored_not_crashed():
    res = check({"accuracy": "0.99", "sample_size": 500,
                 "out_of_sample": True, "leakage_checked": True}, TRUTH)
    assert "suspicious_accuracy" in _checks(res)   # 0.99 > 0.65, read correctly


def test_unparseable_sample_size_is_flagged_unverifiable():
    res = check({"accuracy": 0.5, "sample_size": "lots",
                 "out_of_sample": True, "leakage_checked": True}, TRUTH)
    assert "sample_size" in _checks(res)           # disclosed-but-unreadable → flagged


def test_num_rejects_bool_and_non_finite():
    # bool is a flag, not a measurement; NaN/inf are fabrication-shaped → None (not scored numeric).
    assert _num(True) is None and _num(False) is None
    assert _num(float("nan")) is None and _num(float("inf")) is None
    assert _num("0.5") == 0.5 and _num(3) == 3.0


# ── hostile inputs do not crash the gate (a crash is a bypass) ─────────────────
@pytest.mark.parametrize("claim", [None, [], "a bare string", 42, 3.14, True])
def test_non_dict_claim_refused_not_crashed(claim):
    res = check(claim, TRUTH)
    assert res["verdict"] == "REFUSE"
    assert any(i["check"] == "malformed_claim" for i in res["issues"])
    # and the renderer must not crash on a non-dict claim either
    assert "VERIFIED" in format_block(claim, res)


def test_non_serialisable_field_value_does_not_crash():
    # a set / custom object is not JSON-serialisable; the gate must still score the claim.
    res = check({"accuracy": 0.5, "sample_size": 500, "out_of_sample": True,
                 "leakage_checked": True, "weird": {1, 2, 3}}, TRUTH)
    assert res["verdict"] in {"PASS", "WARN", "REFUSE"}


def test_thresholds_none_does_not_crash():
    res = check({"accuracy": 0.5, "sample_size": 500, "out_of_sample": True,
                 "leakage_checked": True}, {"thresholds": None, "facts": None})
    assert res["verdict"] in {"PASS", "WARN", "REFUSE"}


def test_non_dict_truth_does_not_crash():
    for bad_truth in (None, [], "x", 7):
        res = check({"accuracy": 0.5, "sample_size": 500, "out_of_sample": True,
                     "leakage_checked": True}, bad_truth)
        assert res["verdict"] in {"PASS", "WARN", "REFUSE"}


# ── verify(): same robustness through the orchestrator + its renderer ──────────
@pytest.mark.parametrize("claim", [None, [], "x", 42])
def test_verify_non_dict_claim_refused(claim):
    res = verify(claim, truth=TRUTH)
    assert res["verdict"] == "REFUSE"
    assert "VERIFIED" in format_verify_block(claim, res)


def test_verify_non_dict_evidence_and_prior_do_not_crash():
    res = verify({"accuracy": 0.5, "sample_size": 500, "out_of_sample": True, "leakage_checked": True},
                 evidence=[1, 2, 3], prior="not a dict", truth=TRUTH)
    # both supplied → both dimensions present (even though nothing reconciles), no crash
    assert "evidence" in res["dimensions"] and "consistency" in res["dimensions"]


# ── poisoned / fat-fingered truth: a negative tolerance must NOT false-alarm ───
def test_negative_tolerance_does_not_flag_identical_numbers():
    poison = {"thresholds": {"evidence_rel_tol": -1, "evidence_abs_tol": -1}, "facts": []}
    res = verify({"accuracy": 0.5}, evidence={"accuracy": 0.5}, truth=poison)
    assert not any(i["check"] == "evidence:accuracy" for i in res["issues"]), \
        "a negative tolerance falsely flagged identical numbers"


def test_nan_evidence_is_not_a_silent_numeric_agreement():
    # NaN != NaN; a NaN-vs-NaN field must not be reported as 'agreeing' (it routes to type-mismatch).
    res = verify({"x": float("nan")}, evidence={"x": float("nan")}, truth=TRUTH)
    assert any(i["check"] == "evidence_type" for i in res["issues"])


def test_evidence_real_disagreement_still_critical_under_clamp():
    # the clamp must not weaken a genuine mismatch — 0.72 vs 0.58 is still CRITICAL.
    res = verify({"accuracy": 0.72, "sample_size": 500, "out_of_sample": True, "leakage_checked": True},
                 evidence={"accuracy": 0.58}, truth=TRUTH)
    assert res["verdict"] == "REFUSE"
    assert any(i["check"] == "evidence:accuracy" and i["severity"] == "CRITICAL"
               for i in res["issues"])
