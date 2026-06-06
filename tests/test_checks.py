"""Deeper statistical-rigor checks (R1 effect-size floor, R2 power/MDE, R3 CI coherence).

Each new check obeys the gate's standing rule: it fires ONLY when the claim discloses the
relevant field, so a sparse-but-honest claim is never newly flagged (the pre-existing suite in
test_gate.py / test_truths.py proves that invariant holds). These tests assert, per check:

  * it FIRES (right id, right severity) when its field is present and the value is bad,
  * it is SILENT when its field is absent OR the value is fine,
  * it COEXISTS with the existing rigor checks (significance / base_rate / …),

and they keep the claims engineered so exactly one new check is under test at a time
(e.g. a huge sample silences the power check while the effect-size floor is exercised).
"""
import math
from pathlib import Path

from verity.gate import check, load_truth

TRUTH = load_truth(Path(__file__).resolve().parent.parent / "verity" / "truth.yaml")


def _checks(claim, truth=TRUTH):
    return [i["check"] for i in check(claim, truth)["issues"]]


def _issue(claim, cid, truth=TRUTH):
    """The first issue dict with check==cid, or None."""
    return next((i for i in check(claim, truth)["issues"] if i["check"] == cid), None)


# A clean, validated, fully-disclosed base claim that PASSES — every test perturbs ONE field of
# this so the perturbation is the sole cause of any new issue. (strong effect + huge n so neither
# the effect-size floor nor the power check fire on the baseline.)
CLEAN = {"accuracy": 0.55, "sample_size": 100_000, "out_of_sample": True,
         "leakage_checked": True, "effect_size": 0.8,
         "text": "walk-forward, out-of-sample, no look-ahead, causal"}


def test_clean_baseline_passes_and_new_checks_silent():
    """The disclosed-but-healthy baseline clears the bar — none of R1/R2/R3 fire."""
    r = check(CLEAN, TRUTH)
    assert r["verdict"] == "PASS", r["issues"]
    fired = {i["check"] for i in r["issues"]}
    assert not ({"effect_size", "underpowered", "ci_coherence"} & fired)


# ── R1: effect-size floor ──────────────────────────────────────────────────────
def test_r1_negligible_effect_size_flagged_high():
    # es below the 0.1 floor; huge n keeps the power check (R2) silent so R1 is isolated.
    bad = {**CLEAN, "effect_size": 0.05}
    iss = _issue(bad, "effect_size")
    assert iss is not None and iss["severity"] == "HIGH"
    assert "underpowered" not in _checks(bad)              # isolated: only R1 fired
    assert check(bad, TRUTH)["verdict"] == "WARN"          # a rigor gap is a WARN, not REFUSE


def test_r1_reads_cohens_d_and_d_aliases():
    for key in ("cohens_d", "d"):
        c = {k: v for k, v in CLEAN.items() if k != "effect_size"}
        c[key] = 0.02
        assert "effect_size" in _checks(c), key


def test_r1_silent_when_effect_size_absent():
    no_es = {k: v for k, v in CLEAN.items() if k != "effect_size"}
    assert "effect_size" not in _checks(no_es)


def test_r1_silent_when_effect_size_adequate():
    assert "effect_size" not in _checks({**CLEAN, "effect_size": 0.3})


def test_r1_threshold_is_config_overridable():
    # raise the floor and a previously-adequate 0.3 effect now trips it
    strict = {"thresholds": {"min_effect_size": 0.5}, "facts": []}
    assert "effect_size" in _checks({**CLEAN, "effect_size": 0.3}, strict)


# ── R2: statistical power / minimum detectable effect ──────────────────────────
def test_r2_underpowered_disclosed_effect_flagged_high():
    # es=0.3 is ABOVE the R1 floor (so R1 stays silent), but n=50 can't detect it at 80% power.
    bad = {**CLEAN, "effect_size": 0.3, "sample_size": 50}
    iss = _issue(bad, "underpowered")
    assert iss is not None and iss["severity"] == "HIGH"
    assert "effect_size" not in _checks(bad)               # isolated: only R2 fired (not R1)
    n_needed = math.ceil(((1.96 + 0.84) / 0.3) ** 2)
    assert f"~{n_needed}" in iss["detail"]                 # reports the n needed for 80% power


def test_r2_underpowered_via_proportion_lift():
    # no effect_size disclosed -> the effect is the accuracy − base_rate lift; tiny n is underpowered
    c = {"accuracy": 0.53, "base_rate": 0.50, "sample_size": 100,
         "out_of_sample": True, "leakage_checked": True}
    assert "underpowered" in _checks(c)


def test_r2_silent_when_no_effect_disclosed():
    # only accuracy + n, no effect_size and no base_rate -> nothing to compute power against
    c = {"accuracy": 0.55, "sample_size": 50, "out_of_sample": True, "leakage_checked": True}
    assert "underpowered" not in _checks(c)


def test_r2_silent_when_no_sample_size():
    no_n = {k: v for k, v in CLEAN.items() if k != "sample_size"}
    no_n["effect_size"] = 0.3
    assert "underpowered" not in _checks(no_n)


def test_r2_silent_when_adequately_powered():
    # es=0.5 with n=200: mde ≈ 0.198 < 0.5, so the sample CAN detect the effect
    assert "underpowered" not in _checks({**CLEAN, "effect_size": 0.5, "sample_size": 200})


def test_r2_power_constants_are_config_overridable():
    ok = {**CLEAN, "effect_size": 0.3, "sample_size": 200}
    assert "underpowered" not in _checks(ok)               # default constants: powered
    # demand a far larger z_beta -> mde grows -> the same n is now underpowered
    strict = {"thresholds": {"power_z_beta": 5.0}, "facts": []}
    assert "underpowered" in _checks(ok, strict)


# ── R3: confidence-interval coherence ──────────────────────────────────────────
def test_r3_point_estimate_outside_its_own_ci_flagged_high():
    # accuracy 0.55 but CI [0.60, 0.70] does not bracket it -> incoherent / typo'd
    bad = {**CLEAN, "ci_95": [0.60, 0.70]}
    iss = _issue(bad, "ci_coherence")
    assert iss is not None and iss["severity"] == "HIGH"
    assert "outside its own ci" in iss["detail"].lower()


def test_r3_degenerate_width_flagged_high():
    bad = {**CLEAN, "ci": [0.55, 0.55]}                    # est inside, but width == 0
    iss = _issue(bad, "ci_coherence")
    assert iss is not None and iss["severity"] == "HIGH"
    assert "degenerate" in iss["detail"].lower()


def test_r3_inverted_interval_is_degenerate():
    bad = {**CLEAN, "confidence_interval": [0.60, 0.50]}   # hi < lo -> width < 0
    # est 0.55 is NOT within [0.60,0.50] by the lo<=est<=hi rule, so BOTH sub-rules can speak;
    # the degenerate-width HIGH must be present.
    assert any(i["check"] == "ci_coherence" and "degenerate" in i["detail"].lower()
               for i in check(bad, TRUTH)["issues"])


def test_r3_overwide_interval_flagged_medium_not_high():
    # est inside, but the interval spans > the whole [0,1] metric range -> uninformative (MEDIUM)
    wide = {**CLEAN, "ci_95": [-0.5, 0.7]}                 # width 1.2 > max_ci_width 1.0, 0.55 inside
    iss = _issue(wide, "ci_coherence")
    assert iss is not None and iss["severity"] == "MEDIUM"
    assert "uninformative" in iss["detail"].lower()


def test_r3_silent_for_a_coherent_interval():
    good = {**CLEAN, "ci_95": [0.50, 0.60]}                # brackets 0.55, sane width
    assert "ci_coherence" not in _checks(good)


def test_r3_silent_when_no_ci_disclosed():
    assert "ci_coherence" not in _checks(CLEAN)            # CLEAN carries no CI field


def test_r3_silent_when_ci_not_two_elements():
    # a malformed / non-pair CI is not coerced into a coherence judgement
    assert "ci_coherence" not in _checks({**CLEAN, "ci": [0.5]})
    assert "ci_coherence" not in _checks({**CLEAN, "ci": [0.4, 0.5, 0.6]})


def test_r3_max_ci_width_is_config_overridable():
    c = {**CLEAN, "ci_95": [0.50, 0.62]}                   # width 0.12, brackets 0.55
    assert "ci_coherence" not in _checks(c)                # fine under default max_ci_width=1.0
    strict = {"thresholds": {"max_ci_width": 0.05}, "facts": []}
    iss = _issue(c, "ci_coherence", strict)
    assert iss is not None and iss["severity"] == "MEDIUM"


# ── R4: marginal significance (a just-significant p is fragile) ─────────────────
def test_r4_marginal_p_flagged_medium():
    # 0.01 < p <= 0.05 — "just significant"; held-out-validated as fragile on 1,772 real
    # replications (marginal claims replicated 42% vs 59% for strongly significant ones).
    iss = _issue({**CLEAN, "p_value": 0.03}, "marginal_significance")
    assert iss is not None and iss["severity"] == "MEDIUM"


def test_r4_strong_p_is_silent():
    # p <= 0.01 — strongly significant: neither the marginal caution nor the insignificance flag
    fired = _checks({**CLEAN, "p_value": 0.005})
    assert "marginal_significance" not in fired and "significance" not in fired


def test_r4_insignificant_p_is_significance_not_marginal():
    # p > 0.05 — the existing HIGH 'significance' fires; the marginal caution must NOT double-fire
    fired = _checks({**CLEAN, "p_value": 0.06})
    assert "significance" in fired and "marginal_significance" not in fired


def test_r4_silent_when_no_p_disclosed():
    # the standing rule: no p_value disclosed -> no marginal flag
    assert "marginal_significance" not in _checks(CLEAN)


def test_r4_marginal_floor_is_configurable():
    # the 0.01 floor is the principled default, but tunable; widen it and a p of 0.005 becomes marginal
    wide = {"thresholds": {"marginal_p_floor": 0.001}, "facts": []}
    assert _issue({**CLEAN, "p_value": 0.005}, "marginal_significance", wide) is not None


# ── coexistence with the existing rigor checks ─────────────────────────────────
def test_new_checks_coexist_with_significance_and_base_rate():
    # one claim that simultaneously trips an EXISTING check (significance, z<2) and a NEW one
    # (ci_coherence, est outside CI) — both must be reported, proving no mutual clobbering.
    c = {"accuracy": 0.55, "sample_size": 100_000, "out_of_sample": True, "leakage_checked": True,
         "effect_size": 0.8, "z": 1.05, "ci_95": [0.60, 0.70],
         "text": "walk-forward, out-of-sample, no look-ahead, causal"}
    fired = set(_checks(c))
    assert {"significance", "ci_coherence"} <= fired


def test_new_checks_do_not_disturb_the_honest_pass():
    # the canonical honest coin-flip (from test_gate) still PASSES — the new checks add no noise
    # because it discloses none of effect_size / CI, and its accuracy carries no base_rate to
    # power-test against.
    good = {"accuracy": 0.51, "sample_size": 300, "out_of_sample": True, "leakage_checked": True,
            "text": "daily directional signal: walk-forward holdout, out-of-sample, "
                    "no look-ahead, causal"}
    assert check(good, TRUTH)["verdict"] == "PASS"
