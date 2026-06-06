"""The testing surface — `assert_verified` fails a test on an untrustworthy claim, passes a clean one."""
import pytest

from verity import assert_verified


def test_assert_verified_passes_a_clean_claim():
    r = assert_verified({"name": "ok", "accuracy": 0.58, "sample_size": 1000,
                         "out_of_sample": True, "leakage_checked": True})
    assert r["verdict"] == "PASS"


def test_assert_verified_raises_on_refuse():
    with pytest.raises(AssertionError):
        assert_verified({"name": "junk", "accuracy": 0.99, "sample_size": 8, "out_of_sample": False})


def test_assert_verified_warn_is_gated_by_allow_warn():
    # a marginal p-value (0.03) WARNs — tolerated by default, fatal under allow_warn=False
    marginal = {"name": "marg", "accuracy": 0.58, "sample_size": 1000,
                "out_of_sample": True, "leakage_checked": True, "p_value": 0.03}
    assert assert_verified(marginal, allow_warn=True)["verdict"] == "WARN"
    with pytest.raises(AssertionError):
        assert_verified(marginal, allow_warn=False)
