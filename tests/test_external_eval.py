"""The EXTERNAL benchmark (non-circular): does the gate flag real replication failures more
than survivors? Labels come from independent replications, not from the gate's rules."""
from verity import external_eval
from verity.gate import check


def test_external_eval_discriminates_real_replication_failures():
    r = external_eval.run()
    assert r["n"] == 132 and r["n_failed"] == 63 and r["n_replicated"] == 69
    # the load-bearing external claim: verity flags FAILED-to-replicate claims MORE than survivors
    assert r["catch"] > r["false_alarm"]
    assert r["odds_ratio"] > 1.0
    # honestly modest — not an oracle (a stats gate can't see non-statistical failure causes)
    assert r["separation"] < 0.40


def test_external_eval_cli_exits_0_when_signal_intact(capsys):
    rc = external_eval.main([])
    out = capsys.readouterr().out
    assert "external, NOT circular" in out          # honesty banner ships
    assert "odds" in out.lower()
    assert rc == 0                                   # separation > 0 AND odds > 1


def test_require_leakage_check_is_config_gated():
    c = {"accuracy": 0.55, "sample_size": 500, "out_of_sample": True}   # no leakage_checked field
    assert any(i["check"] == "leakage" for i in check(c, {"thresholds": {}, "facts": []})["issues"])
    off = check(c, {"thresholds": {"require_leakage_check": False}, "facts": []})
    assert not any(i["check"] == "leakage" for i in off["issues"])
