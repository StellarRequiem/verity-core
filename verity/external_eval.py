"""External-validity harness — score the gate against REAL replication outcomes.

Unlike ``eval/harness.py`` (circular: cases authored against the gate's own rules), this scores
claims whose labels come from independent replications (the FORRT / DARPA-SCORE corpus; see
``eval/external/SOURCES.md``). It measures DISCRIMINATION: does the gate flag claims that FAILED to
replicate more than claims that HELD UP? A real, external, non-circular signal — and honestly modest,
because a statistics gate sees only the *disclosed statistics*; replication failure has causes it
cannot see (QRPs, fraud, context-sensitivity, publication bias).
"""
from __future__ import annotations

import json
from pathlib import Path

from .gate import check, load_truth

_ROOT = Path(__file__).resolve().parent.parent
_DEFAULT_DATA = _ROOT / "eval" / "external" / "score-replication.jsonl"
_DEFAULT_TRUTH = _ROOT / "eval" / "external" / "replication-truth.yaml"

# Label / metadata fields — NOT part of the claim the gate scores.
_NOT_CLAIM = {"replicated", "es_type_original", "discipline"}


def run(data_path=_DEFAULT_DATA, truth_path=_DEFAULT_TRUTH) -> dict:
    """Score every labelled claim and return the discrimination stats (no printing)."""
    truth = load_truth(truth_path)
    buckets = {True: {"n": 0, "flagged": 0}, False: {"n": 0, "flagged": 0}}
    for line in Path(data_path).read_text(encoding="utf-8").splitlines():
        line = line.strip()
        if not line:
            continue
        rec = json.loads(line)
        replicated = bool(rec.get("replicated"))
        claim = {k: v for k, v in rec.items() if k not in _NOT_CLAIM}
        if check(claim, truth)["verdict"] != "PASS":
            buckets[replicated]["flagged"] += 1
        buckets[replicated]["n"] += 1
    failed, repl = buckets[False], buckets[True]
    catch = failed["flagged"] / failed["n"] if failed["n"] else 0.0
    fp = repl["flagged"] / repl["n"] if repl["n"] else 0.0
    a, b = failed["flagged"], failed["n"] - failed["flagged"]
    c, d = repl["flagged"], repl["n"] - repl["flagged"]
    odds = (a * d) / (b * c) if (b * c) else float("inf")
    return {"n": failed["n"] + repl["n"], "n_failed": failed["n"], "n_replicated": repl["n"],
            "catch": catch, "false_alarm": fp, "separation": catch - fp, "odds_ratio": odds}


_BANNER = (
    "=" * 78 + "\n"
    "verity eval-external — REAL replication outcomes (external, NOT circular)\n"
    + "=" * 78 + "\n"
    "Labels come from independent high-powered replications (FORRT/SCORE, CC-BY 4.0; see\n"
    "eval/external/SOURCES.md) — NOT the gate's own rules. Measures whether the gate flags\n"
    "claims that FAILED to replicate more than ones that HELD UP. Honest bound: a stats gate\n"
    "sees only disclosed statistics, so it catches the under-powered / small-effect slice of\n"
    "failures — a modest, real signal, not an oracle.\n"
    + "=" * 78
)


def main(argv=None) -> int:
    import sys
    args = argv if argv is not None else sys.argv[1:]
    r = run(args[0] if args else _DEFAULT_DATA)
    print(_BANNER)
    print(f"  n = {r['n']}  ({r['n_failed']} failed · {r['n_replicated']} replicated)")
    print(f"  flag-rate on FAILED:     {r['catch']:.0%}")
    print(f"  flag-rate on REPLICATED: {r['false_alarm']:.0%}")
    print(f"  separation: {r['separation']:+.0%}    odds (failed vs replicated flagged): {r['odds_ratio']:.2f}x")
    ok = r["separation"] > 0 and r["odds_ratio"] > 1.0
    print("  -> verity flags real replication FAILURES more than survivors (external signal intact)."
          if ok else "  -> NO external discrimination — regression (see SOURCES.md).")
    return 0 if ok else 1


if __name__ == "__main__":  # pragma: no cover
    raise SystemExit(main())
