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
    acc = claim.get("accuracy", claim.get("win_rate"))
    n = claim.get("sample_size")
    if n is not None:
        if n < th.get("hard_min_sample", 30):
            issues.append({"check": "sample_size", "severity": "CRITICAL",
                           "detail": f"sample {n} < hard floor {th.get('hard_min_sample', 30)} — noise"})
        elif n < th.get("min_sample", 100):
            issues.append({"check": "sample_size", "severity": "HIGH",
                           "detail": f"sample {n} < {th.get('min_sample', 100)} — thin"})
    if acc is not None and acc > th.get("suspicious_accuracy", 0.65):
        issues.append({"check": "suspicious_accuracy", "severity": "HIGH",
                       "detail": f"accuracy {acc} > {th.get('suspicious_accuracy', 0.65)} — auto-suspect; prove it isn't a leak/bug"})
    if th.get("require_out_of_sample", True) and not claim.get("out_of_sample"):
        issues.append({"check": "out_of_sample", "severity": "HIGH",
                       "detail": "not validated out-of-sample / on a holdout"})
    if not claim.get("leakage_checked"):
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
    return out


def check(claim: dict, truth: dict) -> dict:
    """Score a claim. Returns ``{'verdict': REFUSE|WARN|PASS, 'issues': [...]}``."""
    th = truth.get("thresholds", {})
    facts = truth.get("facts", [])
    text = claim.get("text", "") + " " + json.dumps(
        {k: v for k, v in claim.items() if k != "text"})
    issues = ([{"source": "structural", **s} for s in _structural(claim, th)]
              + [{"source": "ground_truth", **c} for c in _match_facts(text, facts)])
    worst = max((_SEV.get(i["severity"], 0) for i in issues), default=0)
    verdict = ("REFUSE" if worst >= _SEV["CRITICAL"]
               else "WARN" if issues else "PASS")
    return {"verdict": verdict, "issues": issues}


def format_block(claim: dict, result: dict) -> str:
    """Render a human-readable VERIFIED block for a checked claim."""
    lines = ["VERIFIED",
             f"  Claim:   {claim.get('name', claim.get('text', '?'))}",
             f"  Verdict: {result['verdict']}"]
    if result["issues"]:
        lines.append("  Issues:")
        for i in result["issues"]:
            lines.append(f"    [{i['severity']}] {i['source']}: {i['detail']}")
    else:
        lines.append("  Issues:  none — claim clears the bar")
    lines.append("  Note:    a PASS clears THESE checks only — not that an edge is real.")
    return "\n".join(lines)
