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


def test_clinical_trials_pack_flags_posthoc_subgroup():
    t = _truth("clinical-trials.yaml")
    good = {"sample_size": 500, "p_value": 0.001, "ci_95": [0.55, 0.65],
            "text": "pre-registered randomized double-blind trial, primary endpoint, intention-to-treat"}
    assert check(good, t)["verdict"] == "PASS"
    bad = {"sample_size": 40, "p_value": 0.04, "text": "post-hoc subgroup analysis showed efficacy"}
    assert check(bad, t)["verdict"] == "REFUSE"          # post-hoc subgroup is fabrication-class here


def test_genomics_pack_demands_genome_wide_significance():
    t = _truth("genomics.yaml")
    good = {"p_value": 1e-9, "sample_size": 50000,
            "text": "genome-wide significant association, replicated in an independent cohort"}
    assert check(good, t)["verdict"] == "PASS"
    bad = {"p_value": 1e-5, "sample_size": 800,
           "text": "candidate gene association, p < 0.05, single cohort"}
    assert check(bad, t)["verdict"] == "REFUSE"
    # the whole point of the pack: p=1e-5 is NOT significant at genome-wide scale
    assert any(i["check"] == "significance" for i in check(bad, t)["issues"])


def test_epidemiology_pack_flags_unadjusted_single_comparison():
    t = _truth("epidemiology.yaml")
    good = {"sample_size": 5000, "p_value": 0.001,
            "text": "adjusted association: confounders and multiple comparisons corrected (bonferroni)"}
    assert check(good, t)["verdict"] == "PASS"
    bad = {"sample_size": 5000, "p_value": 0.03,
           "text": "unadjusted association from a single comparison"}
    assert check(bad, t)["verdict"] == "REFUSE"          # unadjusted single comparison is CRITICAL
