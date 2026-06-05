"""Tests for the eval harness (verity.eval) and the shipped benchmark set.

These are deliberately robust to the parallel build of ``verity.verify``: the
runner SKIPS evidence/consistency cases when verify is unavailable, so the
shipped-benchmark consistency assertion (``_exit == 0``) holds whether or not
verify has landed. The runner mechanics are tested against ``gate.check``
directly (always available), and the fail-path uses an empirical case (no
verify needed) so it proves the harness can FAIL regardless.
"""
from __future__ import annotations

import json
from pathlib import Path

import pytest

from verity import eval as ev

REPO_ROOT = Path(__file__).resolve().parent.parent
BENCHMARK = REPO_ROOT / "eval" / "benchmark.jsonl"

_REQUIRED_KEYS = {"id", "dimension", "failure_mode", "verdict", "label_source",
                  "truth_pack", "claim", "expect_checks"}
_VALID_VERDICTS = {"REFUSE", "WARN", "PASS"}
_VALID_DIMENSIONS = {"empirical", "rigor", "evidence", "consistency"}
_VALID_LABEL_SOURCES = {"definitional", "statistical", "real-incident"}


# ── the benchmark file itself: parses, and every line is well-formed ──────────
def test_benchmark_file_exists():
    assert BENCHMARK.exists(), f"missing benchmark at {BENCHMARK}"


def test_every_line_is_valid_json():
    """Raw parse — every non-blank line is a JSON object (catches trailing-comma / encoding rot)."""
    n = 0
    for lineno, raw in enumerate(BENCHMARK.read_text(encoding="utf-8").splitlines(), 1):
        line = raw.strip()
        if not line:
            continue
        obj = json.loads(line)          # raises with the offending content if malformed
        assert isinstance(obj, dict), f"line {lineno} is not a JSON object"
        n += 1
    assert n >= 1


def test_load_cases_skips_metadata_and_returns_cases():
    cases = ev.load_cases(BENCHMARK)
    # the honesty-header line (id starts with '_') must be filtered out
    assert all(not str(c["id"]).startswith("_") for c in cases)
    # spec floor: at least 18 real cases, balanced enough to have negative controls
    assert len(cases) >= 18


def test_load_cases_rejects_bad_json(tmp_path):
    bad = tmp_path / "bad.jsonl"
    bad.write_text('{"id":"ok","verdict":"PASS","claim":{}}\nnot json\n', encoding="utf-8")
    with pytest.raises(ValueError):
        ev.load_cases(bad)


# ── label hygiene: every case carries the required, valid metadata ────────────
def test_labels_parse_and_are_valid():
    cases = ev.load_cases(BENCHMARK)
    ids = set()
    for c in cases:
        missing = _REQUIRED_KEYS - set(c)
        assert not missing, f"case {c.get('id')!r} missing keys {missing}"
        assert c["verdict"] in _VALID_VERDICTS, f"{c['id']}: bad verdict {c['verdict']!r}"
        assert c["dimension"] in _VALID_DIMENSIONS, f"{c['id']}: bad dimension {c['dimension']!r}"
        assert c["label_source"] in _VALID_LABEL_SOURCES, \
            f"{c['id']}: bad label_source {c['label_source']!r}"
        assert isinstance(c["claim"], dict) and c["claim"], f"{c['id']}: empty claim"
        assert isinstance(c["expect_checks"], list), f"{c['id']}: expect_checks not a list"
        assert c["id"] not in ids, f"duplicate id {c['id']!r}"
        ids.add(c["id"])


def test_real_incident_cases_are_cited():
    """A 'real-incident' label MUST carry a note explaining which logged claim it mirrors."""
    for c in ev.load_cases(BENCHMARK):
        if c["label_source"] == "real-incident":
            assert c.get("note", "").strip(), f"{c['id']}: real-incident with no citation note"


def test_has_negative_controls_for_false_positive_rate():
    """FP-rate needs a real denominator: >=4 PASS cases, spread across dimensions."""
    cases = ev.load_cases(BENCHMARK)
    pass_cases = [c for c in cases if c["verdict"] == "PASS"]
    assert len(pass_cases) >= 4
    # and at least one PASS control whose expect_checks is empty (truly clean)
    assert any(c["expect_checks"] == [] for c in pass_cases)


def test_failure_cases_name_a_check_to_assert():
    """Every non-PASS case must assert at least one check id (proves the RIGHT rule fired)."""
    for c in ev.load_cases(BENCHMARK):
        if c["verdict"] != "PASS":
            assert c["expect_checks"], f"{c['id']}: a failure case with no expect_checks"


# ── the runner: aggregates per dimension, with rates and a check-fired count ──
def test_run_returns_per_dimension_shape():
    res = ev.run(BENCHMARK)
    for dim in ("empirical", "rigor"):       # always-runnable dimensions
        assert dim in res
        d = res[dim]
        for k in ("n", "catch_rate", "false_positive_rate", "checks_fired_correctly"):
            assert k in d, f"{dim} missing aggregate {k}"
    assert "_totals" in res and "_mismatches" in res and "_exit" in res
    assert res["_totals"]["n"] == len(ev.load_cases(BENCHMARK))


def test_shipped_benchmark_is_fully_consistent():
    """The SHIPPED set scores clean: exit 0, no mismatches.

    Robust to the verify build: evidence/consistency cases are skipped (not failed)
    when verify is unavailable, so _exit==0 holds in both worlds. When verify IS
    present, nothing is skipped and all cases score.
    """
    res = ev.run(BENCHMARK)
    assert res["_mismatches"] == [], f"unexpected mismatches: {res['_mismatches']}"
    assert res["_exit"] == 0
    # every SCORED failure case is caught and every clean case is left alone
    for dim, d in res.items():
        if dim.startswith("_"):
            continue
        if d["catch_rate"] is not None:
            assert d["catch_rate"] == 1.0, f"{dim}: catch_rate {d['catch_rate']} < 1.0"
        if d["false_positive_rate"] is not None:
            assert d["false_positive_rate"] == 0.0, \
                f"{dim}: false_positive_rate {d['false_positive_rate']} > 0"


def test_empirical_and_rigor_always_scored_not_skipped():
    """These dimensions never need verify, so they must score regardless of its presence."""
    res = ev.run(BENCHMARK)
    assert res["empirical"]["skipped"] == 0
    assert res["rigor"]["skipped"] == 0


def test_expect_checks_actually_fire_for_scored_cases():
    """For every scored case, each id in expect_checks appears in the gate's issues."""
    res = ev.run(BENCHMARK)
    for c in res["_cases"]:
        if c["skipped"]:
            continue
        assert c["checks_fired"], f"{c['id']}: missing checks {c['missing_checks']} (fired {c['fired']})"


# ── the harness can FAIL: a mislabelled case is reported + nonzero exit ───────
def test_harness_detects_a_mislabelled_case(tmp_path):
    """A deliberately wrong label must produce a mismatch and a nonzero exit —
    proves the regression can actually fail (uses an empirical case: no verify needed)."""
    case = {
        "id": "deliberately-wrong", "dimension": "empirical",
        "failure_mode": "tiny-sample noise", "verdict": "PASS",   # WRONG: this is a REFUSE
        "label_source": "definitional", "truth_pack": None,
        "claim": {"name": "noise", "accuracy": 0.5, "sample_size": 8,
                  "out_of_sample": True, "leakage_checked": True},
        "evidence": None, "prior": None, "expect_checks": ["sample_size"],
    }
    f = tmp_path / "mislabelled.jsonl"
    f.write_text(json.dumps(case) + "\n", encoding="utf-8")
    res = ev.run(f)
    assert res["_exit"] == 1
    assert any(m["id"] == "deliberately-wrong" for m in res["_mismatches"])
    # labelled PASS but the gate flagged it -> counts as a false positive (clean case, flagged)
    assert res["empirical"]["false_positive_rate"] == 1.0


def test_harness_detects_a_missing_expected_check(tmp_path):
    """Right verdict but the asserted check never fires -> still a mismatch (the RIGHT rule must fire)."""
    case = {
        "id": "right-verdict-wrong-check", "dimension": "empirical",
        "failure_mode": "tiny-sample noise", "verdict": "REFUSE",
        "label_source": "definitional", "truth_pack": None,
        "claim": {"name": "noise", "accuracy": 0.5, "sample_size": 8,
                  "out_of_sample": True, "leakage_checked": True},
        "evidence": None, "prior": None,
        "expect_checks": ["no_look_ahead"],          # wrong: this REFUSE is by sample_size
    }
    f = tmp_path / "wrongcheck.jsonl"
    f.write_text(json.dumps(case) + "\n", encoding="utf-8")
    res = ev.run(f)
    assert res["_exit"] == 1
    m = next(m for m in res["_mismatches"] if m["id"] == "right-verdict-wrong-check")
    assert m["match"] is True                        # verdict matched
    assert m["checks_fired"] is False                # but the asserted check did not fire


def test_main_prints_banner_and_returns_exit_code(capsys):
    rc = ev.main([str(BENCHMARK)])
    out = capsys.readouterr().out
    assert "CIRCULAR benchmark" in out               # the honesty framing ships in the output
    assert "not an external benchmark" in out
    assert rc == 0


def test_named_truth_pack_resolves(tmp_path):
    """A bare pack name (e.g. 'trading.yaml') resolves against truths/ — the real-incident
    cases rely on this."""
    cases = [c for c in ev.load_cases(BENCHMARK) if c.get("truth_pack")]
    assert cases, "expected at least one case pinned to a named truth pack"
    res = ev.run(BENCHMARK)
    # those cases scored (not errored) — covered by overall consistency, asserted explicitly here
    scored_ids = {c["id"] for c in res["_cases"] if not c["skipped"]}
    for c in cases:
        if c["dimension"] not in ev._VERIFY_DIMENSIONS:
            assert c["id"] in scored_ids
