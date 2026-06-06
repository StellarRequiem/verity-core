"""Gate a metric-producing function at its boundary — ``@verified``.

    from verity import verified, load_truth

    @verified(truth=load_truth("truths/ml-classification.yaml"))
    def evaluate(model, data) -> dict:
        ...
        return {"accuracy": acc, "sample_size": n, "out_of_sample": True, "leakage_checked": True}

The dict the function returns is run through ``verify`` the moment it is produced: a REFUSE raises
(an untrustworthy number can't propagate), a WARN is surfaced via ``warnings.warn`` and passes. The
same check an agent makes over MCP — wired here to a function boundary instead. Non-dict returns pass
through untouched, so it is safe to drop onto any function.
"""
from __future__ import annotations

import functools
import warnings

from .verify import verify


def verified(_fn=None, *, truth=None, allow_warn: bool = True):
    """Decorator (bare ``@verified`` or ``@verified(truth=..., allow_warn=...)``) — verify the dict a
    function returns; raise ``ValueError`` on REFUSE (and on WARN unless ``allow_warn``)."""
    def deco(fn):
        @functools.wraps(fn)
        def wrapper(*args, **kwargs):
            out = fn(*args, **kwargs)
            if isinstance(out, dict):
                r = verify(out, truth=truth)
                detail = "; ".join(i.get("detail", "") for i in r.get("issues", []))
                if r["verdict"] == "REFUSE" or (not allow_warn and r["verdict"] == "WARN"):
                    raise ValueError(f"verity {r['verdict']} — {fn.__name__} returned an "
                                     f"untrustworthy claim: {detail}")
                if r["verdict"] == "WARN":
                    warnings.warn(f"verity WARN — {fn.__name__}: {detail}", stacklevel=2)
            return out
        return wrapper

    return deco(_fn) if callable(_fn) else deco
