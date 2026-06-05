"""The EXTERNAL benchmark (non-circular): does the gate flag real replication failures more
than survivors? Labels come from independent replications, not from the gate's rules."""
from verity import external_eval
from verity.gate import check


def test_external_eval_trend_in_right_direction_but_honestly_underpowered():
    r = external_eval.run()
    assert r["n"] == 132 and r["n_failed"] == 63 and r["n_replicated"] == 69
    assert r["catch"] > r["false_alarm"] and r["odds_ratio"] > 1.0   # direction: failures flagged more
    assert r["separation"] < 0.40                                    # honestly modest, not an oracle
    # held to verity's own bar: the +10pp gap is NOT significant at n=132 — and we report it, not hide it
    assert "z" in r and "p_value" in r
    assert not r["significant"] and r["p_value"] > 0.05


def test_external_eval_cli_flags_its_own_insignificance(capsys):
    rc = external_eval.main([])
    out = capsys.readouterr().out
    assert "external, NOT circular" in out          # honesty banner ships
    assert "NOT significant" in out and "SUGGESTIVE" in out   # the harness flags its own under-power
    assert rc == 0                                   # CI guard = direction intact (not a significance claim)


def test_require_leakage_check_is_config_gated():
    c = {"accuracy": 0.55, "sample_size": 500, "out_of_sample": True}   # no leakage_checked field
    assert any(i["check"] == "leakage" for i in check(c, {"thresholds": {}, "facts": []})["issues"])
    off = check(c, {"thresholds": {"require_leakage_check": False}, "facts": []})
    assert not any(i["check"] == "leakage" for i in off["issues"])
