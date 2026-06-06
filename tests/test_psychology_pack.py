"""The PSYCHOLOGY domain pack — the flagship, locked tight against the replication crisis.

Psychology is where the replication crisis was first measured, so this pack is the strictest of
the behavioral-science family: a pre-registered, confirmatory, adequately-powered, validated-measure
claim with a real sample, a strongly-significant p, a practical effect, and a confidence interval
PASSES; each of the three canonical failure modes — HARKing, p-hacking via researcher degrees of
freedom, and an unvalidated/underpowered measure — REFUSEs at CRITICAL.

The point of this file is not merely that the bad claims refuse, but that they refuse via the RIGHT
fact and are NOT silently suppressed by the canonical-substring trap (a canonical term that is a
substring of a forbidden phrase would make the forbidden phrase self-suppress). Each bad-claim test
asserts the specific ground-truth check id fired, which is exactly what suppression would hide.
"""
from pathlib import Path

from verity import check, load_truth

PACKS = Path(__file__).resolve().parent.parent / "truths"


def _truth():
    return load_truth(PACKS / "psychology.yaml")


def _ground_checks(claim, t):
    """The set of ground-truth check ids the pack raised for ``claim`` (what fired, by name)."""
    return {i["check"] for i in check(claim, t)["issues"] if i["source"] == "ground_truth"}


def test_honest_preregistered_powered_claim_passes():
    """An exemplary registered-report claim clears every gate, ground-truth AND structural.

    Pre-registered + confirmatory analysis + a-priori hypothesis (fact 1), pre-specified analysis with
    all measures reported (fact 2), a validated measure that is adequately powered (fact 3). Sample
    well over the floor (200 ≥ 100), p strongly significant (0.002 ≤ 0.01, so not even marginal),
    a practical effect (d=0.5 ≥ 0.1) the sample can detect, and a confidence interval present.
    """
    t = _truth()
    good = {
        "name": "registered-report-effect",
        "sample_size": 200,
        "p_value": 0.002,
        "effect_size": 0.5,
        "ci_95": [0.30, 0.70],
        "text": ("pre-registered confirmatory analysis of an a-priori hypothesis; "
                 "pre-specified analysis with all measures reported and a sensitivity analysis; "
                 "a validated measure, adequately powered, with a direct replication"),
    }
    res = check(good, t)
    assert res["verdict"] == "PASS", res["issues"]


def test_harking_refuses_and_is_not_suppressed():
    """A hypothesis invented after the results (HARKing) REFUSEs via the pre-registration fact.

    The text carries the forbidden tells of fact 1 (HARKing / a post-hoc hypothesis) and crucially
    contains NO fact-1 canonical — so the contradiction must SURFACE, not self-suppress. The asserts
    prove the prereg fact actually fired (suppression is precisely what would make this set empty).
    """
    t = _truth()
    harking = {
        "name": "harked-effect",
        "sample_size": 180,
        "p_value": 0.004,
        "effect_size": 0.4,
        "ci_95": [0.20, 0.60],
        "text": ("the study found a significant effect; the hypothesis was a post-hoc hypothesis "
                 "constructed after seeing the data — classic HARKing"),
    }
    res = check(harking, t)
    assert res["verdict"] == "REFUSE", res["issues"]
    assert "prereg_no_harking" in _ground_checks(harking, t)         # fired, not suppressed


def test_p_hacking_refuses_and_is_not_suppressed():
    """Researcher degrees of freedom (p-hacking) REFUSE via the analytic-flexibility fact.

    Forbidden tells of fact 2 (optional stopping, the garden of forking paths, undisclosed
    exclusions) with no fact-2 canonical present. The marginal p (0.041) is deliberately just-under
    the bar too — but the REFUSE is the CRITICAL ground-truth contradiction, which the assert pins.
    """
    t = _truth()
    phacked = {
        "name": "p-hacked-effect",
        "sample_size": 150,
        "p_value": 0.041,
        "effect_size": 0.3,
        "ci_95": [0.05, 0.55],
        "text": ("the analysis used optional stopping and undisclosed exclusions; significance "
                 "emerged from the garden of forking paths across many comparisons"),
    }
    res = check(phacked, t)
    assert res["verdict"] == "REFUSE", res["issues"]
    assert "prespecified_no_phacking" in _ground_checks(phacked, t)  # fired, not suppressed


def test_unvalidated_measure_refuses_and_is_not_suppressed():
    """An unvalidated, single-item, underpowered measure REFUSEs via the measurement fact.

    Forbidden tells of fact 3 (single-item measure / unvalidated scale / underpowered) with no fact-3
    canonical. Critically the honest-sounding "validated measure" canonical is ABSENT — its presence
    would suppress the flag, and the assert proves the measurement fact fired regardless.
    """
    t = _truth()
    bad_measure = {
        "name": "unvalidated-measure-effect",
        "sample_size": 120,
        "p_value": 0.006,
        "effect_size": 0.25,
        "ci_95": [0.05, 0.45],
        "text": ("the construct was assessed with a single-item measure on an unvalidated scale; "
                 "the design was underpowered for the reported effect"),
    }
    res = check(bad_measure, t)
    assert res["verdict"] == "REFUSE", res["issues"]
    assert "validated_powered_measure" in _ground_checks(bad_measure, t)  # fired, not suppressed


def test_confirmatory_substring_trap_does_not_self_suppress_harking():
    """The exact substring trap is closed: 'exploratory presented as confirmatory' still REFUSEs.

    The bare canonical 'confirmatory' would be a substring of this forbidden phrase and silently
    suppress fact 1; the pack uses the specific 'confirmatory analysis' instead. This regression
    test asserts the trap stays closed — the phrase contains no specific canonical, so it fires.
    """
    t = _truth()
    trap = {
        "name": "exploratory-as-confirmatory",
        "sample_size": 160,
        "p_value": 0.003,
        "effect_size": 0.45,
        "ci_95": [0.25, 0.65],
        "text": ("an exploratory finding from this experiment was exploratory presented as "
                 "confirmatory in the writeup"),
    }
    res = check(trap, t)
    assert res["verdict"] == "REFUSE", res["issues"]
    assert "prereg_no_harking" in _ground_checks(trap, t)            # the trap stayed closed
