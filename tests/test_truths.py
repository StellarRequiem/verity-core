"""The shipped domain truth packs load and behave — each PASSES a representative honest claim
and flags a domain-typical bad one. Proves the packs are valid + tuned, not just present."""
from pathlib import Path

from verity import check, load_truth

PACKS = Path(__file__).resolve().parent.parent / "truths"


def _truth(name):
    return load_truth(PACKS / name)


def test_ml_pack_passes_honest_classifier_refuses_no_lift():
    t = _truth("ml-classification.yaml")
    good = {"accuracy": 0.87, "sample_size": 5000, "out_of_sample": True, "leakage_checked": True, "base_rate": 0.51}
    assert check(good, t)["verdict"] == "PASS"
    no_lift = {"accuracy": 0.985, "sample_size": 90, "out_of_sample": False, "base_rate": 0.98}
    assert check(no_lift, t)["verdict"] == "REFUSE"


def test_trading_pack_auto_suspects_high_winrate():
    t = _truth("trading.yaml")
    suspect = {"win_rate": 0.72, "sample_size": 200, "out_of_sample": True, "leakage_checked": True}
    assert check(suspect, t)["verdict"] in ("WARN", "REFUSE")        # >0.65 is auto-suspect here
    honest = {"win_rate": 0.53, "sample_size": 500, "out_of_sample": True, "leakage_checked": True}
    assert check(honest, t)["verdict"] == "PASS"


def test_ab_pack_needs_significance_not_out_of_sample():
    t = _truth("ab-test.yaml")
    good = {"accuracy": 0.12, "sample_size": 50000, "leakage_checked": True, "z": 4.0}
    assert check(good, t)["verdict"] == "PASS"                       # no OOS needed; big + significant
    underpowered = {"accuracy": 0.12, "sample_size": 200, "leakage_checked": True, "z": 1.1}
    assert check(underpowered, t)["verdict"] == "REFUSE"             # tiny sample + z<2


def test_research_pack_requires_a_confidence_interval():
    t = _truth("research.yaml")
    no_ci = {"accuracy": 0.40, "sample_size": 200, "out_of_sample": True, "leakage_checked": True}
    assert any(i["check"] == "confidence_interval" for i in check(no_ci, t)["issues"])
    with_ci = {"accuracy": 0.40, "sample_size": 200, "out_of_sample": True, "leakage_checked": True,
               "ci_95": [0.35, 0.45]}
    assert check(with_ci, t)["verdict"] == "PASS"
