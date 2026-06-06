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


def _source_view(src) -> tuple[str, dict, str]:
    """Normalize one source into a uniform ``(sid, facts, text)`` view. Never raises.

    Three accepted shapes:
      * ``{"id"/"source"/"name": .., "facts": {..}, "text": ..}`` — a combined source: its
        ``facts`` dict is compared key-by-key and its ``text`` is substring-searched.
      * a bare facts dict (no dict-valued ``facts`` key) — the dict ITSELF is the facts bag;
        a ``text`` field, if any, doubles as searchable text (mirroring ``gate.check`` building
        searchable text from a claim's own ``text``).
      * a plain string — no facts, the whole string is the searchable text.
      * anything else (int / None / list / …) — no facts, ``str(src)`` as text, a generic id.

    ``sid`` is for the human-readable detail ONLY; it is never compared. Everything is
    ``str()``-wrapped so a weird / non-finite source value contributes facts={}/text but
    never crashes the verifier.
    """
    if isinstance(src, dict):
        if isinstance(src.get("facts"), dict):
            facts = src["facts"]
            text = str(src.get("text", ""))
            sid = src.get("id", src.get("source", src.get("name", "?")))
        else:
            facts = src
            text = str(src.get("text", ""))
            sid = src.get("id", src.get("source", src.get("name", "?")))
        return (str(sid), facts, text)
    if isinstance(src, str):
        return (src[:40] or "?", {}, src)            # plain-text source
    return (f"<{type(src).__name__}>", {}, str(src))


def _source_asserts(k: str, cv, facts: dict, text: str, th: dict) -> str:
    """Does ONE source assert claim-value ``cv`` for key ``k``? → "contradict" | "support" | "silent".

    STRUCTURED (``k`` is in ``facts``): reuse the EXACT evidence branch order & comparison —
    bool-first (so ``True == 1.0`` cannot mask a flip), then numeric-within-tolerance, then
    normalized-string, then a mixed/uncoercible fall-through. INTENTIONAL divergence from
    ``_evidence``: a mixed/uncoercible UNEQUAL structured value where BOTH sides are non-numeric
    (e.g. two differing lists/dicts) is a CONTRADICTION here (a source asserting the key with a
    concrete incomparable shape disputes the claim), where evidence treats it as a MEDIUM
    type-mismatch. The ONE exception — a deliberate adversarial guard — is the NUMERIC-vs-GARBAGE
    pair: if exactly one side is a finite number and the other is not (NaN/inf/set/None/list/…),
    the comparison is incoherent and the source is "silent" on that key, NOT a contradiction, so a
    poisoned source cannot weaponise junk into a forced REFUSE. Outside that guard, finding ``k`` in
    ``facts`` yields contradict/support — never "silent". ``k`` is excluded from ``facts``-search if
    it is a text/name key by the caller (``_grounding`` iterates non-text keys only), keeping the
    claim-side text exclusion symmetric.

    TEXT (``k`` NOT in ``facts``, ``text`` non-empty): the value's canonical string form is
    substring-searched (the same normalized-containment idiom as ``gate._match_facts``). A text
    source can only SUPPORT or be SILENT — NEVER contradict: the value's string being absent
    means the key may simply be phrased differently, not that the source asserts a different
    value. (This keeps the false-positive-contradiction risk at zero for prose sources.)
    """
    # (a) STRUCTURED match against this source's facts.
    if isinstance(facts, dict) and k in facts:
        sv = facts[k]
        cv_bool, sv_bool = isinstance(cv, bool), isinstance(sv, bool)
        if cv_bool or sv_bool:
            return "support" if cv == sv else "contradict"      # bool-first: True==1.0 masking
        cvn, svn = _num(cv), _num(sv)
        if cvn is not None and svn is not None:
            return "contradict" if _num_disagree(cvn, svn, th) else "support"
        if isinstance(cv, str) and isinstance(sv, str):
            return "support" if _norm(cv) == _norm(sv) else "contradict"
        # NUMERIC-vs-GARBAGE guard (adversarial): if EXACTLY ONE side reads as a finite number and
        # the other does NOT (NaN/inf, a set, None, a list, an unparseable string, …), the comparison
        # is INCOHERENT — the source is not making a credible, comparable counter-assertion about a
        # numeric key. Routing that to "contradict" would let a POISONED source force REFUSE on an
        # honest numeric claim merely by injecting unreadable junk for that key (a denial-of-trust
        # false-contradiction). Garbage neither grounds nor refutes → SILENT (degrades to the MEDIUM
        # "not supported by any cited source", never a garbage-driven CRITICAL). Mirrors _num's stance
        # that a non-finite "number" is fabrication-shaped, not a value to score against.
        if (cvn is None) != (svn is None):
            return "silent"
        # mixed / uncoercible, NEITHER numeric: a source asserting a concrete differing structured
        # value (e.g. two different lists/dicts) still disputes the claim (see docstring).
        return "support" if cv == sv else "contradict"
    # (b) TEXT match — only when the key is NOT structurally asserted and there is text to search.
    if text:
        if isinstance(cv, bool):
            vs = str(cv).lower()                                # "true" / "false"
        else:
            cvn = _num(cv)
            if cvn is not None:
                vs = f"{cvn:g}"                                 # 0.58 -> "0.58", 300 -> "300"
            elif isinstance(cv, str):
                vs = _norm(cv)
            else:
                vs = str(cv)
        if _norm(vs) in _norm(text):
            return "support"
    # (c) otherwise the source is silent on this key.
    return "silent"


def _grounding(claim: dict, sources: list, th: dict) -> list[dict]:
    """Reconcile each disclosed claim fact against what the CITED sources actually assert.

    For each disclosed claim key (every key except text/name, in claim order), scan ALL sources:

      * CONTRADICTION beats SUPPORT beats SILENT. If any source contradicts the key →
        CRITICAL (a fabrication-class error: the claim's OWN cited source asserts a different
        value) — even when another source supports it (sources that DISAGREE about the key do
        not safely ground it; surface the conflict). The detail names the first contradictor.
      * Else if at least one source supports the key → grounded (no issue).
      * Else (no source asserts the key at all) → MEDIUM "not supported by any cited source".

    A STRUCTURED source contradicts by asserting a differing value; a TEXT source can only
    support or be silent (see ``_source_asserts``). Sources are normalized once via
    ``_source_view``. Pure-Python, deterministic, no I/O — sources are caller-supplied resolved
    facts/text, exactly like ``truth``; they are NEVER fetched or crawled.
    """
    issues: list[dict] = []
    keys = [k for k in claim if k not in _TEXT_KEYS]
    views = [_source_view(s) for s in sources]      # normalize once: [(sid, facts, text), ...]
    for k in keys:
        cv = claim[k]
        states = [_source_asserts(k, cv, facts, text, th) for (_, facts, text) in views]
        contradictors = [(views[i][0], views[i][1].get(k)) for i, st in enumerate(states)
                         if st == "contradict"]
        if contradictors:
            sid, sv = contradictors[0]
            issues.append({"source": "grounding", "check": f"grounding:{k}", "severity": "CRITICAL",
                           "detail": f"claim {k}={cv!r} contradicts source {sid} {k}={sv!r}"})
        elif any(st == "support" for st in states):
            continue                                 # grounded — at least one source backs K
        else:
            issues.append({"source": "grounding", "check": f"grounding:{k}", "severity": "MEDIUM",
                           "detail": f"claim {k} not supported by any cited source"})
    return issues


def verify(claim: dict, *, evidence: dict | None = None, sources: list | None = None,
           prior: dict | None = None, truth: dict | None = None) -> dict:
    """Verify ``claim`` across every applicable dimension before acting on it.

    EMPIRICAL hygiene always runs (``gate.check``). EVIDENCE-match runs iff ``evidence``
    is given; CONSISTENCY runs iff ``prior`` is given; GROUNDING runs iff ``sources`` is a
    NON-EMPTY list. A dimension key is ABSENT when its input was not supplied — so a caller
    can distinguish "checked and clean" from "not applicable". The overall verdict is the
    worst severity across all run dimensions, by the one ``gate`` ladder.

    ``truth`` is a *resolved* truth dict (thresholds + facts); when None the packaged
    default is loaded here. ``sources`` is now used (a) by EVIDENCE for a presence/empty
    provenance check AND (b) by GROUNDING — when non-empty — as resolved facts/text to
    reconcile the claim against; it is still NEVER crawled or fetched (the no-I/O rule holds:
    sources are caller-supplied resolved facts/text, exactly like ``truth``).

    Returns::

        {"verdict": "REFUSE"|"WARN"|"PASS",
         "dimensions": {"empirical": {"verdict", "issues"},
                        "evidence":    {...},   # iff evidence is not None
                        "consistency": {...},   # iff prior    is not None
                        "grounding":   {...}},  # iff sources is a non-empty list
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

    # GROUNDING — only when `sources` is a NON-EMPTY list (real cited sources to reconcile
    # against). An empty/None sources list is NOT a grounding run: empty is the evidence dim's
    # "provenance missing" LOW case, None is "no provenance claimed". The isinstance guard makes a
    # non-list `sources` (e.g. a bare string) inert here. `claim_d` ({} for a non-dict claim,
    # already REFUSEd by empirical) yields no grounding keys — no crash.
    if isinstance(sources, list) and len(sources) > 0:
        gr_issues = _grounding(claim_d, sources, th)
        dimensions["grounding"] = {"verdict": _verdict_of(gr_issues), "issues": gr_issues}
        all_issues.extend(gr_issues)

    return {"verdict": _verdict_of(all_issues), "dimensions": dimensions, "issues": all_issues}
