"""The decorator surface — @verified gates a function's returned claim at the boundary."""
import warnings

import pytest

from verity import verified


def test_verified_raises_on_untrustworthy_return():
    @verified
    def bad():
        return {"accuracy": 0.99, "sample_size": 5, "out_of_sample": False}
    with pytest.raises(ValueError):
        bad()


def test_verified_passes_a_clean_return():
    @verified
    def good():
        return {"accuracy": 0.57, "sample_size": 1000, "out_of_sample": True, "leakage_checked": True}
    assert good()["accuracy"] == 0.57


def test_verified_warns_but_passes_on_warn():
    @verified                                     # marginal p -> WARN
    def marginal():
        return {"accuracy": 0.57, "sample_size": 1000, "out_of_sample": True,
                "leakage_checked": True, "p_value": 0.03}
    with warnings.catch_warnings(record=True) as w:
        warnings.simplefilter("always")
        marginal()
        assert any("verity WARN" in str(x.message) for x in w)
    @verified(allow_warn=False)                   # …unless strict
    def strict_marginal():
        return {"accuracy": 0.57, "sample_size": 1000, "out_of_sample": True,
                "leakage_checked": True, "p_value": 0.03}
    with pytest.raises(ValueError):
        strict_marginal()


def test_verified_ignores_non_dict_returns():
    @verified
    def scalar():
        return 42
    assert scalar() == 42
