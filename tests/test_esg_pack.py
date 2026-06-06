"""The ESG / SUSTAINABILITY / EMISSIONS pack (truths/esg.yaml) loads and detects greenwashing:
an honest, full-scope, independently-assured transition claim PASSES, while the field's classic
tells REFUSE/WARN — offsets with no additionality or double-counting (CRITICAL → REFUSE),
scope-1-only boundaries and cherry-picked/rebaselined baselines (HIGH → WARN), and self-reported
unaudited figures (MEDIUM → WARN).

This is a FACTS-heavy, non-statistical domain: the structural/statistical knobs are permissive
(no OOS, no leakage, no CI requirement, suspicious_accuracy=1.0 so a high % cut is not auto-suspect)
and the whole burden rides on the four ground-truth facts.

The substring-trap defusal is exercised explicitly on fact (4): the obvious canonical
"third-party assurance" is a SUBSTRING of the forbidden "no third-party assurance" and would
silently suppress it — the pack uses "independently assured" / "reasonable assurance opinion"
instead, and ``test_esg_pack_substring_trap_is_defused`` proves the forbidden term still fires.
"""
from pathlib import Path

from verity import check, load_truth

PACKS = Path(__file__).resolve().parent.parent / "truths"


def _truth():
    return load_truth(PACKS / "esg.yaml")


def test_esg_pack_passes_honest_transition_claim():
    """A full-value-chain (all three scopes), fixed-base-year, science-based, independently-assured
    claim built on additional-and-permanent verified removals clears the bar. A high reduction %
    (here accuracy=0.42) is NOT auto-suspect — suspicious_accuracy is 1.0 for this domain."""
    t = _truth()
    good = {
        "name": "fy2025-transition-plan",
        "accuracy": 0.42,  # a % reduction is a headline figure, NOT an ML sample — no sample_size here
        "text": ("emissions cut 42% against a fixed base year (vs 2019) under a science-based "
                 "target with a published base year recalculation policy; the ghg inventory covers "
                 "the full value chain across all three scopes (scope 3 included). Residual offsets "
                 "are additional and permanent, gold standard verified removals using retired "
                 "credits, and the disclosure is independently assured under a reasonable assurance "
                 "opinion"),
    }
    res = check(good, t)
    assert res["verdict"] == "PASS"
    assert not any(i["check"] == "suspicious_accuracy" for i in res["issues"])


def test_esg_pack_refuses_offset_additionality():
    """Offsets with no additionality + double-counting are fabrication-class — the reduction never
    happened. CRITICAL ground-truth → REFUSE."""
    t = _truth()
    bad = {
        "name": "carbon-neutral-via-offsets",
        "text": ("we are carbon neutral: the net zero claim rests on avoided-emissions credits with "
                 "no additionality, and the same offsets are double-counted against both the "
                 "national inventory and our corporate target (phantom credits, unverified offsets)"),
    }
    res = check(bad, t)
    assert res["verdict"] == "REFUSE"
    assert any(i["check"] == "offset_additionality" for i in res["issues"])


def test_esg_pack_warns_scope_and_baseline_gaming():
    """A scope-1-only boundary (omitting scope 3) on a cherry-picked, rebaselined year materially
    misstates the trend — two HIGH facts → WARN (no CRITICAL present, so not a REFUSE)."""
    t = _truth()
    gamed = {
        "name": "headline-40pct",
        "text": ("our footprint disclosure is scope 1 only and omits scope 3 (a partial value "
                 "chain), and the 40% reduction is measured against a cherry-picked baseline that "
                 "was rebaselined to flatter the trajectory"),
    }
    res = check(gamed, t)
    assert res["verdict"] == "WARN"
    assert any(i["check"] == "scope_coverage" and i["severity"] == "HIGH" for i in res["issues"])
    assert any(i["check"] == "baseline_integrity" and i["severity"] == "HIGH" for i in res["issues"])


def test_esg_pack_warns_self_reported_unaudited():
    """Self-reported, unaudited figures with no external assurance are a credibility gap — MEDIUM
    → WARN (not fatal on their own, but not believed without a third party)."""
    t = _truth()
    unaudited = {
        "name": "self-reported-esg",
        "text": ("the sustainability report figures are self-reported and unaudited with no "
                 "external assurance — self-attested by management"),
    }
    res = check(unaudited, t)
    assert res["verdict"] == "WARN"
    assert any(i["check"] == "third_party_assurance" and i["severity"] == "MEDIUM"
               for i in res["issues"])


def test_esg_pack_substring_trap_is_defused():
    """The whole point of "independently assured" over the obvious "third-party assurance": a claim
    with ONLY the forbidden term "no third-party assurance" and NO canonical evidence must STILL
    fire. A bare "third-party assurance" canonical would substring-match the forbidden phrase and
    silently suppress it — this proves it does not."""
    t = _truth()
    trap = {
        "name": "assurance-trap",
        "text": ("the esg report emissions disclosure carries no third-party assurance "
                 "whatsoever"),
    }
    res = check(trap, t)
    # MEDIUM fact → WARN, and crucially the third_party_assurance check MUST be present.
    assert res["verdict"] == "WARN"
    assert any(i["check"] == "third_party_assurance" for i in res["issues"]), (
        "the forbidden 'no third-party assurance' must fire — the canonical substring must NOT "
        "suppress it")


def test_esg_pack_does_not_fire_off_domain():
    """Domain-gating: a claim with none of the ESG keywords must not trip any ESG fact."""
    t = _truth()
    off_domain = {
        "name": "quarterly-sales", "sample_size": 500,
        "text": "quarterly sales pipeline conversion improved on a defined cohort, like-for-like",
    }
    res = check(off_domain, t)
    assert not any(i["check"] in {"offset_additionality", "scope_coverage",
                                  "baseline_integrity", "third_party_assurance"}
                   for i in res["issues"])
