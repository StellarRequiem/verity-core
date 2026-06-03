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
