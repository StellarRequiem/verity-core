"""verity CLI — check empirical result-claims from the shell or CI.

    verity check       --claim '{"accuracy":0.92,"sample_size":40}'  [--truth truth.yaml]
    verity check       --claim-file claim.json                       [--truth truth.yaml]
    verity check-batch claims.jsonl                                  [--truth truth.yaml]

A *claim* is a JSON object describing a measured result (accuracy/win_rate, sample_size,
out_of_sample, leakage_checked, optionally z / n_comparisons / base_rate …) or plain text.
The gate scores it — structural hygiene + statistical rigor + ground-truth facts — and returns
REFUSE / WARN / PASS. The **exit code is the worst verdict**, so this gates CI exactly like a
linter: `0` PASS · `1` WARN · `2` REFUSE. A PASS means *trustworthy*, not *profitable*.
"""
from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

from .gate import check, format_block, load_truth

_RANK = {"PASS": 0, "WARN": 1, "REFUSE": 2}


def _load_claim(s: str) -> dict:
    """A JSON object → a structured claim; anything else → a plain-text claim."""
    s = s.strip()
    if s.startswith("{"):
        try:
            obj = json.loads(s)
        except ValueError:
            obj = None
        if isinstance(obj, dict):
            return obj
    return {"text": s}


def _truth(path):
    return load_truth(path) if path else {"thresholds": {}, "facts": []}


def _worst(results: list[dict]) -> str:
    return max((r["verdict"] for r in results), key=lambda v: _RANK.get(v, 1), default="PASS")


def _cmd_check(args) -> int:
    raw = Path(args.claim_file).read_text(encoding="utf-8") if args.claim_file else args.claim
    claim = _load_claim(raw)
    result = check(claim, _truth(args.truth))
    print(format_block(claim, result))
    return _RANK.get(result["verdict"], 1)


def _cmd_check_batch(args) -> int:
    truth = _truth(args.truth)
    claims, results = [], []
    for line in Path(args.path).read_text(encoding="utf-8").splitlines():
        line = line.strip()
        if not line:
            continue
        c = _load_claim(line)
        claims.append(c)
        results.append(check(c, truth))
    counts = {v: sum(1 for r in results if r["verdict"] == v) for v in ("PASS", "WARN", "REFUSE")}
    print(f"verity check-batch — {len(results)} claim(s): "
          f"{counts['PASS']} PASS · {counts['WARN']} WARN · {counts['REFUSE']} REFUSE")
    for c, r in zip(claims, results):
        name = str(c.get("name") or c.get("text", "?"))[:56]
        top = r["issues"][0]["detail"] if r["issues"] else "clears the bar"
        print(f"  [{r['verdict']:6}] {name}  —  {top}")
    return _RANK.get(_worst(results), 1)


def main(argv=None) -> int:
    p = argparse.ArgumentParser(
        prog="verity",
        description="Check empirical result-claims for trustworthiness (REFUSE/WARN/PASS). "
                    "Exit code = worst verdict (0 PASS · 1 WARN · 2 REFUSE) — CI-gateable.",
    )
    sub = p.add_subparsers(dest="cmd", required=True)

    pc = sub.add_parser("check", help="check ONE claim (inline or from a file)")
    g = pc.add_mutually_exclusive_group(required=True)
    g.add_argument("--claim", metavar="JSON_OR_TEXT", help="the claim: a JSON object or plain text")
    g.add_argument("--claim-file", metavar="PATH", help="read the claim from a file")
    pc.add_argument("--truth", metavar="PATH", help="optional ground-truth YAML (thresholds + facts)")
    pc.set_defaults(func=_cmd_check)

    pb = sub.add_parser("check-batch", help="check a JSONL backlog; exit code = the worst verdict")
    pb.add_argument("path", metavar="CLAIMS.jsonl", help="one claim per line (JSON object or text)")
    pb.add_argument("--truth", metavar="PATH", help="optional ground-truth YAML")
    pb.set_defaults(func=_cmd_check_batch)

    args = p.parse_args(argv)
    return args.func(args)


if __name__ == "__main__":  # pragma: no cover
    sys.exit(main())
