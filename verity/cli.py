"""verity CLI — verify empirical result-claims from the shell or CI.

    verity check       --claim '{"accuracy":0.92,"sample_size":40}'  [--truth truth.yaml]
    verity check       --claim-file claim.json                       [--truth truth.yaml]
    verity check-batch claims.jsonl                                  [--truth truth.yaml]
    verity verify      --claim '{...}' [--evidence '{...}'] [--prior '{...}']
                       [--sources a,b] [--truth truth.yaml]          # all dimensions at once
    verity eval        [eval/benchmark.jsonl]                        # run the regression harness

A *claim* is a JSON object describing a measured result (accuracy/win_rate, sample_size,
out_of_sample, leakage_checked, optionally z / n_comparisons / base_rate …) or plain text.
The gate scores it — structural hygiene + statistical rigor + ground-truth facts — and returns
REFUSE / WARN / PASS. ``verify`` additionally reconciles the claim against supplied ``evidence``
(recomputed values) and a ``prior`` assertion (contradiction check). The **exit code is the worst
verdict**, so every subcommand gates CI exactly like a linter: `0` PASS · `1` WARN · `2` REFUSE.
A PASS means *trustworthy*, not *profitable*.
"""
from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

from . import eval as _eval
from . import external_eval as _external_eval
from .gate import check, format_block, format_verify_block, load_truth
from .verify import verify

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


def _load_json_arg(s: str | None):
    """Parse an inline-JSON-or-``@file`` argument into a dict/list (or None if not given).

    Accepts ``{"a":1}`` / ``[1,2]`` directly, or ``@path/to/file.json`` to read+parse a file.
    Raises ``ValueError`` with a clear message on malformed JSON so the CLI fails loudly rather
    than silently mis-parsing (a verifier that quietly drops your evidence is worse than useless).
    """
    if s is None:
        return None
    s = s.strip()
    if s.startswith("@"):
        s = Path(s[1:]).read_text(encoding="utf-8").strip()
    try:
        return json.loads(s)
    except ValueError as e:
        raise ValueError(f"could not parse JSON argument: {e}") from e


def _load_sources(s: str | None) -> list | None:
    """``--sources`` accepts a JSON array (``["a","b"]`` / ``@file``) OR a bare comma list (``a,b``)."""
    if s is None:
        return None
    s = s.strip()
    if s.startswith("[") or s.startswith("@"):
        val = _load_json_arg(s)
        if not isinstance(val, list):
            raise ValueError("--sources JSON must be an array")
        return val
    return [part.strip() for part in s.split(",") if part.strip()]


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


def _cmd_verify(args) -> int:
    """The agent-native entrypoint: empirical hygiene + evidence-match + consistency-vs-prior."""
    claim = _load_claim(
        Path(args.claim_file).read_text(encoding="utf-8") if args.claim_file else args.claim)
    evidence = _load_json_arg(args.evidence)
    prior = _load_json_arg(args.prior)
    sources = _load_sources(args.sources)
    res = verify(claim, evidence=evidence, prior=prior, sources=sources, truth=_truth(args.truth))
    print(format_verify_block(claim, res))
    return _RANK.get(res["verdict"], 1)


def _cmd_eval(args) -> int:
    """Run the self-authored regression harness (prints the honesty banner + per-dimension table)."""
    return _eval.main([args.path] if args.path else [])


def _cmd_eval_external(args) -> int:
    """Score the gate against REAL replication outcomes (external, non-circular)."""
    return _external_eval.main([args.path] if args.path else [])


def main(argv=None) -> int:
    p = argparse.ArgumentParser(
        prog="verity",
        description="Verify empirical result-claims for trustworthiness (REFUSE/WARN/PASS). "
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

    pv = sub.add_parser("verify", help="verify a claim across ALL dimensions (empirical + evidence "
                                       "+ consistency) — the recommended agent entrypoint")
    gv = pv.add_mutually_exclusive_group(required=True)
    gv.add_argument("--claim", metavar="JSON_OR_TEXT", help="the claim: a JSON object or plain text")
    gv.add_argument("--claim-file", metavar="PATH", help="read the claim from a file")
    pv.add_argument("--evidence", metavar="JSON|@FILE",
                    help="recomputed ground-truth values to reconcile against (JSON object or @path)")
    pv.add_argument("--prior", metavar="JSON|@FILE",
                    help="a previously-asserted claim to check for contradiction (JSON object or @path)")
    pv.add_argument("--sources", metavar="JSON|a,b,c",
                    help="source identifiers: a JSON array, @path, or a bare comma-separated list")
    pv.add_argument("--truth", metavar="PATH", help="optional ground-truth YAML (thresholds + facts)")
    pv.set_defaults(func=_cmd_verify)

    pe = sub.add_parser("eval", help="run the self-authored known-failure-mode regression harness "
                                     "(circular by construction — prints an honesty banner)")
    pe.add_argument("path", nargs="?", metavar="BENCHMARK.jsonl",
                    help="optional benchmark path (defaults to the shipped eval/benchmark.jsonl)")
    pe.set_defaults(func=_cmd_eval)

    px = sub.add_parser("eval-external", help="score the gate against REAL replication outcomes "
                                              "(external / non-circular; FORRT-SCORE, CC-BY 4.0)")
    px.add_argument("path", nargs="?", metavar="BENCHMARK.jsonl",
                    help="optional path (defaults to eval/external/score-replication.jsonl)")
    px.set_defaults(func=_cmd_eval_external)

    args = p.parse_args(argv)
    return args.func(args)


if __name__ == "__main__":  # pragma: no cover
    sys.exit(main())
