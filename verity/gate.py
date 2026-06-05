"""Verification gate — a Reality Anchor for empirical result-claims.

A *claim* is a dict describing a measured result, e.g.::

    {"name": "btc-momentum", "accuracy": 0.51, "sample_size": 300,
     "out_of_sample": True, "leakage_checked": True,
     "text": "daily directional, walk-forward holdout, no look-ahead"}

``check()`` scores it against a *truth* dict (see ``truth.yaml``):

  * structural hygiene — sample floor, suspicious accuracy, out-of-sample and
    leakage requirements; and
  * ground-truth facts — a forbidden term inside a fact's domain, with no
    canonical term present, is a contradiction at that fact's severity.

Verdict: ``REFUSE`` (any CRITICAL) | ``WARN`` (any issue) | ``PASS`` (clean).
Nothing is believed until it clears. A PASS means *trustworthy*, not *profitable*.
"""
from __future__ import annotations

import json
import math
from pathlib import Path

try:
    import yaml
except ModuleNotFoundError:  # the gate still runs (with empty truth) without PyYAML
    yaml = None

_SEV = {"INFO": 0, "LOW": 1, "MEDIUM": 2, "HIGH": 3, "CRITICAL": 4}


def _norm(s: str) -> str:
    return " ".join((s or "").lower().split())


def load_truth(path: str | Path) -> dict:
    """Load thresholds + facts from a YAML file (empty dict if missing/no PyYAML)."""
    p = Path(path)
    if yaml is None or not p.exists():
        return {"thresholds": {}, "facts": []}
    return yaml.safe_load(p.read_text(encoding="utf-8")) or {}


def _structural(claim: dict, th: dict) -> list[dict]:
    issues: list[dict] = []
    raw_acc = claim.get("accuracy", claim.get("win_rate"))
    acc = _num(raw_acc)                       # via _num: never raises on a string/bool/NaN field
    n = _num(claim.get("sample_size"))
    # A disclosed-but-unparseable sample size / accuracy is itself suspect — a number we cannot
    # read is not a number we can trust. Flag it instead of silently skipping the floor.
    if claim.get("sample_size") is not None and n is None:
        issues.append({"check": "sample_size", "severity": "HIGH",
                       "detail": f"sample_size {claim.get('sample_size')!r} is not a finite number — unverifiable"})
    if raw_acc is not None and acc is None:
        issues.append({"check": "metric_range", "severity": "HIGH",
                       "detail": f"accuracy/win_rate {raw_acc!r} is not a finite number — unverifiable"})
    if n is not None:
        if n < th.get("hard_min_sample", 30):
            issues.append({"check": "sample_size", "severity": "CRITICAL",
                           "detail": f"sample {n:g} < hard floor {th.get('hard_min_sample', 30)} — noise"})
        elif n < th.get("min_sample", 100):
            issues.append({"check": "sample_size", "severity": "HIGH",
                           "detail": f"sample {n:g} < {th.get('min_sample', 100)} — thin"})
    if acc is not None:
        # An accuracy / win-rate outside [0,1] is impossible — a unit error or fabrication, not a
        # merely-suspicious result. CRITICAL: a metric that cannot exist must never be believed.
        if not (0.0 <= acc <= 1.0):
            issues.append({"check": "metric_range", "severity": "CRITICAL",
                           "detail": f"accuracy/win_rate {acc:g} outside the valid [0,1] range — "
                                     "impossible value (unit error or fabrication)"})
        elif acc > th.get("suspicious_accuracy", 0.65):
            issues.append({"check": "suspicious_accuracy", "severity": "HIGH",
                           "detail": f"accuracy {acc:g} > {th.get('suspicious_accuracy', 0.65)} — "
                                     "auto-suspect; prove it isn't a leak/bug"})
    if th.get("require_out_of_sample", True) and not _affirmed(claim.get("out_of_sample")):
        issues.append({"check": "out_of_sample", "severity": "HIGH",
                       "detail": "not validated out-of-sample / on a holdout"})
    if th.get("require_leakage_check", True) and not _affirmed(claim.get("leakage_checked")):
        issues.append({"check": "leakage", "severity": "HIGH",
                       "detail": "look-ahead / leakage not affirmatively checked"})
    return issues


def _match_facts(text: str, facts: list[dict]) -> list[dict]:
    t = _norm(text)
    out: list[dict] = []
    for f in facts:
        if not any(_norm(k) in t for k in f.get("domain_keywords", [])):
            continue  # claim is not in this fact's domain
        canonical = any(_norm(c) in t for c in f.get("canonical_terms", []))
        forbidden = [c for c in f.get("forbidden_terms", []) if _norm(c) in t]
        if forbidden and not canonical:
            out.append({"check": f["id"], "severity": f.get("severity", "MEDIUM"),
                        "detail": f"forbidden {forbidden} in-domain with no canonical evidence"})
        # DELIBERATELY no "forbidden AND canonical => soft flag" rule: canonical terms suppress the
        # contradiction by design, and forbidden terms like "look-ahead" legitimately appear inside
        # canonical phrases ("no look-ahead"). Surfacing the co-occurrence would false-alarm on every
        # honest "we did NOT use future data" claim — and reliable negation detection is exactly the
        # fuzzy-NLP this gate refuses to do. The laundering risk is a documented honest gap, not a
        # silently-broken check. (See README "Honest gaps".)
    return out


def _num(v):
    """float(v) or None — never raises, so a malformed field is simply not scored.

    A bool is deliberately NOT coerced: ``True``/``False`` are flags, not measurements,
    and silently reading them as ``1.0``/``0.0`` would let a boolean field masquerade as a
    numeric one (e.g. an accuracy of ``True``). NaN / ±inf are rejected too — a non-finite
    "number" is a fabrication-shaped value, not something to score against a threshold.
    """
    if isinstance(v, bool):
        return None
    try:
        f = float(v)
    except (TypeError, ValueError):
        return None
    return f if math.isfinite(f) else None


# Strings that look like a positive affirmation but are actually a denial — an agent that
# writes ``out_of_sample: "false"`` must NOT slip past the holdout/leakage checks because the
# non-empty string happens to be truthy. Treated as False for the "did you affirm X?" checks.
_FALSEY_STRINGS = {"false", "no", "0", "none", "n", "off", "nan", "null", ""}


def _affirmed(v) -> bool:
    """Did the claim AFFIRMATIVELY assert this flag? Defends against deceptive truthiness.

    ``True``/non-zero-number/an unambiguous yes → affirmed; ``False``/missing/0/NaN and any
    denial-shaped string ("false", "no", "0", …) → NOT affirmed. A bare truthy string that is
    not a known denial is taken at face value (affirmed).
    """
    if isinstance(v, str):
        return _norm(v) not in _FALSEY_STRINGS
    if isinstance(v, float) and not math.isfinite(v):
        return False                        # a NaN/inf "flag" is not an affirmation
    f = _num(v)
    if f is not None:                       # numeric (incl. 0.0) — affirmed iff non-zero & finite
        return f != 0.0
    return bool(v)                          # genuine bool / other truthy object


def _rigor(claim: dict, th: dict) -> list[dict]:
    """Statistical-rigor checks for an empirical result-claim.

    Each fires ONLY when the claim discloses the relevant field (or the truth config requires
    it), so a sparse claim is never spuriously flagged — these *add* scrutiny when there is
    something concrete to scrutinise:

      * ``significance``        — a disclosed z-score / p-value must actually clear the bar.
      * ``multiple_comparisons``— "best of N tries" inflates significance unless corrected.
      * ``base_rate``           — accuracy must beat the majority-class frequency by a real margin.
      * ``confidence_interval`` — (opt-in via config) a point estimate should carry an error bar.
      * ``effect_size``         — a disclosed standardized effect must clear a practical floor
                                  (significant-but-negligible is large-n p-hacking).
      * ``underpowered``        — a disclosed effect + sample size must clear the minimum
                                  detectable effect at 80% power (a null on tiny n is not evidence
                                  of absence; an over-claimed positive whose n can't support it).
      * ``ci_coherence``        — a disclosed CI must bracket its own point estimate and have a
                                  sane, informative width.

    All are at most HIGH severity (a rigor gap is a WARN, not the noise-floor REFUSE).
    """
    issues: list[dict] = []
    acc = _num(claim.get("accuracy", claim.get("win_rate")))

    # significance — a reported effect must be statistically distinguishable from chance
    z = _num(claim.get("z", claim.get("z_vs_50", claim.get("z_score"))))
    if z is not None and abs(z) < th.get("min_z", 2.0):
        issues.append({"check": "significance", "severity": "HIGH",
                       "detail": f"z {z:g} < {th.get('min_z', 2.0)} — not statistically distinguishable from chance"})
    p = _num(claim.get("p_value", claim.get("p")))
    if p is not None and p > th.get("max_p", 0.05):
        issues.append({"check": "significance", "severity": "HIGH",
                       "detail": f"p {p:g} > {th.get('max_p', 0.05)} — not significant"})

    # multiple comparisons — best-of-N selection inflates any significance unless corrected
    n_comp = _num(claim.get("n_comparisons", claim.get("strategies_tried", claim.get("variants_tried"))))
    if n_comp is not None and n_comp > 1 and not _affirmed(claim.get("multiplicity_corrected")):
        issues.append({"check": "multiple_comparisons", "severity": "MEDIUM",
                       "detail": f"best of {int(n_comp)} comparisons, no multiplicity correction — "
                                 "significance is selection-inflated (e.g. apply Bonferroni)"})

    # base rate — accuracy has to beat the majority class by a real margin, or it is no lift
    br = _num(claim.get("base_rate"))
    if br is not None and acc is not None and acc <= br + th.get("min_lift", 0.0):
        issues.append({"check": "base_rate", "severity": "HIGH",
                       "detail": f"accuracy {acc:g} ≤ base rate {br:g} (+{th.get('min_lift', 0.0)} lift) — "
                                 "no real lift over the majority class"})

    # confidence interval — opt-in: a point estimate should carry an error bar
    has_ci = any(claim.get(k) is not None for k in ("ci", "ci_95", "confidence_interval", "std_error", "stderr"))
    if th.get("require_confidence_interval", False) and acc is not None and not has_ci:
        issues.append({"check": "confidence_interval", "severity": "MEDIUM",
                       "detail": "point estimate with no confidence interval / error bar reported"})

    # ── R1: effect-size floor ─────────────────────────────────────────────────
    # A standardized effect can be statistically detectable yet practically negligible — at large
    # n, a trivial effect clears the z-bar (textbook large-n p-hacking). Fires only when disclosed.
    es = _num(claim.get("effect_size", claim.get("cohens_d", claim.get("d"))))
    if es is not None:
        min_es = th.get("min_effect_size", 0.1)
        if abs(es) < min_es:
            issues.append({"check": "effect_size", "severity": "HIGH",
                           "detail": f"effect size {es:g} < {min_es:g} — statistically detectable "
                                     "but practically negligible"})

    # ── R2: statistical power / minimum detectable effect ─────────────────────
    # Crude closed-form MDE at alpha=0.05, power=0.80 (standard-normal constants, no scipy):
    #   mde ≈ (z_a + z_b) / sqrt(n)  in standardized units.
    # The effect is taken in SD units: the disclosed effect size, else a proportion-lift
    # (accuracy − base_rate). 'No significant effect' on a tiny n is unsurprising, not evidence of
    # absence; an over-claimed positive whose n can't support it is equally suspect. Fires only when
    # BOTH an effect and a sample size are disclosed.
    z_a = th.get("power_z_alpha", 1.96)
    z_b = th.get("power_z_beta", 0.84)
    br_p = _num(claim.get("base_rate"))
    effect_sd = es if es is not None else (
        (acc - br_p) if (acc is not None and br_p is not None) else None)
    n_pow = _num(claim.get("sample_size"))
    if effect_sd is not None and n_pow is not None and n_pow > 0:
        mde = (z_a + z_b) / math.sqrt(n_pow)
        if abs(effect_sd) < mde:
            n_needed = (math.ceil(((z_a + z_b) / effect_sd) ** 2)
                        if effect_sd != 0 else float("inf"))
            issues.append({"check": "underpowered", "severity": "HIGH",
                           "detail": f"n={int(n_pow)} underpowered for effect {effect_sd:g} "
                                     f"(needs ~{n_needed} for 80% power)"})

    # ── R3: confidence-interval coherence ─────────────────────────────────────
    # Validates a CI that IS present (distinct from the opt-in presence check above). Fires only
    # when a 2-element interval AND a point estimate are disclosed.
    ci_raw = next((claim.get(k) for k in ("ci", "ci_95", "confidence_interval")
                   if claim.get(k) is not None), None)
    est = acc  # the point estimate is the accuracy / win_rate
    if est is not None and isinstance(ci_raw, (list, tuple)) and len(ci_raw) == 2:
        lo, hi = _num(ci_raw[0]), _num(ci_raw[1])
        if lo is not None and hi is not None:
            if not (lo <= est <= hi):
                issues.append({"check": "ci_coherence", "severity": "HIGH",
                               "detail": f"point estimate {est:g} lies outside its own CI "
                                         f"[{lo:g},{hi:g}]"})
            width = hi - lo
            if width <= 0:
                issues.append({"check": "ci_coherence", "severity": "HIGH",
                               "detail": "degenerate confidence interval (width<=0)"})
            elif width > th.get("max_ci_width", 1.0):
                issues.append({"check": "ci_coherence", "severity": "MEDIUM",
                               "detail": "confidence interval wider than the whole metric range "
                                         "— uninformative"})

    return issues


def _verdict_of(issues: list[dict]) -> str:
    """Worst severity across ``issues`` → REFUSE (≥ CRITICAL) / WARN (any) / PASS (clean).

    The single, canonical verdict rule. ``check`` and ``verify`` both defer to it so there is
    exactly one ladder and one vocabulary — never a second.
    """
    worst = max((_SEV.get(i.get("severity"), 0) for i in issues), default=0)
    return "REFUSE" if worst >= _SEV["CRITICAL"] else "WARN" if issues else "PASS"


def check(claim: dict, truth: dict) -> dict:
    """Score a claim. Returns ``{'verdict': REFUSE|WARN|PASS, 'issues': [...]}``.

    Defensive by construction: a non-dict claim, a non-dict ``truth``, ``None`` thresholds/facts,
    or a field value that does not JSON-serialize must never crash the verifier — an input that
    can take the gate *down* is itself a way to bypass it. A structurally-invalid claim is REFUSEd.
    """
    if not isinstance(claim, dict):
        return {"verdict": "REFUSE", "issues": [{"source": "structural", "check": "malformed_claim",
                "severity": "CRITICAL",
                "detail": f"claim is {type(claim).__name__}, not an object — nothing to verify"}]}
    truth = truth if isinstance(truth, dict) else {}
    th = truth.get("thresholds") or {}        # tolerate thresholds: None / missing
    facts = truth.get("facts") or []          # tolerate facts: None / missing
    if not isinstance(th, dict):
        th = {}
    # Build the searchable text WITHOUT assuming every field is JSON-serialisable (a set, a custom
    # object, … must not raise). default=str renders anything; we only need it for substring search.
    fields = {k: v for k, v in claim.items() if k != "text"}
    text = str(claim.get("text", "")) + " " + json.dumps(fields, default=str)
    issues = ([{"source": "structural", **s} for s in _structural(claim, th)]
              + [{"source": "rigor", **r} for r in _rigor(claim, th)]
              + [{"source": "ground_truth", **c} for c in _match_facts(text, facts)])
    return {"verdict": _verdict_of(issues), "issues": issues}


def _claim_label(claim) -> str:
    """A short, crash-proof display label for a claim (dict or not)."""
    if isinstance(claim, dict):
        return str(claim.get("name", claim.get("text", "?")))
    return f"<{type(claim).__name__}>"


def format_block(claim: dict, result: dict) -> str:
    """Render a human-readable VERIFIED block for a checked claim."""
    lines = ["VERIFIED",
             f"  Claim:   {_claim_label(claim)}",
             f"  Verdict: {result['verdict']}"]
    if result["issues"]:
        lines.append("  Issues:")
        for i in result["issues"]:
            lines.append(f"    [{i['severity']}] {i['source']}: {i['detail']}")
    else:
        lines.append("  Issues:  none — claim clears the bar")
    lines.append("  Note:    a PASS clears THESE checks only — not that an edge is real.")
    return "\n".join(lines)


def format_verify_block(claim: dict, res: dict) -> str:
    """Render a multi-dimension VERIFIED block for a ``verify`` result.

    Like ``format_block``, but adds a ``Dimensions:`` section listing each RUN dimension's
    verdict, then the flattened issues grouped by source. Keeps the closing scope note so the
    surface never over-promises (a PASS clears THESE checks only).
    """
    lines = ["VERIFIED",
             f"  Claim:   {_claim_label(claim)}",
             f"  Verdict: {res['verdict']}",
             "  Dimensions:"]
    for dim, body in res.get("dimensions", {}).items():
        lines.append(f"    {dim:<12} {body['verdict']}")
    issues = res.get("issues", [])
    if issues:
        lines.append("  Issues (by source):")
        # group in a stable source order, then by appearance within each source
        order = ["structural", "rigor", "ground_truth", "evidence", "consistency"]
        seen = [s for s in order if any(i["source"] == s for i in issues)]
        seen += [s for s in dict.fromkeys(i["source"] for i in issues) if s not in seen]
        for src in seen:
            for i in issues:
                if i["source"] == src:
                    chk = str(i.get("check", ""))
                    # some checks already embed their source (e.g. "evidence:accuracy") — don't
                    # double it up into "evidence:evidence:accuracy"; show the check id as-is then.
                    label = chk if chk.startswith(f"{src}:") else f"{src}:{chk}"
                    lines.append(f"    [{i['severity']:8}] {label}  {i['detail']}")
    else:
        lines.append("  Issues:  none — claim clears every run dimension")
    lines.append("  Note:    a PASS clears THESE checks only — not that an edge is real.")
    return "\n".join(lines)
