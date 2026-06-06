"""The BUSINESS domain pack (truths/business.yaml) loads and behaves: an honest, cohort-defined
C-suite claim PASSES, while a vanity / cherry-picked claim and a supply-chain-gamed claim REFUSE.

The pack verifies the-numbers-a-business-reports: a metric must have a defined denominator and
cohort, a real period (not a cherry-picked window), and beat a baseline. These tests also pin the
TWO things easy to get wrong here:
  * a RATE is not ML accuracy — ``suspicious_accuracy`` is 1.0, so an honest 18% retention is not
    auto-suspected, and OOS / leakage are waived (no ML-holdout notion for a KPI); and
  * the substring trap — bare canonical "gaap" is a SUBSTRING of forbidden "non-gaap (undisclosed)"
    and would silently suppress that flag, so the pack uses the specific "gaap-reconciled". The
    ``test_business_pack_substring_trap_is_defused`` case proves the forbidden term still REFUSEs.
"""
from pathlib import Path

from verity import check, load_truth

PACKS = Path(__file__).resolve().parent.parent / "truths"


def _truth():
    return load_truth(PACKS / "business.yaml")


def test_business_pack_passes_honest_cohort_defined_claim():
    """A like-for-like, defined-cohort, GAAP-reconciled claim across departments clears the bar."""
    t = _truth()
    good = {
        "name": "q3-net-revenue-retention",
        "sample_size": 1200, "p_value": 0.002, "base_rate": 0.0, "accuracy": 0.18,
        "text": ("like-for-like growth on a defined cohort over the trailing twelve months, "
                 "gaap-reconciled; net revenue retention reported with cohort retention and "
                 "fully-loaded cac; fulfilment measured as otif (perfect order rate, "
                 "end-to-end lead time)"),
    }
    assert check(good, t)["verdict"] == "PASS"


def test_business_pack_refuses_vanity_cherry_picked():
    """A vanity metric over a cherry-picked period with survivorship + undisclosed non-GAAP is fabrication-class."""
    t = _truth()
    bad = {
        "name": "record-quarter", "sample_size": 5000,
        "text": ("record revenue this dashboard quarter — a vanity metric over a cherry-picked "
                 "period with an undefined denominator and survivorship in the customer base; "
                 "non-gaap (undisclosed) adjustments"),
    }
    res = check(bad, t)
    assert res["verdict"] == "REFUSE"
    assert any(i["check"] == "metric_integrity" for i in res["issues"])


def test_business_pack_refuses_supply_chain_gamed():
    """Origin-only on-time + a backorder-excluding fill rate game the fulfilment number — REFUSE."""
    t = _truth()
    gamed = {
        "name": "logistics-scorecard", "sample_size": 800,
        "text": ("delivery scorecard: 99% on-time (origin only) and a 97% fill rate excluding "
                 "backorders across all shipment logistics"),
    }
    res = check(gamed, t)
    assert res["verdict"] == "REFUSE"
    assert any(i["check"] == "supply_chain" for i in res["issues"])


def test_business_pack_refuses_sales_marketing_gamed():
    """Blended CAC hiding paid + logo churn hiding revenue churn is a dishonest unit-economics story."""
    t = _truth()
    sales = {
        "name": "cac-story", "sample_size": 400,
        "text": "reporting blended cac (hiding paid) and logo churn hiding revenue churn in the funnel",
    }
    res = check(sales, t)
    assert res["verdict"] == "REFUSE"
    assert any(i["check"] == "sales_marketing" for i in res["issues"])


def test_business_pack_substring_trap_is_defused():
    """The whole point of "gaap-reconciled": an undisclosed non-GAAP claim with NO real canonical
    must STILL REFUSE. A bare "gaap" canonical would substring-match the forbidden phrase and
    silently suppress it — this proves it does not."""
    t = _truth()
    trap = {
        "name": "non-gaap-only", "sample_size": 5000,
        "text": "adjusted earnings via non-gaap (undisclosed) addbacks on the revenue dashboard",
    }
    res = check(trap, t)
    assert res["verdict"] == "REFUSE"
    assert any(i["check"] == "metric_integrity" for i in res["issues"])


def test_business_pack_rate_is_not_auto_suspected():
    """A high RATE (here a 0.82 retention) is not an ML accuracy — ``suspicious_accuracy`` is 1.0,
    so an honest cohort-defined claim does NOT trip the auto-suspect rule the trading pack uses."""
    t = _truth()
    high_rate = {
        "name": "gross-retention", "sample_size": 1500, "accuracy": 0.82, "base_rate": 0.0,
        "text": "gross revenue retention on a defined cohort, like-for-like, trailing twelve months",
    }
    res = check(high_rate, t)
    assert res["verdict"] == "PASS"
    assert not any(i["check"] == "suspicious_accuracy" for i in res["issues"])


def test_business_pack_sample_floor_still_bites():
    """OOS/leakage are waived, but the hard sample floor is not: below 30 accounts is anecdote."""
    t = _truth()
    thin = {
        "name": "tiny-cohort", "sample_size": 12,
        "text": "like-for-like defined cohort over the trailing twelve months, gaap-reconciled",
    }
    res = check(thin, t)
    assert res["verdict"] == "REFUSE"
    assert any(i["check"] == "sample_size" and i["severity"] == "CRITICAL" for i in res["issues"])
