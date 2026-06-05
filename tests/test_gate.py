"""The gate must refuse fabrication and pass honest results."""
from pathlib import Path

from verity.gate import check, load_truth

TRUTH = load_truth(Path(__file__).resolve().parent.parent / "verity" / "truth.yaml")


def test_refuses_fabrication():
    fake = {"name": "x", "accuracy": 0.72, "sample_size": 18,
            "out_of_sample": False, "leakage_checked": False,
            "text": "72% win rate, money printer"}
    assert check(fake, TRUTH)["verdict"] == "REFUSE"


def test_passes_honest_coin_flip():
    good = {"name": "y", "accuracy": 0.51, "sample_size": 300,
            "out_of_sample": True, "leakage_checked": True,
            "text": "daily directional signal: walk-forward holdout, "
                    "out-of-sample, no look-ahead, causal"}
    assert check(good, TRUTH)["verdict"] == "PASS"


def test_small_sample_is_critical():
    c = {"accuracy": 0.5, "sample_size": 5,
         "out_of_sample": True, "leakage_checked": True}
    r = check(c, TRUTH)
    assert r["verdict"] == "REFUSE"
    assert any(i["severity"] == "CRITICAL" for i in r["issues"])


def test_lookahead_in_description_is_caught():
    c = {"accuracy": 0.55, "sample_size": 300,
         "out_of_sample": True, "leakage_checked": True,
         "text": "signal that uses future returns, look-ahead"}
    r = check(c, TRUTH)
    assert r["verdict"] == "REFUSE"
    assert any(i.get("check") == "no_look_ahead" for i in r["issues"])


# ── rigor checks: fire ONLY when the claim discloses the relevant field ────────
def test_rigor_silent_when_fields_absent():
    """A sparse but honest claim is untouched by the rigor checks — nothing to scrutinise."""
    good = {"accuracy": 0.51, "sample_size": 300, "out_of_sample": True, "leakage_checked": True}
    assert check(good, TRUTH)["verdict"] == "PASS"


def test_rigor_flags_an_insignificant_z():
    # the real BTC backtest claim: honest, validated — but z=1.05 is a coin flip
    c = {"accuracy": 0.5252, "sample_size": 436, "out_of_sample": True, "leakage_checked": True,
         "z": 1.05}
    r = check(c, TRUTH)
    assert r["verdict"] == "WARN"
    assert any(i["check"] == "significance" for i in r["issues"])


def test_rigor_flags_multiple_comparisons_unless_corrected():
    c = {"accuracy": 0.58, "sample_size": 436, "out_of_sample": True, "leakage_checked": True,
         "n_comparisons": 8}
    assert any(i["check"] == "multiple_comparisons" for i in check(c, TRUTH)["issues"])
    # a disclosed multiplicity correction clears the flag
    assert not any(i["check"] == "multiple_comparisons"
                   for i in check({**c, "multiplicity_corrected": True}, TRUTH)["issues"])


def test_rigor_flags_no_lift_over_base_rate():
    c = {"accuracy": 0.55, "sample_size": 500, "out_of_sample": True, "leakage_checked": True,
         "base_rate": 0.60}
    r = check(c, TRUTH)
    assert r["verdict"] == "WARN"
    assert any(i["check"] == "base_rate" for i in r["issues"])


def test_rigor_confidence_interval_is_opt_in():
    c = {"accuracy": 0.55, "sample_size": 500, "out_of_sample": True, "leakage_checked": True}
    assert not any(i["check"] == "confidence_interval" for i in check(c, TRUTH)["issues"])
    truth_ci = {"thresholds": {"require_confidence_interval": True}, "facts": []}
    assert any(i["check"] == "confidence_interval" for i in check(c, truth_ci)["issues"])
