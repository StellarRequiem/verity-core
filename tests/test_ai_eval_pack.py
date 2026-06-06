"""The AI-EVAL domain pack (truths/ai-eval.yaml) loads and behaves.

The eval domain's failure modes are NOT trading's: a high score is legitimate (never
auto-suspect), but data contamination, a cherry-picked baseline, tuning on the test
set, and a noise-level headline are the real sins. These tests pin: an honest held-out
claim PASSES, a near-perfect score is NOT auto-suspect (the anti-trading-paranoia
principle), contamination/weak-baseline/tiny-sample are caught, and the substring trap
is defused (a forbidden term still fires when no canonical is present).
"""
from pathlib import Path

from verity import check, load_truth

PACKS = Path(__file__).resolve().parent.parent / "truths"


def _truth():
    return load_truth(PACKS / "ai-eval.yaml")


def test_ai_eval_pack_loads_with_domain_fit_thresholds():
    t = _truth()
    # The defining domain choice: a high AI score is legitimate — do NOT auto-suspect it.
    assert t["thresholds"]["suspicious_accuracy"] == 1.0
    assert t["thresholds"]["require_leakage_check"] is True       # decontamination is mandatory
    assert {f["id"] for f in t["facts"]} >= {
        "no_data_contamination", "honest_baseline", "eval_integrity", "reported_variance"}


def test_ai_eval_pack_passes_an_honest_held_out_claim():
    good = {
        "name": "model-x-on-benchmark-z",
        "accuracy": 0.91, "base_rate": 0.50, "sample_size": 5000,
        "out_of_sample": True, "leakage_checked": True,
        "z": 12.0, "p_value": 0.0001, "effect_size": 0.40,
        "ci_95": [0.90, 0.92], "std_error": 0.004, "n_comparisons": 1,
        "text": ("evaluated on a held-out test set; decontaminated via n-gram decontamination; "
                 "91% vs a strong baseline of 50%; averaged across multiple random seeds; "
                 "pre-registered evaluation on a blind test set"),
    }
    assert check(good, _truth())["verdict"] == "PASS"


def test_ai_eval_does_not_auto_suspect_a_high_score():
    # The anti-trading-paranoia test: 99% is a legitimate result here, not auto-suspect.
    high = {
        "name": "near-perfect-on-a-solved-task",
        "accuracy": 0.99, "base_rate": 0.50, "sample_size": 5000,
        "out_of_sample": True, "leakage_checked": True,
        "z": 30.0, "p_value": 1e-9, "effect_size": 0.80, "ci_95": [0.985, 0.995], "n_comparisons": 1,
        "text": ("99% accuracy on a held-out test set, decontaminated; strong baseline at 50%; "
                 "averaged across multiple random seeds; blind test set"),
    }
    res = check(high, _truth())
    assert res["verdict"] == "PASS"
    assert not any(i["check"] == "suspicious_accuracy" for i in res["issues"])


def test_ai_eval_refuses_disclosed_contamination():
    bad = {
        "name": "leaked-eval", "accuracy": 0.95, "base_rate": 0.50, "sample_size": 2000,
        "out_of_sample": True, "leakage_checked": True, "z": 10.0, "p_value": 0.001, "effect_size": 0.4,
        "text": ("95% on the benchmark — but a later audit found train-test overlap due to data "
                 "leakage: the test set in the training corpus"),
    }
    res = check(bad, _truth())
    assert res["verdict"] == "REFUSE"
    assert any(i["check"] == "no_data_contamination" for i in res["issues"])


def test_ai_eval_warns_on_a_weak_baseline():
    weak = {
        "name": "weak-baseline-claim", "accuracy": 0.70, "base_rate": 0.50, "sample_size": 3000,
        "out_of_sample": True, "leakage_checked": True, "z": 8.0, "p_value": 0.001, "effect_size": 0.3,
        "n_comparisons": 1,
        "text": ("70% on the benchmark, beats a weak baseline; held-out test set; decontaminated; "
                 "averaged across multiple random seeds"),
    }
    res = check(weak, _truth())
    assert res["verdict"] == "WARN"                              # HIGH (not CRITICAL) → warn, not refuse
    assert any(i["check"] == "honest_baseline" for i in res["issues"])


def test_ai_eval_refuses_an_underpowered_sample():
    tiny = {
        "name": "tiny-eval", "accuracy": 0.80, "base_rate": 0.50, "sample_size": 30,
        "out_of_sample": True, "leakage_checked": True,
        "text": ("80% on a held-out test set, decontaminated; strong baseline; "
                 "averaged across multiple random seeds"),
    }
    res = check(tiny, _truth())
    assert res["verdict"] == "REFUSE"
    assert any(i["check"] == "sample_size" for i in res["issues"])   # 30 < hard_min_sample 100


def test_ai_eval_substring_trap_is_defused():
    # Only forbidden contamination terms, NO canonical — the CRITICAL fact must still fire.
    trap = {
        "name": "contamination-only", "accuracy": 0.88, "base_rate": 0.50, "sample_size": 2000,
        "out_of_sample": True, "leakage_checked": True,
        "text": "benchmark contamination: the model memorized the benchmark via train-test overlap",
    }
    res = check(trap, _truth())
    assert res["verdict"] == "REFUSE"
    assert any(i["check"] == "no_data_contamination" for i in res["issues"])
