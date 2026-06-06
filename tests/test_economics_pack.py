"""The economics / econometrics domain pack loads and is tuned, not just present.

The core econometric distinction the pack must enforce: a result is only trustworthy if it is
IDENTIFIED. An honest claim — a stated design (IV / diff-in-diff / RDD), clustered/robust
standard errors, a multiple-comparison correction, a practical effect — PASSES; an unidentified,
uncontrolled, p-hacked association REFUSEs even when its p-value looks fine.

Also guards the substring trap baked into the gate (gate._match_facts): a canonical term that is a
SUBSTRING of a forbidden term would silently cancel the flag. We assert the bad claim genuinely
REFUSEs (not merely WARNs), which only holds if no canonical term suppresses the forbidden hit.
"""
from pathlib import Path

from verity import check, load_truth

PACK = Path(__file__).resolve().parent.parent / "truths" / "economics.yaml"


def _truth():
    return load_truth(PACK)


def test_economics_pack_passes_identified_corrected_claim():
    t = _truth()
    # Honest applied-micro result: a credible design, inference robust to clustering, multiplicity
    # corrected, significant with a real effect — and NOT auto-suspected for OOS/leakage (waived).
    good = {
        "sample_size": 8000,
        "p_value": 0.002,
        "effect_size": 0.34,
        "text": "difference-in-differences with a stated identification strategy; clustered "
                "standard errors, multiple-comparison correction (bonferroni), pre-analysis plan",
    }
    assert check(good, t)["verdict"] == "PASS"


def test_economics_pack_refuses_unidentified_uncontrolled_claim():
    t = _truth()
    # The textbook sin: a precise, significant coefficient with NO identification — correlation
    # dressed as causation. This MUST be a hard REFUSE (CRITICAL fact), which also proves no
    # canonical term is a substring of these forbidden terms (otherwise the flag is suppressed).
    bad = {
        "sample_size": 8000,
        "p_value": 0.002,
        "text": "observational regression coefficient, no controls, unidentified and p-hacked; "
                "correlation implies causation",
    }
    res = check(bad, t)
    assert res["verdict"] == "REFUSE"
    # be specific: the REFUSE is the identification fact firing, not some incidental check.
    assert any(i["check"] == "identification_and_inference" for i in res["issues"])


def test_economics_pack_floors_a_significant_but_negligible_effect():
    t = _truth()
    # Significance is NOT sufficient: a trivially-small effect that clears the p-bar at large n is
    # large-n p-hacking. The practical-effect floor must catch it even with a clean design.
    negligible = {
        "sample_size": 200000,
        "p_value": 0.001,
        "effect_size": 0.01,
        "text": "regression discontinuity with clustered standard errors and a pre-analysis plan",
    }
    res = check(negligible, t)
    assert res["verdict"] in ("WARN", "REFUSE")
    assert any(i["check"] == "effect_size" for i in res["issues"])


def test_economics_pack_waives_out_of_sample_and_leakage():
    t = _truth()
    # An econometric estimate is in-sample by construction; demanding a holdout / leakage check
    # would mis-fire. A well-identified claim that mentions NEITHER must still PASS.
    no_oos = {
        "sample_size": 5000,
        "p_value": 0.01,
        "effect_size": 0.25,
        "text": "instrumental variable estimate with robust standard errors and bonferroni correction",
    }
    res = check(no_oos, t)
    assert res["verdict"] == "PASS"
    assert not any(i["check"] in ("out_of_sample", "leakage") for i in res["issues"])
