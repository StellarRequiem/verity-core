"""The neuroscience (neuroimaging / fMRI) truth pack loads and is tuned — it PASSES an honest,
multiple-comparison-corrected study and REFUSEs the domain-typical sins (uncorrected whole-brain,
double dipping / circular analysis, underpowered n). The pack's whole reason to exist is that
"significant" at a single voxel means nothing without correction across the tens of thousands tested.
"""
from pathlib import Path

from verity import check, load_truth

PACKS = Path(__file__).resolve().parent.parent / "truths"


def _truth():
    return load_truth(PACKS / "neuroscience.yaml")


def test_neuroscience_pack_passes_corrected_refuses_uncorrected_circular():
    t = _truth()
    # HONEST: correction across voxels, adequate n, significant after correction, an independent
    # (pre-registered) ROI — exactly what a trustworthy fMRI result discloses.
    good = {"sample_size": 40, "p_value": 0.002,
            "text": "whole-brain GLM, cluster-corrected with a permutation test (FWE p<0.05); "
                    "effect tested in a pre-registered ROI, independent of the selection contrast"}
    assert check(good, t)["verdict"] == "PASS"
    # BAD: uncorrected whole-brain + double dipping on a circular analysis, underpowered n — the
    # textbook false-positive imaging result. Forbidden-class here, so it REFUSEs.
    bad = {"sample_size": 12, "p_value": 0.001,
           "text": "whole-brain analysis at p<0.001 uncorrected; double dipping on a circular "
                   "analysis of the voxels selected by the same contrast"}
    assert check(bad, t)["verdict"] == "REFUSE"


def test_neuroscience_pack_fires_the_correction_fact():
    # The point of the pack: a result reported UNCORRECTED for multiple comparisons is refused even
    # when sample size and p-value are otherwise pristine — the CRITICAL must come from the fact.
    t = _truth()
    uncorrected = {"sample_size": 50, "p_value": 0.001,
                   "text": "whole-brain fMRI activation reported uncorrected for multiple comparisons"}
    res = check(uncorrected, t)
    assert res["verdict"] == "REFUSE"
    assert any(i["check"] == "multiple_comparison_correction" for i in res["issues"])


def test_neuroscience_pack_avoids_canonical_substring_trap():
    # Regression guard for the gate's documented trap: a canonical term that is a SUBSTRING of a
    # forbidden term would be silently present in any claim using that forbidden term and suppress
    # the flag. "cluster-corrected" must NOT suppress "uncorrected". Assert mechanically that no
    # canonical term is a substring of any forbidden term, AND that the bad claim still REFUSEs.
    t = _truth()
    fact = next(f for f in t["facts"] if f["id"] == "multiple_comparison_correction")
    norm = lambda s: " ".join(s.lower().split())
    for c in fact["canonical_terms"]:
        for f in fact["forbidden_terms"]:
            assert norm(c) not in norm(f), f"canonical {c!r} is a substring of forbidden {f!r} — TRAP"
    # the forbidden term in isolation, with no canonical phrasing anywhere, must REFUSE
    bad = {"sample_size": 40, "p_value": 0.01,
           "text": "voxel-wise BOLD contrast, uncorrected"}
    assert check(bad, t)["verdict"] == "REFUSE"
