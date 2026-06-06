"""The JOURNALISM domain pack (truths/journalism.yaml) loads and behaves: an honest, named-source,
in-context, grounded, disclosed news claim PASSES, while the domain-typical sins REFUSE/WARN.

This is the verify-the-reporting layer — sourcing, context, statistical grounding, disclosure — and
is DELIBERATELY NOT the research pack's causal-inference scope. These tests pin the things easy to get
wrong here:
  * an unsourced / single-anonymous-source assertion is fabrication-class -> REFUSE (CRITICAL);
  * a cherry-picked quote and a denominator-free statistic mislead -> WARN (HIGH);
  * an undisclosed conflict / sponsored-as-news is a trust breach -> WARN (MEDIUM);
  * a reported percentage is NOT an ML accuracy (suspicious_accuracy=1.0) and OOS/leakage are waived,
    so an honest story with a high number does not get auto-suspected; and
  * the substring trap — bare canonical "named source" is a SUBSTRING of forbidden "unnamed source",
    and "cited dataset" of "no cited dataset"; the pack uses the specific
    "named on-the-record source" / "dataset cited and linked" so the forbidden flags still fire.
"""
from pathlib import Path

from verity import check, load_truth

PACKS = Path(__file__).resolve().parent.parent / "truths"


def _truth():
    return load_truth(PACKS / "journalism.yaml")


def test_journalism_pack_passes_honest_sourced_in_context_claim():
    """A named-source, in-context, grounded, disclosed report clears the bar (PASS)."""
    t = _truth()
    good = {
        "name": "city-budget-report",
        "text": ("according to a named on-the-record source and multiple independent sources, with "
                 "documents reviewed; the full quote in context and a verbatim transcript are linked. "
                 "The 12% figure is reported as a per-capita rate with the denominator reported and the "
                 "dataset cited and linked. The outlet is editorially independent with funding disclosed."),
    }
    res = check(good, t)
    assert res["verdict"] == "PASS", res


def test_journalism_pack_refuses_unsourced_single_anonymous():
    """A claim resting on a single anonymous / unnamed source with an unsourced assertion is
    fabrication-class -> REFUSE on the CRITICAL sourcing fact."""
    t = _truth()
    bad = {
        "name": "bombshell-report",
        "text": ("the report alleges, citing a single anonymous source and one unnamed source, that the "
                 "deal collapsed — an unsourced assertion with people familiar with the matter and a "
                 "person who declined to be named"),
    }
    res = check(bad, t)
    assert res["verdict"] == "REFUSE", res
    assert any(i["check"] == "sourcing_attribution" and i["severity"] == "CRITICAL" for i in res["issues"]), res


def test_journalism_pack_warns_cherry_picked_quote():
    """A quote stripped of context / cherry-picked misleads -> WARN on the HIGH context fact."""
    t = _truth()
    quote = {
        "name": "gotcha-clip",
        "text": ("the candidate's statement was a quote stripped of context — a cherry-picked quote "
                 "and an out-of-context excerpt from a doctored clip"),
    }
    res = check(quote, t)
    assert res["verdict"] == "WARN", res
    assert any(i["check"] == "quote_in_context" and i["severity"] == "HIGH" for i in res["issues"]), res


def test_journalism_pack_warns_statistic_with_no_denominator():
    """A statistic with no denominator / no cited dataset is unverifiable -> WARN on the HIGH grounding fact."""
    t = _truth()
    stat = {
        "name": "crime-surge",
        "text": ("crime is up 200%, a raw count with no base rate — a percentage with no sample size, "
                 "no denominator, and no cited dataset behind the figures"),
    }
    res = check(stat, t)
    assert res["verdict"] == "WARN", res
    assert any(i["check"] == "statistical_grounding" and i["severity"] == "HIGH" for i in res["issues"]), res


def test_journalism_pack_warns_undisclosed_coi_sponsored_as_news():
    """An undisclosed conflict of interest / sponsored-as-news is a trust breach -> WARN (MEDIUM)."""
    t = _truth()
    coi = {
        "name": "native-ad",
        "text": ("the glowing review was sponsored content presented as news — an advertorial unlabeled "
                 "with an undisclosed conflict of interest and undisclosed sponsorship"),
    }
    res = check(coi, t)
    assert res["verdict"] == "WARN", res
    assert any(i["check"] == "disclosure_coi" and i["severity"] == "MEDIUM" for i in res["issues"]), res


def test_journalism_pack_high_number_is_not_auto_suspected():
    """A high reported percentage is NOT an ML accuracy — suspicious_accuracy=1.0 and OOS/leakage are
    waived, so an honest grounded story with a 0.92 figure does NOT trip the auto-suspect rule."""
    t = _truth()
    high = {
        "name": "approval-rating", "accuracy": 0.92, "sample_size": 1500,
        "text": ("the 92% figure is reported with the denominator reported, sample size given, and the "
                 "dataset cited and linked, attributed to a named on-the-record source"),
    }
    res = check(high, t)
    assert res["verdict"] == "PASS", res
    assert not any(i["check"] == "suspicious_accuracy" for i in res["issues"]), res
    assert not any(i["check"] in ("out_of_sample", "leakage") for i in res["issues"]), res


def test_journalism_pack_no_canonical_is_a_substring_of_a_forbidden_term():
    """The SUBSTRING-TRAP rule, mechanically, for EVERY fact: a canonical term that is a substring of a
    forbidden term would always be present whenever that forbidden term is, silently suppressing the
    flag. Assert no canonical is a substring of any forbidden term across all four facts."""
    t = _truth()
    norm = lambda s: " ".join(s.lower().split())
    for fact in t["facts"]:
        for c in fact["canonical_terms"]:
            for f in fact["forbidden_terms"]:
                assert norm(c) not in norm(f), (
                    f"TRAP in fact {fact['id']!r}: canonical {c!r} is a substring of forbidden {f!r}")


def test_journalism_pack_substring_trap_is_defused_on_forbidden_only():
    """The defusal: a claim with ONLY forbidden sourcing terms and NO canonical phrasing anywhere must
    STILL REFUSE on the CRITICAL sourcing fact. A bare "named source" canonical would substring-match
    the forbidden "unnamed source" and suppress it — this proves the specific canonical does not."""
    t = _truth()
    trap = {
        "name": "anon-only",
        "text": "the story rests on an unnamed source and a single anonymous source; sources say it is true",
    }
    res = check(trap, t)
    assert res["verdict"] == "REFUSE", res
    assert any(i["check"] == "sourcing_attribution" for i in res["issues"]), res
