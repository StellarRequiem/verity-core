"""The EXTERNAL benchmark (non-circular): does the gate flag real replication failures more
than survivors? Labels come from independent replications, not from the gate's rules."""
from verity import external_eval
from verity.gate import check


def test_external_eval_significant_on_the_full_corpus():
    r = external_eval.run()
    assert r["n"] == 1772 and r["n_failed"] == 787 and r["n_replicated"] == 985
    assert r["catch"] > r["false_alarm"] and r["odds_ratio"] > 1.0   # failures flagged more
    assert r["significant"] and r["p_value"] < 0.05                  # confirmed at proper power
    assert r["separation"] < 0.40                                    # significant != large — modest


def test_external_eval_cli_reports_significant(capsys):
    rc = external_eval.main([])
    out = capsys.readouterr().out
    assert "external, NOT circular" in out          # honesty banner ships
    assert "SIGNIFICANT" in out and "— significant." in out          # confirmed signal
    assert rc == 0


def test_score_subset_is_the_underpowered_arc():
    """The 132-case SCORE subset shows the same direction but is NOT significant — the honest arc
    that motivated getting the full corpus. (verity flagged its own under-powered claim here.)"""
    from pathlib import Path
    sub = Path(external_eval.__file__).resolve().parent.parent / "eval" / "external" / "score-replication.jsonl"
    r = external_eval.run(sub)
    assert r["n"] == 132 and r["catch"] > r["false_alarm"]   # same direction
    assert not r["significant"]                               # but under-powered at n=132


def test_require_leakage_check_is_config_gated():
    c = {"accuracy": 0.55, "sample_size": 500, "out_of_sample": True}   # no leakage_checked field
    assert any(i["check"] == "leakage" for i in check(c, {"thresholds": {}, "facts": []})["issues"])
    off = check(c, {"thresholds": {"require_leakage_check": False}, "facts": []})
    assert not any(i["check"] == "leakage" for i in off["issues"])


def test_marginal_signal_is_robust_not_a_lucky_split():
    """The 2.14x improvement's mechanism — strong (p<=.01) replicates more than marginal
    (.01<p<=.05) — must hold across folds, not just one split (eval/external/robustness.py)."""
    import importlib.util
    from pathlib import Path
    rp = Path(__file__).resolve().parent.parent / "eval" / "external" / "robustness.py"
    spec = importlib.util.spec_from_file_location("_robustness", rp)
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    r = mod.run()
    assert r["folds_ok"] >= 9          # right direction in (almost) every fold
    assert r["mean_gap"] > 0.05        # and a materially positive average gap
