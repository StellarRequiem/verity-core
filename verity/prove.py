"""Proof-carrying claims — does the number actually *reproduce*?

The gate (``check`` / ``verify``) asks *is this claim statistically trustworthy?*
— sample floor, base-rate lift, out-of-sample, leakage. It never re-derives the
number. ``prove`` closes that gap: a claim carries a re-runnable ``proof``
command; ``prove`` RUNS it and asserts the produced value matches the *claimed*
value within tolerance. A claim with no proof, a proof that errors, output with
no parseable value, or a mismatch all **REFUSE**. A reproduced match **PASSES**.

This is the reproducibility leg of the Reality Anchor: not "is the stat sound"
(``check``) and not "does it match cited evidence" (``verify``/``ground``), but
"does this number fall out of a command anyone can re-run." A PASS means
*reproduced*, not *profitable*.

SECURITY — read before pointing this at a file. ``prove`` EXECUTES the command in
each claim's ``proof`` field. Those commands are meant to be the PROJECT'S OWN
proof recipes — committed to its repo, run in its own trusted CI, exactly like
its test suite. It is **not** a sandbox. Never run ``prove`` over a claims file
from an untrusted source. (This is also why ``prove`` is intentionally CLI/CI
only and is *not* exposed as an MCP tool — agent-facing arbitrary-command
execution is a surface we don't open.)

A *claim* here is the same dict the rest of verity uses, plus::

    {"name": "fraud-detector", "metric": "accuracy", "value": 0.94,
     "proof": "python eval.py --metric accuracy", "tolerance": 0.005}

``proof`` is a shell-style string (``shlex``-split) or an argv list. The command
should print the reproduced value to stdout — as JSON (``{"accuracy": 0.94}`` or
a bare number), a labelled line (``accuracy: 0.94`` / ``accuracy=0.94``), or
failing those, the last number on stdout is taken as the headline result.
"""
from __future__ import annotations

import json
import math
import re
import shlex
import subprocess

PASS, REFUSE = "PASS", "REFUSE"

# A number, including scientific notation. Used for the plaintext fallback.
_NUM = re.compile(r"-?\d+\.?\d*(?:[eE][-+]?\d+)?")
# Known metric keys, in the order we'd guess one if the claim doesn't say `metric`.
_METRIC_KEYS = ("accuracy", "win_rate", "f1", "auc", "roc_auc", "precision",
                "recall", "score", "value")


def _claimed(claim: dict):
    """Return ``(metric_name, claimed_value)``. Explicit ``value`` wins; otherwise the
    first recognised metric key present in the claim."""
    if "value" in claim:
        return claim.get("metric", "value"), claim["value"]
    for k in _METRIC_KEYS:
        if k in claim:
            return k, claim[k]
    return None, None


def _labelled(stdout: str, metric: str | None) -> float | None:
    """A line like ``accuracy: 0.94`` or ``accuracy = 0.94`` (case-insensitive)."""
    if not metric:
        return None
    m = re.search(rf"{re.escape(metric)}\s*[:=]\s*({_NUM.pattern})", stdout, re.I)
    return float(m.group(1)) if m else None


def extract_value(stdout: str, metric: str | None = None) -> float | None:
    """Pull the reproduced number from the proof command's stdout.

    Priority: (1) JSON — a dict keyed by ``metric``, or a dict with exactly one
    numeric value, or a bare number; (2) a ``metric: value`` labelled line;
    (3) the LAST number on stdout (the command's headline result). ``None`` if
    nothing parses.
    """
    s = stdout.strip()
    if not s:
        return None
    # (1) JSON output
    try:
        obj = json.loads(s)
        if isinstance(obj, bool):  # json.loads("true") -> True; not a metric
            pass
        elif isinstance(obj, (int, float)):
            return float(obj)
        elif isinstance(obj, dict):
            if metric and isinstance(obj.get(metric), (int, float)) and not isinstance(obj.get(metric), bool):
                return float(obj[metric])
            nums = [v for v in obj.values() if isinstance(v, (int, float)) and not isinstance(v, bool)]
            if len(nums) == 1:
                return float(nums[0])
    except ValueError:
        pass
    # (2) labelled line
    lab = _labelled(s, metric)
    if lab is not None:
        return lab
    # (3) last number on stdout
    nums = _NUM.findall(s)
    return float(nums[-1]) if nums else None


def prove(claim: dict, *, cwd: str | None = None, timeout: float = 600.0,
          tolerance: float | None = None) -> dict:
    """Run the claim's ``proof`` command and check the produced value matches the claim.

    Returns ``{name, metric, claimed, reproduced, cmd, returncode, verdict, detail}``.
    ``verdict`` is ``PASS`` only when the command runs cleanly AND the reproduced
    value is within tolerance of the claimed value; everything else is ``REFUSE``.
    """
    name = str(claim.get("name") or claim.get("text", "?"))
    proof = claim.get("proof")
    metric, claimed = _claimed(claim)
    tol = tolerance if tolerance is not None else float(claim.get("tolerance", 0.005))

    base = {"name": name, "metric": metric, "claimed": claimed,
            "reproduced": None, "cmd": proof, "returncode": None}

    if not proof:
        return {**base, "verdict": REFUSE,
                "detail": "no `proof` command — the claim is not re-runnable"}
    if claimed is None:
        return {**base, "verdict": REFUSE,
                "detail": "no claimed value to check (set `value` or a metric key)"}
    try:
        claimed_f = float(claimed)
    except (TypeError, ValueError):
        return {**base, "verdict": REFUSE,
                "detail": f"claimed value {claimed!r} is not numeric"}

    try:
        argv = proof if isinstance(proof, list) else shlex.split(proof)
        run = subprocess.run(argv, cwd=cwd, capture_output=True, text=True, timeout=timeout)
    except subprocess.TimeoutExpired:
        return {**base, "verdict": REFUSE, "detail": f"proof command timed out after {timeout:g}s"}
    except (OSError, ValueError) as e:
        return {**base, "verdict": REFUSE, "detail": f"proof command could not run: {e}"}

    base["returncode"] = run.returncode
    if run.returncode != 0:
        last = ((run.stderr or run.stdout).strip().splitlines() or [""])[-1]
        return {**base, "verdict": REFUSE,
                "detail": f"proof command exited {run.returncode}: {last[:120]}"}

    repro = extract_value(run.stdout, metric)
    base["reproduced"] = repro
    if repro is None:
        return {**base, "verdict": REFUSE, "detail": "proof produced no parseable value on stdout"}

    if math.isclose(repro, claimed_f, abs_tol=tol):
        return {**base, "verdict": PASS,
                "detail": f"reproduced {repro:g} ≈ claimed {claimed_f:g} (±{tol:g})"}
    return {**base, "verdict": REFUSE,
            "detail": f"reproduced {repro:g} ≠ claimed {claimed_f:g} "
                      f"(Δ={abs(repro - claimed_f):g} > ±{tol:g})"}


def prove_batch(claims: list[dict], *, cwd: str | None = None,
                timeout: float = 600.0) -> list[dict]:
    """Prove a list of claims; returns one result dict per claim (order preserved)."""
    return [prove(c, cwd=cwd, timeout=timeout) for c in claims]


def format_prove_block(result: dict) -> str:
    """One-line ``[VERDICT] name — detail`` rendering, matching the batch roll-ups."""
    return f"  [{result['verdict']:6}] {str(result['name'])[:56]}  —  {result['detail']}"
