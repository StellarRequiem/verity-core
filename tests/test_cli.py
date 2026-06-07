"""The verity CLI gates result-claims and exits on the worst verdict (0 PASS · 1 WARN · 2 REFUSE)."""
import json
from pathlib import Path

import pytest

from verity.cli import _load_json_arg, _load_sources, main

REPO_ROOT = Path(__file__).resolve().parent.parent
BENCHMARK = REPO_ROOT / "eval" / "benchmark.jsonl"


def test_check_single_pass_and_refuse(capsys):
    assert main(["check", "--claim",
                 '{"accuracy":0.51,"sample_size":300,"out_of_sample":true,"leakage_checked":true}']) == 0
    assert main(["check", "--claim",
                 '{"accuracy":0.72,"sample_size":18,"out_of_sample":false,"leakage_checked":false}']) == 2
    assert "VERIFIED" in capsys.readouterr().out


def test_check_accepts_plain_text_claim(capsys):
    rc = main(["check", "--claim", "some words with no structured fields"])
    assert isinstance(rc, int)                       # runs; a bare claim warns (no oos/leakage affirmed)
    assert "Verdict:" in capsys.readouterr().out


def test_check_batch_rolls_up_to_worst(tmp_path, capsys):
    backlog = tmp_path / "claims.jsonl"
    backlog.write_text("\n".join(json.dumps(c) for c in [
        {"accuracy": 0.51, "sample_size": 300, "out_of_sample": True, "leakage_checked": True},   # PASS
        {"accuracy": 0.55, "sample_size": 40, "out_of_sample": True, "leakage_checked": True},     # WARN (thin)
        {"accuracy": 0.50, "sample_size": 10, "out_of_sample": True, "leakage_checked": True},     # REFUSE (noise)
    ]) + "\n", encoding="utf-8")
    rc = main(["check-batch", str(backlog)])
    out = capsys.readouterr().out
    assert "3 claim(s): 1 PASS · 1 WARN · 1 REFUSE" in out
    assert rc == 2                                   # worst verdict fails the gate


def test_check_batch_reports_all_failing_reasons_not_just_the_first(tmp_path, capsys):
    """A claim that violates MULTIPLE rules must surface ALL of them, not short-circuit on the first.

    verity-demo PR #1's claim: a tiny sample AND no lift over the base rate AND no holdout AND no
    leakage check. Against the ml-classification pack (hard_min_sample 100, min_lift 0.02) the worst
    reason is the noise floor, but the claim earns several more — the roll-up must list them all.
    """
    truth = REPO_ROOT / "truths" / "ml-classification.yaml"
    backlog = tmp_path / "multi.jsonl"
    backlog.write_text(json.dumps(
        {"name": "fraud-detector v3 (offline)", "accuracy": 0.985, "sample_size": 90,
         "out_of_sample": False, "base_rate": 0.98, "text": "..."}) + "\n", encoding="utf-8")
    rc = main(["check-batch", str(backlog), "--truth", str(truth)])
    out = capsys.readouterr().out
    assert rc == 2                                              # verdict + exit unchanged: REFUSE
    assert "1 PASS · 0 WARN · 1 REFUSE" not in out             # (sanity: it's the 1-REFUSE roll-up)
    assert "0 PASS · 0 WARN · 1 REFUSE" in out
    # all three advertised rules surface — not only the first (the noise floor)
    assert "sample 90 < hard floor 100 — noise" in out         # rule 1: sample-size floor
    assert "base rate 0.98" in out and "no real lift" in out   # rule 2: no lift over base rate
    assert "not validated out-of-sample" in out                # rule 3: out-of-sample / holdout
    assert "leakage not affirmatively checked" in out          # (and leakage, also unchecked)
    # the primary line is unchanged in shape; the extras hang off it as continuation lines
    assert "[REFUSE] fraud-detector v3 (offline)  —  sample 90 < hard floor 100 — noise" in out
    assert out.count("·") >= 3                                  # >=3 extra-reason continuation lines


def test_check_batch_clean_backlog_passes(tmp_path):
    backlog = tmp_path / "clean.jsonl"
    backlog.write_text(
        json.dumps({"accuracy": 0.51, "sample_size": 300, "out_of_sample": True, "leakage_checked": True}) + "\n",
        encoding="utf-8")
    assert main(["check-batch", str(backlog)]) == 0


def test_check_batch_flags_a_disclosed_but_insignificant_result(tmp_path, capsys):
    # the rigor checks fire through the CLI: a disclosed z below 2 is flagged
    backlog = tmp_path / "rigor.jsonl"
    backlog.write_text(json.dumps(
        {"name": "best-of-4", "win_rate": 0.5252, "sample_size": 436, "out_of_sample": True,
         "leakage_checked": True, "z": 1.05, "n_comparisons": 4}) + "\n", encoding="utf-8")
    rc = main(["check-batch", str(backlog)])
    assert rc == 1                                   # WARN — not significant + best-of-N selection


# ── `verity verify` — the multi-dimension agent entrypoint ────────────────────
def test_verify_honest_claim_passes(capsys):
    rc = main(["verify", "--claim",
               '{"name":"honest","accuracy":0.51,"sample_size":300,"out_of_sample":true,'
               '"leakage_checked":true,"text":"walk-forward out-of-sample no look-ahead causal"}'])
    out = capsys.readouterr().out
    assert "Dimensions:" in out and "Verdict: PASS" in out
    assert rc == 0


def test_verify_evidence_mismatch_refuses_with_exit_2(capsys):
    # claims 72% but the recomputed evidence says 58% → fabrication-class CRITICAL → REFUSE
    rc = main(["verify",
               "--claim", '{"name":"inflated","accuracy":0.72,"sample_size":400,'
                          '"out_of_sample":true,"leakage_checked":true}',
               "--evidence", '{"accuracy":0.58}',
               "--sources", "recomputed.csv"])
    out = capsys.readouterr().out
    assert "evidence" in out and "REFUSE" in out
    assert rc == 2


def test_verify_prior_sign_flip_refuses(capsys):
    rc = main(["verify",
               "--claim", '{"name":"edge","edge":0.04,"sample_size":400,'
                          '"out_of_sample":true,"leakage_checked":true}',
               "--prior", '{"name":"edge","edge":-0.04}'])
    assert rc == 2
    assert "sign_flip" in capsys.readouterr().out


def test_verify_reads_args_from_files(tmp_path, capsys):
    claim = tmp_path / "claim.json"
    claim.write_text(json.dumps({"accuracy": 0.55, "sample_size": 400,
                                 "out_of_sample": True, "leakage_checked": True}), encoding="utf-8")
    ev = tmp_path / "ev.json"
    ev.write_text(json.dumps({"accuracy": 0.55}), encoding="utf-8")
    rc = main(["verify", "--claim-file", str(claim), "--evidence", f"@{ev}"])
    assert rc == 0                                   # agreeing evidence, clean


def test_verify_malformed_json_arg_errors_loudly():
    with pytest.raises(ValueError):
        main(["verify", "--claim", '{"accuracy":0.5}', "--evidence", "{not json}"])


def test_load_json_arg_inline_and_file(tmp_path):
    assert _load_json_arg('{"a":1}') == {"a": 1}
    assert _load_json_arg("[1,2,3]") == [1, 2, 3]
    assert _load_json_arg(None) is None
    f = tmp_path / "x.json"
    f.write_text('{"k":"v"}', encoding="utf-8")
    assert _load_json_arg(f"@{f}") == {"k": "v"}


def test_load_sources_array_or_comma():
    assert _load_sources("a,b, c") == ["a", "b", "c"]
    assert _load_sources('["x","y"]') == ["x", "y"]
    assert _load_sources(None) is None
    assert _load_sources("") == []


# ── `verity eval` — the regression harness, behind the CLI ────────────────────
def test_eval_subcommand_runs_shipped_benchmark(capsys):
    rc = main(["eval"])
    out = capsys.readouterr().out
    assert "CIRCULAR benchmark" in out                # honesty banner ships
    assert "TOTAL" in out
    assert rc == 0                                     # shipped set is fully consistent


def test_eval_subcommand_accepts_a_path(capsys):
    rc = main(["eval", str(BENCHMARK)])
    assert rc == 0
    assert "not an external benchmark" in capsys.readouterr().out
