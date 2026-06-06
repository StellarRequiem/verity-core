"""GROUNDING — the 4th verify() dimension: a claim reconciled against its CITED sources.

Pure, deterministic unit tests (no I/O happens — sources are caller-supplied resolved
facts/text, exactly like truth). GROUNDING runs iff `sources` is a NON-EMPTY list. The
load-bearing invariants:
  * CONTRADICTION (a structured source asserting a differing value) → CRITICAL → REFUSE;
  * SUPPORT (any source backs the key) → grounded (clean);
  * SILENT (no source asserts the key) → MEDIUM "not supported by any cited source";
  * precedence CONTRADICT > SUPPORT > SILENT (sources that disagree don't safely ground);
  * a TEXT source can SUPPORT (its string appears) but NEVER contradict.
GROUNDING speaks the same ONE gate ladder and is flattened after consistency.
"""
from pathlib import Path

from verity.gate import load_truth
from verity.verify import _grounding, _verdict_of, verify

TRUTH = load_truth(Path(__file__).resolve().parent.parent / "verity" / "truth.yaml")

# A clean, honest baseline claim that PASSes the empirical gate on its own.
CLEAN = {"name": "y", "accuracy": 0.51, "sample_size": 300,
         "out_of_sample": True, "leakage_checked": True,
         "text": "daily directional signal: walk-forward holdout, out-of-sample, "
                 "no look-ahead, causal"}


# ── G1: presence/absence semantics — empty / None / no-sources omit the dimension ──
def test_grounding_absent_when_sources_empty_or_none():
    # truth-only → no sources arg → grounding not applicable (absent).
    assert "grounding" not in verify(CLEAN, truth=TRUTH)["dimensions"]
    # empty list is the EVIDENCE dim's domain (provenance-missing), not grounding's.
    assert "grounding" not in verify(CLEAN, sources=[], evidence={}, truth=TRUTH)["dimensions"]
    # None means no provenance claimed → absent.
    assert "grounding" not in verify(CLEAN, sources=None, truth=TRUTH)["dimensions"]


# ── G2: a fully-supported claim → the dimension exists and is clean (PASS) ──
def test_grounding_present_clean_when_all_supported():
    res = verify({"accuracy": 0.58}, sources=[{"accuracy": 0.58, "id": "recompute.csv"}],
                 truth=TRUTH)
    assert res["dimensions"]["grounding"] == {"verdict": "PASS", "issues": []}


# ── G3: a structured source asserting a differing number → CRITICAL → overall REFUSE ──
def test_grounding_contradiction_is_critical_refuse():
    res = verify({"accuracy": 0.91}, sources=[{"accuracy": 0.58, "id": "recompute.csv"}],
                 truth=TRUTH)
    iss = res["dimensions"]["grounding"]["issues"]
    crit = [i for i in iss if i["check"] == "grounding:accuracy"]
    assert crit and crit[0]["severity"] == "CRITICAL"
    assert "contradicts source recompute.csv" in crit[0]["detail"]
    assert res["verdict"] == "REFUSE"


# ── G4: numeric within the (reused evidence) tolerance → support, clean ──
def test_grounding_numeric_within_tolerance_supports():
    # 0.58 vs 0.5805 is < 1% → grounded, no issue (same bar as the evidence dim).
    assert _grounding({"accuracy": 0.58}, [{"accuracy": 0.5805}], {}) == []


# ── G5: a claim key no source mentions → MEDIUM unsupported → overall WARN ──
def test_grounding_unsupported_key_is_medium():
    res = verify({"accuracy": 0.58, "sharpe": 1.2}, sources=[{"accuracy": 0.58}], truth=TRUTH)
    iss = res["dimensions"]["grounding"]["issues"]
    # accuracy is grounded (no issue); sharpe is unsupported (MEDIUM).
    assert not any(i["check"] == "grounding:accuracy" for i in iss)
    unsup = [i for i in iss if i["check"] == "grounding:sharpe"]
    assert unsup and unsup[0]["severity"] == "MEDIUM"
    assert unsup[0]["detail"] == "claim sharpe not supported by any cited source"
    assert res["verdict"] == "WARN"


# ── G6: a TEXT source whose value-string appears → support; absent → unsupported ──
def test_grounding_text_source_supports_by_substring():
    src = ["walk-forward holdout, measured accuracy 0.58 out-of-sample"]
    assert _grounding({"accuracy": 0.58}, src, {}) == []
    # a string NOT containing 0.58 → MEDIUM unsupported.
    out = _grounding({"accuracy": 0.58}, ["accuracy was measured carefully"], {})
    assert out and out[0]["severity"] == "MEDIUM" and out[0]["check"] == "grounding:accuracy"


# ── G7: a TEXT source can NEVER contradict (absence is unsupported, not false) ──
def test_grounding_text_source_never_contradicts():
    out = _grounding({"accuracy": 0.58}, ["accuracy was 0.91"], {})
    # 0.58's string is absent → MEDIUM unsupported; text cannot drive a CRITICAL.
    assert out and out[0]["severity"] == "MEDIUM"
    assert not any(i["severity"] == "CRITICAL" for i in out)


# ── G8: bool branch first — a flip is a contradiction, not masked by True==1.0 ──
def test_grounding_bool_branch_first():
    out = _grounding({"out_of_sample": True}, [{"out_of_sample": False}], {})
    assert out and out[0]["check"] == "grounding:out_of_sample" and out[0]["severity"] == "CRITICAL"
    # an agreeing bool → clean.
    assert _grounding({"out_of_sample": True}, [{"out_of_sample": True}], {}) == []


# ── G9: strings compared normalized (case/whitespace insensitive) ──
def test_grounding_string_normalized():
    assert _grounding({"venue": "Coinbase"}, [{"venue": " coinbase "}], {}) == []
    out = _grounding({"venue": "Coinbase"}, [{"venue": "Kraken"}], {})
    assert out and out[0]["severity"] == "CRITICAL" and out[0]["check"] == "grounding:venue"


# ── G10: name/text are never demanded of the sources (excluded like the claim side) ──
def test_grounding_name_text_excluded():
    out = _grounding({"name": "x", "text": "y", "accuracy": 0.58}, [{"accuracy": 0.58}], {})
    assert out == []


# ── G11: CONTRADICTION beats SUPPORT — disagreeing sources are not safe grounding ──
def test_grounding_contradiction_beats_support():
    out = _grounding({"accuracy": 0.58}, [{"accuracy": 0.58}, {"accuracy": 0.91}], {})
    assert out and out[0]["severity"] == "CRITICAL" and out[0]["check"] == "grounding:accuracy"


# ── G12: the combined {id, facts, text} source shape — facts compared, sid in detail ──
def test_grounding_combined_shape():
    out = _grounding({"accuracy": 0.58},
                     [{"id": "r", "facts": {"accuracy": 0.91}, "text": "notes"}], {})
    assert out and out[0]["severity"] == "CRITICAL"
    assert "contradicts source r accuracy=0.91" in out[0]["detail"]


# ── G13: flattened after consistency; every grounding issue carries source=="grounding" ──
def test_grounding_flattened_after_consistency():
    res = verify(CLEAN, evidence={"accuracy": 0.51}, prior={"accuracy": 0.51},
                 sources=[{"sharpe": 9.9}], truth=TRUTH)
    expected = (res["dimensions"]["empirical"]["issues"]
                + res["dimensions"]["evidence"]["issues"]
                + res["dimensions"]["consistency"]["issues"]
                + res["dimensions"]["grounding"]["issues"])
    assert res["issues"] == expected
    assert all(i["source"] == "grounding" for i in res["dimensions"]["grounding"]["issues"])
    # and there IS at least one grounding issue here (sharpe unsupported) to make the check real.
    assert res["dimensions"]["grounding"]["issues"]


# ── G14: the per-dimension verdict matches its own issues (the one ladder) ──
def test_grounding_per_dimension_verdict_matches_own_issues():
    res = verify({"accuracy": 0.91}, sources=[{"accuracy": 0.58}], truth=TRUTH)
    gr = res["dimensions"]["grounding"]
    assert gr["verdict"] == _verdict_of(gr["issues"])


# ── G15: a non-list `sources` is inert (isinstance guard); evidence path unaffected ──
def test_grounding_non_list_sources_is_inert():
    res = verify(CLEAN, sources="recompute.csv", truth=TRUTH)
    assert "grounding" not in res["dimensions"]
    # the evidence path is untouched: supplying evidence + a bare-string sources still works,
    # and the empty-sources LOW flag is NOT spuriously triggered (the string is non-empty/non-list).
    res2 = verify(CLEAN, evidence={"accuracy": 0.51}, sources="recompute.csv", truth=TRUTH)
    assert res2["dimensions"]["evidence"] == {"verdict": "PASS", "issues": []}
    assert "grounding" not in res2["dimensions"]


# ══════════════════════════════════════════════════════════════════════════════
#  ADVERSARIAL — try to FOOL or CRASH grounding. Default: "the verifier is wrong".
# ══════════════════════════════════════════════════════════════════════════════

# ── A1: a POISONED source cannot weaponise garbage into a forced REFUSE ──────────
# A malicious/garbage source value (NaN/inf/set/None/list/unparseable-str) for a key the
# claim states as a finite NUMBER must NOT count as a contradiction — the comparison is
# incoherent. Otherwise any honest numeric claim could be forced to REFUSE by injecting
# unreadable junk for that key (a denial-of-trust false-contradiction). It degrades to the
# MEDIUM "unsupported" (silent), never a garbage-driven CRITICAL.
def test_grounding_poisoned_garbage_source_does_not_force_refuse():
    for poison in (float("nan"), float("inf"), {1, 2, 3}, None, "not-a-number", [1, 2]):
        out = _grounding({"accuracy": 0.58}, [{"accuracy": poison}], {})
        assert all(i["severity"] != "CRITICAL" for i in out), f"poison {poison!r} forced CRITICAL"
        assert out and out[0]["check"] == "grounding:accuracy" and out[0]["severity"] == "MEDIUM"
    # end-to-end: the overall grounding dimension is not REFUSE on the poison alone.
    res = verify({"accuracy": 0.58}, sources=[{"accuracy": float("nan"), "id": "poison"}], truth=TRUTH)
    assert res["dimensions"]["grounding"]["verdict"] != "REFUSE"


# ── A2: poison cannot HIDE a real contradiction, nor SUPPRESS a real support ─────
def test_grounding_poison_neither_hides_contradiction_nor_blocks_support():
    # a genuine contradictor still fires CRITICAL even with a garbage source alongside it.
    out = _grounding({"accuracy": 0.91},
                     [{"accuracy": float("nan")}, {"accuracy": 0.58}], {})
    assert any(i["severity"] == "CRITICAL" and i["check"] == "grounding:accuracy" for i in out)
    # a real supporting source still grounds the key — the silent poison does not block it.
    assert _grounding({"accuracy": 0.58},
                      [{"accuracy": 0.58}, {"accuracy": float("nan")}], {}) == []


# ── A3: a concrete differing STRUCTURED value (neither side numeric) still contradicts ──
# The poison guard must NOT over-fire: two genuinely-different non-numeric structured values
# (lists/dicts) are a real disagreement, preserved as CRITICAL (the documented divergence).
def test_grounding_nonnumeric_structured_disagreement_still_contradicts():
    out = _grounding({"window": [1, 2]}, [{"window": [3, 4]}], {})
    assert out and out[0]["severity"] == "CRITICAL" and out[0]["check"] == "grounding:window"
    assert _grounding({"window": [1, 2]}, [{"window": [1, 2]}], {}) == []   # equal → support


# ── A4: malicious / non-dict / non-serialisable sources must DEGRADE, never crash ──
def test_grounding_garbage_sources_never_crash():
    garbage = [None, 42, 3.14, [1, 2, 3], object(), b"bytes",
               {"facts": 123}, {"facts": None}, [[1], [2]],
               {"facts": {"accuracy": {1, 2}}}]    # set-valued source fact
    for g in garbage:
        res = verify({"accuracy": 0.58}, sources=[g], truth=TRUTH)   # must not raise
        assert res["verdict"] in {"PASS", "WARN", "REFUSE"}
        assert "grounding" in res["dimensions"]
    # a whole list of pure junk: still no crash, just an unsupported (MEDIUM) claim key.
    res = verify({"accuracy": 0.58}, sources=[None, 1, "x", object()], truth=TRUTH)
    assert res["verdict"] in {"WARN", "REFUSE"}
    assert any(i["check"] == "grounding:accuracy" for i in res["dimensions"]["grounding"]["issues"])


# ── A5: OMISSION-EVASION (the known gap) — a claim that omits the disputed fact ──
# A source asserts `accuracy`, but the claim simply has NO accuracy key. Grounding only
# iterates the claim's OWN disclosed keys, so the omission is silently un-checked — exactly
# the documented limitation. The contract here: it must DEGRADE gracefully (no crash, the
# disputed-but-omitted fact is just never grounded), NOT raise and NOT spuriously contradict.
def test_grounding_omission_evasion_degrades_does_not_crash():
    # claim omits `accuracy` entirely; the source's accuracy is therefore irrelevant to grounding.
    res = verify({"sharpe": 1.2}, sources=[{"accuracy": 0.58}], truth=TRUTH)
    gr = res["dimensions"]["grounding"]["issues"]
    # only the claim's OWN key (sharpe, unsupported) is graded; `accuracy` is not invented.
    assert [i["check"] for i in gr] == ["grounding:sharpe"]
    assert not any("accuracy" in i["check"] for i in gr)
    # and a claim that drops a key a source disputes never raises (pure-Python, deterministic).
    assert verify({}, sources=[{"accuracy": 0.91}], truth=TRUTH)["verdict"] in {"PASS", "WARN", "REFUSE"}


# ── A6: a source cannot LAUNDER a contradicting number behind supporting prose ──
# When a combined source carries BOTH a structured fact AND text, the STRUCTURED fact wins
# (checked first). So prose that merely mentions the claimed value cannot mask a structured
# counter-assertion — the contradiction still fires.
def test_grounding_text_cannot_launder_structured_contradiction():
    out = _grounding({"accuracy": 0.58},
                     [{"facts": {"accuracy": 0.91}, "text": "accuracy 0.58 confirmed", "id": "s"}], {})
    assert out and out[0]["severity"] == "CRITICAL"
    assert "accuracy=0.91" in out[0]["detail"]
