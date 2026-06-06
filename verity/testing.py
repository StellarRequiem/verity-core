"""verity in your test suite — assert a result-claim clears the bar.

    from verity import assert_verified

    def test_model_card_is_honest():
        assert_verified({"accuracy": 0.87, "sample_size": 5000,
                         "out_of_sample": True, "leakage_checked": True, "base_rate": 0.51})

A REFUSE fails the test (the AssertionError carries the reasons); a WARN fails too unless
``allow_warn=True`` (the default). Pass ``truth=`` for a domain pack, or
``evidence=`` / ``prior=`` / ``sources=`` to also reconcile the claim against recomputed truth, a
previously-asserted claim, or its cited sources — the same four dimensions ``verify`` runs.
"""
from __future__ import annotations

from .verify import verify


def assert_verified(claim, *, truth=None, evidence=None, sources=None, prior=None,
                    allow_warn: bool = True) -> dict:
    """Raise ``AssertionError`` unless ``claim`` clears the verity gate; return the verdict on pass.

    Designed for any test runner (pytest, unittest, plain ``assert``) — it is a thin, dependency-free
    wrapper over ``verify`` so a CI test suite can refuse to let an untrustworthy number ship.
    """
    r = verify(claim, evidence=evidence, sources=sources, prior=prior, truth=truth)
    failed = r["verdict"] == "REFUSE" or (not allow_warn and r["verdict"] == "WARN")
    if failed:
        name = claim.get("name", "claim") if isinstance(claim, dict) else "claim"
        reasons = "; ".join(i.get("detail", "") for i in r.get("issues", [])) or "no specific issue"
        raise AssertionError(f"verity {r['verdict']} — {name}: {reasons}")
    return r
