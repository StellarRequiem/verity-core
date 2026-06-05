"""verify() — the unified multi-dimension entrypoint.

These are pure, deterministic unit tests: no I/O is mocked because none happens.
verify() takes a *resolved* truth dict, so each dimension is exercised in isolation.
The load-bearing invariant: every dimension speaks the ONE gate ladder
(REFUSE ≥ CRITICAL / WARN any / PASS clean), and the overall verdict is the worst
across all RUN dimensions.
"""
from pathlib import Path

from verity import verify as pkg_verify  # the package re-export must work
from verity.gate import check, load_truth
from verity.verify import _consistency, _evidence, _verdict_of, verify

TRUTH = load_truth(Path(__file__).resolve().parent.parent / "verity" / "truth.yaml")

# A clean, honest baseline claim that PASSes the empirical gate on its own.
CLEAN = {"name": "y", "accuracy": 0.51, "sample_size": 300,
         "out_of_sample": True, "leakage_checked": True,
         "text": "daily directional signal: walk-forward holdout, out-of-sample, "
                 "no look-ahead, causal"}


# ── orchestration: empirical-only path is exactly gate.check ──────────────────
def test_export_is_wired():
    assert pkg_verify is verify


def test_empirical_only_matches_gate_check():
    res = verify(CLEAN, truth=TRUTH)
    gate_res = check(CLEAN, TRUTH)
    assert res["dimensions"]["empirical"] == gate_res
    # with no evidence/prior, only the empirical dimension is present...
    assert set(res["dimensions"]) == {"empirical"}
    # ...and the flattened issues are exactly the empirical issues, verdict matches.
    assert res["issues"] == gate_res["issues"]
    assert res["verdict"] == gate_res["verdict"]


def test_empirical_refusal_propagates_to_overall():
    fake = {"name": "x", "accuracy": 0.72, "sample_size": 18,
            "out_of_sample": False, "leakage_checked": False,
            "text": "72% win rate, money printer"}
    res = verify(fake, truth=TRUTH)
    assert res["verdict"] == "REFUSE"
    assert res["dimensions"]["empirical"]["verdict"] == "REFUSE"


def test_truth_defaults_to_packaged_when_none():
    # No truth passed → verify loads the packaged default (no exception, real verdict).
    res = verify(CLEAN)
    assert res["verdict"] in {"PASS", "WARN", "REFUSE"}
    assert "empirical" in res["dimensions"]


# ── dimension presence/absence semantics ──────────────────────────────────────
def test_absent_inputs_omit_their_dimension():
    res = verify(CLEAN, truth=TRUTH)
    assert "evidence" not in res["dimensions"]
    assert "consistency" not in res["dimensions"]


def test_present_but_clean_evidence_dimension_is_present():
    # evidence supplied AND agreeing → the dimension exists and is clean (PASS),
    # which is distinguishable from "not applicable" (absent key).
    res = verify(CLEAN, evidence={"accuracy": 0.51, "sample_size": 300}, truth=TRUTH)
    assert "evidence" in res["dimensions"]
    assert res["dimensions"]["evidence"] == {"verdict": "PASS", "issues": []}


def test_empty_evidence_dict_is_still_supplied():
    # {} is "supplied, nothing shared to reconcile" — dimension present, clean.
    res = verify(CLEAN, evidence={}, truth=TRUTH)
    assert res["dimensions"]["evidence"] == {"verdict": "PASS", "issues": []}


# ── EVIDENCE dimension ────────────────────────────────────────────────────────
def test_evidence_number_mismatch_is_critical_refuse():
    res = verify(CLEAN, evidence={"accuracy": 0.93}, truth=TRUTH)
    assert res["verdict"] == "REFUSE"
    iss = res["dimensions"]["evidence"]["issues"]
    assert any(i["check"] == "evidence:accuracy" and i["severity"] == "CRITICAL" for i in iss)


def test_evidence_numbers_within_tolerance_agree():
    # default rel tol 1% — 0.51 vs 0.5105 is < 1% → no issue.
    assert _evidence({"accuracy": 0.51}, {"accuracy": 0.5105}, None, {}) == []
    # just outside tolerance → CRITICAL.
    out = _evidence({"accuracy": 0.51}, {"accuracy": 0.60}, None, {})
    assert out and out[0]["severity"] == "CRITICAL"


def test_evidence_bool_flip_is_high_not_critical():
    # bool must NOT be swallowed by the numeric branch (True == 1.0). A flip is HIGH.
    res = verify(CLEAN, evidence={"out_of_sample": False}, truth=TRUTH)
    iss = res["dimensions"]["evidence"]["issues"]
    flip = [i for i in iss if i["check"] == "evidence:out_of_sample"]
    assert flip and flip[0]["severity"] == "HIGH"
    assert res["verdict"] == "WARN"   # HIGH, not CRITICAL → WARN overall
    # an agreeing bool produces no issue
    assert _evidence({"out_of_sample": True}, {"out_of_sample": True}, None, {}) == []


def test_evidence_string_mismatch_is_medium_normalized():
    # normalized equality only — case/whitespace differences are NOT a mismatch.
    assert _evidence({"venue": "Coinbase"}, {"venue": "  coinbase "}, None, {}) == []
    out = _evidence({"venue": "Coinbase"}, {"venue": "Kraken"}, None, {})
    assert out and out[0]["severity"] == "MEDIUM" and out[0]["check"] == "evidence:venue"


def test_evidence_mixed_type_is_evidence_type_medium():
    out = _evidence({"k": [1, 2]}, {"k": "1,2"}, None, {})
    assert out and out[0]["check"] == "evidence_type" and out[0]["severity"] == "MEDIUM"


def test_evidence_only_shared_keys_participate():
    # claim-only and evidence-only keys are silent (can only reconcile shared fields).
    assert _evidence({"a": 1, "only_claim": 9}, {"a": 1, "only_ev": 9}, None, {}) == []


def test_text_and_name_are_excluded_from_reconciliation():
    out = _evidence({"name": "alpha", "text": "x"}, {"name": "beta", "text": "y"}, None, {})
    assert out == []


def test_sources_empty_emits_low_sources_missing():
    out = _evidence({"accuracy": 0.51}, {"accuracy": 0.51}, [], {})
    assert out == [{"source": "evidence", "check": "sources_missing", "severity": "LOW",
                    "detail": "evidence supplied with an empty sources list — provenance not cited"}]
    # a non-empty / None sources list does NOT add the issue
    assert _evidence({"accuracy": 0.51}, {"accuracy": 0.51}, ["paper.pdf"], {}) == []
    assert _evidence({"accuracy": 0.51}, {"accuracy": 0.51}, None, {}) == []


# ── CONSISTENCY dimension ─────────────────────────────────────────────────────
def test_consistency_revised_number_is_high_warn():
    res = verify({"name": "m", "win_rate": 0.58}, prior={"name": "m", "win_rate": 0.52}, truth=TRUTH)
    assert "consistency" in res["dimensions"]
    iss = res["dimensions"]["consistency"]["issues"]
    assert any(i["check"] == "consistency:win_rate" and i["severity"] == "HIGH" for i in iss)
    assert res["verdict"] == "WARN"


def test_consistency_sign_flip_on_edge_is_critical_refuse():
    res = verify({"edge": 0.03}, prior={"edge": -0.03}, truth=TRUTH)
    iss = res["dimensions"]["consistency"]["issues"]
    assert any(i["check"] == "consistency:sign_flip" and i["severity"] == "CRITICAL" for i in iss)
    assert res["verdict"] == "REFUSE"


def test_consistency_sign_flip_only_on_signed_effect_fields():
    # a non-effect field that merely changes sign is HIGH (revision), not sign_flip.
    out = _consistency({"balance": 5.0}, {"balance": -5.0}, {})
    assert out and out[0]["check"] == "consistency:balance" and out[0]["severity"] == "HIGH"


def test_consistency_unchanged_restatement_is_clean():
    same = {"name": "m", "win_rate": 0.52, "edge": 0.01}
    res = verify(same, prior=dict(same), truth=TRUTH)
    assert res["dimensions"]["consistency"] == {"verdict": "PASS", "issues": []}


def test_consistency_bool_change_is_high():
    out = _consistency({"out_of_sample": True}, {"out_of_sample": False}, {})
    assert out and out[0]["check"] == "consistency:out_of_sample" and out[0]["severity"] == "HIGH"


def test_consistency_string_change_is_medium():
    out = _consistency({"regime": "bull"}, {"regime": "bear"}, {})
    assert out and out[0]["severity"] == "MEDIUM"
    assert _consistency({"regime": "Bull"}, {"regime": " bull "}, {}) == []


def test_consistency_ignores_bookkeeping_keys():
    # timestamp/ts/run_id/seq are expected to change — never a contradiction.
    for k in ("timestamp", "ts", "run_id", "seq"):
        assert _consistency({k: "b"}, {k: "a"}, {}) == []


def test_consistency_zero_is_not_a_sign_flip():
    # 0 -> +x is a revision, not a sign flip (0 has no sign to flip).
    out = _consistency({"edge": 0.05}, {"edge": 0.0}, {})
    assert out and out[0]["check"] == "consistency:edge" and out[0]["severity"] == "HIGH"


# ── the merged verdict + provenance ───────────────────────────────────────────
def test_flattened_issues_carry_their_source():
    res = verify(CLEAN, evidence={"accuracy": 0.93}, prior={"accuracy": 0.51},
                 truth=TRUTH)
    sources = {i["source"] for i in res["issues"]}
    assert sources <= {"structural", "rigor", "ground_truth", "evidence", "consistency"}
    # the flattened list is the concatenation of each run dimension's issues, in order.
    expected = (res["dimensions"]["empirical"]["issues"]
                + res["dimensions"]["evidence"]["issues"]
                + res["dimensions"]["consistency"]["issues"])
    assert res["issues"] == expected


def test_overall_is_worst_across_all_run_dimensions():
    # empirical clean + evidence CRITICAL → overall REFUSE (worst wins).
    res = verify(CLEAN, evidence={"accuracy": 0.93}, truth=TRUTH)
    assert res["dimensions"]["empirical"]["verdict"] == "PASS"
    assert res["verdict"] == "REFUSE"


def test_verdict_of_uses_one_ladder():
    assert _verdict_of([]) == "PASS"
    assert _verdict_of([{"severity": "LOW"}]) == "WARN"
    assert _verdict_of([{"severity": "MEDIUM"}, {"severity": "HIGH"}]) == "WARN"
    assert _verdict_of([{"severity": "HIGH"}, {"severity": "CRITICAL"}]) == "REFUSE"
    # an unknown severity is treated as 0 (does not crash, ranks lowest).
    assert _verdict_of([{"severity": "BOGUS"}]) == "WARN"


def test_per_dimension_verdict_matches_its_own_issues():
    res = verify(CLEAN, evidence={"out_of_sample": False}, truth=TRUTH)
    ev = res["dimensions"]["evidence"]
    assert ev["verdict"] == _verdict_of(ev["issues"])
