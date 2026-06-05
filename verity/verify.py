"""verity.verify — the unified, multi-dimension verification entrypoint.

``verify()`` is a thin orchestrator over per-dimension checks. It does NOT
re-implement gate logic:

  * EMPIRICAL   — always runs ``gate.check`` (structural + rigor + ground-truth).
  * EVIDENCE    — runs iff ``evidence`` is supplied: rule-based field reconciliation
                  of the claim against recomputed ground-truth values.
  * CONSISTENCY — runs iff ``prior`` is supplied: rule-based contradiction check of
                  the claim against a previously-asserted claim.

Every dimension emits the SAME issue dict the gate already emits —
``{"source", "check", "severity", "detail"}`` — and the overall verdict is the
worst severity across ALL run dimensions, by the one ``gate`` ladder
(REFUSE ≥ CRITICAL / WARN any / PASS clean). One vocabulary, no second.

EVIDENCE and CONSISTENCY are deterministic field reconciliation, never fuzzy NLP:
they compare structured numeric / bool / string fields key-by-key with an explicit
numeric tolerance and exact normalized string equality. A field participates only
if it appears in BOTH dicts; non-shared keys are silent (an honest gap, not a guess).
Pure-Python, deterministic, no I/O — ``verify`` takes a *resolved* truth dict, never
a path, so the load (and any file I/O) stays with the caller / CLI / MCP.
"""
from __future__ import annotations

import math
from pathlib import Path

from .gate import _SEV, _norm, _num, check, load_truth

# The packaged default truth — the same one mcp.py / cli use when none is given.
_DEFAULT_TRUTH = Path(__file__).resolve().parent / "truth.yaml"

# Keys never reconciled as data — they are free-text / identity, not measured facts.
_TEXT_KEYS = ("text", "name")
# Keys ignored by the CONSISTENCY check: bookkeeping that is *expected* to change.
_IGNORE_CONSISTENCY = {"timestamp", "ts", "run_id", "seq"}
# Signed effect fields where a sign flip is a direct contradiction (CONSISTENCY).
_SIGNED_EFFECT = {"effect", "effect_size", "lift", "z", "delta", "edge"}


def _verdict_of(issues: list[dict]) -> str:
    """Worst severity across ``issues`` → REFUSE (≥ CRITICAL) / WARN (any) / PASS (clean).

    Mirrors ``gate.check``'s verdict rule exactly. ``gate`` may export the canonical
    extraction of this helper; if it does we defer to it so there is a single source
    of truth, otherwise this byte-identical fallback keeps ``verify`` self-contained.
    """
    from . import gate
    canonical = getattr(gate, "_verdict_of", None)
    if canonical is not None and canonical is not _verdict_of:
        return canonical(issues)
    worst = max((_SEV.get(i["severity"], 0) for i in issues), default=0)
    return "REFUSE" if worst >= _SEV["CRITICAL"] else "WARN" if issues else "PASS"


def _shared_keys(a: dict, b: dict) -> list[dict]:
    """Keys present in BOTH dicts, excluding free-text/identity keys, in claim order."""
    return [k for k in a if k in b and k not in _TEXT_KEYS]


def _num_disagree(c: float, e: float, th: dict) -> bool:
    """True iff two numbers differ beyond max(abs_tol, rel_tol * |e|).

    Tolerances are clamped to be non-negative: a NEGATIVE tolerance in a (poisoned or simply
    fat-fingered) truth pack would otherwise make *every* comparison — even ``0.5`` vs ``0.5`` —
    "disagree", a config-induced false alarm. A non-finite difference (NaN/inf, e.g. NaN inputs)
    is treated as NOT a numeric disagreement here; such fields are routed to the type-mismatch
    branch by the caller instead. Identical numbers always agree.
    """
    if c == e:
        return False
    diff = abs(c - e)
    if not math.isfinite(diff):
        return False
    tol_abs = max(0.0, _num(th.get("evidence_abs_tol", 1e-9)) or 0.0)
    tol_rel = max(0.0, _num(th.get("evidence_rel_tol", 0.01)) or 0.0)
    return diff > max(tol_abs, tol_rel * abs(e))


def _evidence(claim: dict, evidence: dict, sources: list | None, th: dict) -> list[dict]:
    """Reconcile the claim's structured fields against recomputed ground-truth values.

    For each key present in BOTH ``claim`` and ``evidence`` (excluding text/name):
      * both bool (or one bool)  → mismatch if unequal               → HIGH
      * both numeric             → mismatch beyond tolerance         → CRITICAL
                                   (a claimed number disagreeing with ground truth is
                                    a fabrication-class error)
      * both str                 → mismatch if normalized-unequal    → MEDIUM
      * mixed / uncoercible, unequal                                 → MEDIUM, "evidence_type"
    Plus: if ``sources`` is supplied but empty, one LOW "sources_missing" issue —
    evidence asserted with no provenance cited. Keys in only one dict are silent.
    """
    issues: list[dict] = []
    for k in _shared_keys(claim, evidence):
        c, e = claim[k], evidence[k]
        c_bool, e_bool = isinstance(c, bool), isinstance(e, bool)
        if c_bool or e_bool:
            # bool branch FIRST — bool is an int subtype, so float(True)==1.0 would
            # otherwise mask a true/false flip inside the numeric branch.
            if c != e:
                issues.append({"source": "evidence", "check": f"evidence:{k}", "severity": "HIGH",
                               "detail": f"claim {k}={c!r} disagrees with evidence {e!r}"})
            continue
        cn, en = _num(c), _num(e)
        if cn is not None and en is not None:
            if _num_disagree(cn, en, th):
                tol_rel = th.get("evidence_rel_tol", 0.01)
                issues.append({"source": "evidence", "check": f"evidence:{k}", "severity": "CRITICAL",
                               "detail": f"claim {k}={cn:g} disagrees with evidence {en:g} (tol {tol_rel:.0%})"})
            continue
        if isinstance(c, str) and isinstance(e, str):
            if _norm(c) != _norm(e):
                issues.append({"source": "evidence", "check": f"evidence:{k}", "severity": "MEDIUM",
                               "detail": f"claim {k}={c!r} disagrees with evidence {e!r}"})
            continue
        # mixed / uncoercible types
        if c != e:
            issues.append({"source": "evidence", "check": "evidence_type", "severity": "MEDIUM",
                           "detail": f"claim {k}={c!r} ({type(c).__name__}) not comparable to "
                                     f"evidence {e!r} ({type(e).__name__})"})
    if sources is not None and len(sources) == 0:
        issues.append({"source": "evidence", "check": "sources_missing", "severity": "LOW",
                       "detail": "evidence supplied with an empty sources list — provenance not cited"})
    return issues


def _consistency(claim: dict, prior: dict, th: dict) -> list[dict]:
    """Flag fields whose value contradicts a previously-asserted claim.

    For each key present in BOTH ``claim`` and ``prior`` (excluding text/name and the
    bookkeeping ignore set):
      * both bool                → contradiction if unequal              → HIGH
      * both numeric             → contradiction beyond the SAME tolerance → HIGH
                                   (a silently-revised number is a story-change, not
                                    necessarily fabrication — the prior could be wrong);
                                   a SIGN FLIP on a signed-effect field escalates to
                                   CRITICAL ("consistency:sign_flip").
      * both str                 → contradiction if normalized-unequal   → MEDIUM
    Non-shared keys are silent.
    """
    issues: list[dict] = []
    for k in _shared_keys(claim, prior):
        if k in _IGNORE_CONSISTENCY:
            continue
        c, p = claim[k], prior[k]
        c_bool, p_bool = isinstance(c, bool), isinstance(p, bool)
        if c_bool or p_bool:
            if c != p:
                issues.append({"source": "consistency", "check": f"consistency:{k}", "severity": "HIGH",
                               "detail": f"{k} changed {p!r} -> {c!r} vs prior assertion"})
            continue
        cn, pn = _num(c), _num(p)
        if cn is not None and pn is not None:
            if _num_disagree(cn, pn, th):
                if k in _SIGNED_EFFECT and (cn < 0) != (pn < 0) and cn != 0 and pn != 0:
                    issues.append({"source": "consistency", "check": "consistency:sign_flip",
                                   "severity": "CRITICAL",
                                   "detail": f"{k} sign-flipped {pn:g} -> {cn:g} vs prior assertion"})
                else:
                    issues.append({"source": "consistency", "check": f"consistency:{k}", "severity": "HIGH",
                                   "detail": f"{k} changed {pn:g} -> {cn:g} vs prior assertion"})
            continue
        if isinstance(c, str) and isinstance(p, str):
            if _norm(c) != _norm(p):
                issues.append({"source": "consistency", "check": f"consistency:{k}", "severity": "MEDIUM",
                               "detail": f"{k} changed {p!r} -> {c!r} vs prior assertion"})
            continue
        # mixed / uncoercible types that differ — still a story-change
        if c != p:
            issues.append({"source": "consistency", "check": f"consistency:{k}", "severity": "MEDIUM",
                           "detail": f"{k} changed {p!r} -> {c!r} vs prior assertion"})
    return issues


def verify(claim: dict, *, evidence: dict | None = None, sources: list | None = None,
           prior: dict | None = None, truth: dict | None = None) -> dict:
    """Verify ``claim`` across every applicable dimension before acting on it.

    EMPIRICAL hygiene always runs (``gate.check``). EVIDENCE-match runs iff ``evidence``
    is given; CONSISTENCY runs iff ``prior`` is given. A dimension key is ABSENT when its
    input was not supplied — so a caller can distinguish "checked and clean" from "not
    applicable". The overall verdict is the worst severity across all run dimensions,
    by the one ``gate`` ladder.

    ``truth`` is a *resolved* truth dict (thresholds + facts); when None the packaged
    default is loaded here. ``sources`` is used ONLY for a presence/empty check — it is
    never crawled or fetched (the no-I/O rule holds).

    Returns::

        {"verdict": "REFUSE"|"WARN"|"PASS",
         "dimensions": {"empirical": {"verdict", "issues"},
                        "evidence":    {...},   # iff evidence is not None
                        "consistency": {...}},  # iff prior    is not None
         "issues": [...all issues, flattened, each carrying its "source"...]}
    """
    if truth is None:
        truth = load_truth(_DEFAULT_TRUTH)
    if not isinstance(truth, dict):
        truth = {}
    th = truth.get("thresholds")
    th = th if isinstance(th, dict) else {}   # tolerate thresholds: None / non-dict

    dimensions: dict[str, dict] = {}
    all_issues: list[dict] = []

    # EMPIRICAL — always. gate.check already returns {"verdict", "issues"} in our shape, and is
    # itself defensive against a non-dict claim (it REFUSEs rather than crashing).
    empirical = check(claim, truth)
    dimensions["empirical"] = empirical
    all_issues.extend(empirical["issues"])

    # Field reconciliation needs dicts on BOTH sides. A non-dict claim has already been REFUSEd by
    # the empirical dimension; here we simply have nothing to reconcile field-by-field, so coerce a
    # non-dict to an empty mapping rather than crash. The supplied-ness (dimension presence) is
    # decided by the caller's argument, not by the value being a dict — `evidence=[]` is "supplied".
    claim_d = claim if isinstance(claim, dict) else {}

    # EVIDENCE — only when evidence was supplied (present-with-empty is still "supplied").
    if evidence is not None:
        ev_issues = _evidence(claim_d, evidence if isinstance(evidence, dict) else {}, sources, th)
        dimensions["evidence"] = {"verdict": _verdict_of(ev_issues), "issues": ev_issues}
        all_issues.extend(ev_issues)

    # CONSISTENCY — only when a prior assertion was supplied.
    if prior is not None:
        co_issues = _consistency(claim_d, prior if isinstance(prior, dict) else {}, th)
        dimensions["consistency"] = {"verdict": _verdict_of(co_issues), "issues": co_issues}
        all_issues.extend(co_issues)

    return {"verdict": _verdict_of(all_issues), "dimensions": dimensions, "issues": all_issues}
