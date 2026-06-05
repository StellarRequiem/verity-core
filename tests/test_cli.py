"""The verity CLI gates result-claims and exits on the worst verdict (0 PASS · 1 WARN · 2 REFUSE)."""
import json

from verity.cli import main


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
