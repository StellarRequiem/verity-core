"""The FINANCE domain pack (truths/finance.yaml) loads and behaves: an honest, fully-reconciled
earnings claim PASSES, while the four real financial-report failure modes are caught at their stated
severities — non-GAAP-without-reconciliation REFUSEs (CRITICAL), revenue-booked-not-earned and a
cherry-picked-period/undefined-cohort claim WARN (HIGH), and organic/acquired conflation WARNs
(MEDIUM).

This pack targets the EARNINGS / financial-statement layer (distinct from business.yaml's operational
KPI + supply-chain focus). Two things are easy to get wrong here and are pinned by these tests:
  * a finance figure is NOT an ML accuracy — ``suspicious_accuracy`` is 1.0 so a high margin / growth
    rate is not auto-suspected, and OOS / leakage are waived (a realized period has no holdout); the
    sample floor applies ONLY to cohort/retention rates (binomial-CI grounded), and a single-period
    aggregate that omits sample_size is never floored; and
  * the substring trap — every bad-claim test asserts the RIGHT ground-truth fact fired, which is
    exactly what a canonical-substring-of-forbidden suppression would hide, and a dedicated
    trap-defusal test proves a claim with ONLY forbidden terms (no canonical) still REFUSEs.
"""
from pathlib import Path

from verity import check, load_truth

PACKS = Path(__file__).resolve().parent.parent / "truths"


def _truth():
    return load_truth(PACKS / "finance.yaml")


def _ground_checks(claim, t):
    """The set of ground-truth check ids the pack raised for ``claim`` (what fired, by name)."""
    return {i["check"] for i in check(claim, t)["issues"] if i["source"] == "ground_truth"}


def test_finance_pack_no_canonical_is_substring_of_a_forbidden_term():
    """The SUBSTRING-TRAP invariant, asserted in-code: within every fact, no canonical term may be a
    substring of any forbidden term (else the canonical silently suppresses that forbidden flag)."""
    t = _truth()
    norm = lambda s: " ".join((s or "").lower().split())
    for f in t["facts"]:
        for c in f["canonical_terms"]:
            for fb in f["forbidden_terms"]:
                assert norm(c) not in norm(fb), (
                    f"canonical {c!r} is a substring of forbidden {fb!r} in fact {f['id']!r}")


def test_finance_pack_passes_honest_reconciled_earnings_claim():
    """An exemplary earnings release clears the bar: non-GAAP reconciled to GAAP (fact 1), revenue
    recognized under ASC 606 by sell-through (fact 2), a like-for-like comparable period with a stated
    cohort and denominator (fact 3), and organic-only growth excluding acquisitions (fact 4).

    No sample is floored: this is a single-period aggregate, so sample_size is omitted. A high margin
    (0.42) is present to prove ``suspicious_accuracy`` is 1.0 and does NOT auto-suspect it.
    """
    t = _truth()
    good = {
        "name": "q3-earnings-release",
        "accuracy": 0.42, "base_rate": 0.0,
        "text": ("adjusted ebitda presented gaap-reconciled with a full reconciliation to gaap; "
                 "recognized revenue under asc 606 measured by sell-through, revenue earned on "
                 "delivery; results on a like-for-like comparable period over the trailing twelve "
                 "months with a stated cohort and a stated denominator; organic-only growth that "
                 "excludes acquisitions, with the acquisition contribution broken out"),
    }
    res = check(good, t)
    assert res["verdict"] == "PASS", res["issues"]


def test_finance_pack_refuses_nongaap_without_reconciliation():
    """Headline adjusted earnings with NO reconciliation to GAAP — the #1 SEC comment-letter trigger.
    CRITICAL, so the verdict is REFUSE, via the non-GAAP-reconciliation fact."""
    t = _truth()
    bad = {
        "name": "adjusted-eps-headline",
        "text": ("adjusted eps and adjusted ebitda headline the release as non-gaap (unreconciled) "
                 "addbacks; a recurring item as one-time, with no gaap reconciliation provided"),
    }
    res = check(bad, t)
    assert res["verdict"] == "REFUSE", res["issues"]
    assert "nongaap_reconciliation" in _ground_checks(bad, t)        # fired, not suppressed


def test_finance_pack_warns_on_revenue_booked_not_earned():
    """Channel-stuffing / bookings-as-revenue is revenue booked but not yet earned under ASC 606.
    HIGH (no CRITICAL fact fires), so the verdict is WARN, via the revenue-recognition fact."""
    t = _truth()
    stuffed = {
        "name": "revenue-pull-forward",
        "text": ("the quarter's revenue reflects channel-stuffing and bill-and-hold invoices — "
                 "bookings counted as revenue and revenue pulled forward from next quarter"),
    }
    res = check(stuffed, t)
    assert res["verdict"] == "WARN", res["issues"]
    assert "revenue_recognition" in _ground_checks(stuffed, t)       # fired, not suppressed


def test_finance_pack_warns_on_cherry_picked_period_undefined_cohort():
    """A cherry-picked window with an undefined cohort and shifting denominator. HIGH → WARN, via the
    period/cohort/denominator fact."""
    t = _truth()
    window = {
        "name": "hand-picked-window",
        "text": ("growth quoted over a cherry-picked period — a 53-week year and a stub period — "
                 "against an undefined cohort and an undefined denominator"),
    }
    res = check(window, t)
    assert res["verdict"] == "WARN", res["issues"]
    assert "period_cohort_denominator" in _ground_checks(window, t)  # fired, not suppressed


def test_finance_pack_warns_on_organic_vs_acquired_conflation():
    """Acquisition revenue folded into a headline 'organic' growth number. MEDIUM → WARN, via the
    organic-vs-acquired fact."""
    t = _truth()
    conflated = {
        "name": "growth-headline",
        "text": "reported double-digit growth with acquired growth as organic and m&a-inflated growth",
    }
    res = check(conflated, t)
    assert res["verdict"] == "WARN", res["issues"]
    assert "organic_vs_acquired" in _ground_checks(conflated, t)     # fired, not suppressed


def test_finance_pack_substring_trap_is_defused_nongaap():
    """The core trap-defusal: a claim carrying ONLY forbidden terms (NO canonical) still REFUSEs.
    A bare "gaap" canonical would be a substring of "non-gaap (unreconciled)" and silently suppress
    the flag; the pack uses the specific "gaap-reconciled" instead. This proves the trap stays closed
    on the CRITICAL fact — the forbidden phrase contains no specific canonical, so it fires."""
    t = _truth()
    trap = {
        "name": "nongaap-only",
        "text": "earnings reported as non-gaap (unreconciled) with unreconciled adjustments",
    }
    res = check(trap, t)
    assert res["verdict"] == "REFUSE", res["issues"]
    assert "nongaap_reconciliation" in _ground_checks(trap, t)       # the trap stayed closed


def test_finance_pack_cohort_sample_floor_bites_but_aggregate_is_exempt():
    """The sample floor applies ONLY when a cohort/retention sample IS disclosed: a retention rate on
    12 accounts is anecdote (CRITICAL → REFUSE), while an otherwise-identical single-period aggregate
    that omits sample_size is NOT floored (PASS)."""
    t = _truth()
    base_text = ("recognized revenue under asc 606 on a like-for-like comparable period, "
                 "trailing twelve months, gaap-reconciled, organic-only growth")
    thin_cohort = {"name": "tiny-cohort-retention", "sample_size": 12, "text": base_text}
    res_thin = check(thin_cohort, t)
    assert res_thin["verdict"] == "REFUSE", res_thin["issues"]
    assert any(i["check"] == "sample_size" and i["severity"] == "CRITICAL"
               for i in res_thin["issues"])

    aggregate = {"name": "single-period-aggregate", "text": base_text}     # no sample_size
    res_agg = check(aggregate, t)
    assert res_agg["verdict"] == "PASS", res_agg["issues"]
