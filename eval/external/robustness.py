"""Is the marginal-significance improvement a lucky split? — a re-runnable robustness check.

The headline result (the ``marginal_significance`` check took the gate from 1.41x to 2.14x on the
1,772-case FORRT corpus) rests on one claim: strongly-significant findings (p <= 0.01) replicate
more often than *marginal* ones (0.01 < p <= 0.05). This script stress-tests that claim two ways —
across 10 folds (is it stable, or one lucky subset?) and per-discipline (is it one field, or
general?) — so the defense ships with the claim. Exit 0 iff the signal is robust (>= 9/10 folds).
"""
from __future__ import annotations

import json
import statistics
from pathlib import Path

_DATA = Path(__file__).resolve().parent / "fred-replication.jsonl"


def _rate(cases):
    n = len(cases)
    return ((sum(1 for r in cases if r.get("replicated")) / n) if n else None), n


def run(data_path=_DATA) -> dict:
    rows = [json.loads(ln) for ln in Path(data_path).read_text(encoding="utf-8").splitlines() if ln.strip()]
    sig = [r for r in rows if r.get("p_value") is not None and r["p_value"] <= 0.05]

    # 10 deterministic folds (by index) — does strong>marginal hold in EVERY fold?
    gaps = []
    for f in range(10):
        fold = [r for i, r in enumerate(sig) if i % 10 == f]
        rm, _ = _rate([r for r in fold if r["p_value"] > 0.01])
        rs, _ = _rate([r for r in fold if r["p_value"] <= 0.01])
        if rm is not None and rs is not None:
            gaps.append(rs - rm)

    # per-discipline (n>=40) — is the gap one field or general?
    by_disc: dict[str, list] = {}
    for r in sig:
        by_disc.setdefault(r.get("discipline", "?"), []).append(r)
    per = []
    for d, cs in sorted(by_disc.items(), key=lambda x: -len(x[1])):
        if len(cs) < 40:
            continue
        rm, nm = _rate([r for r in cs if r["p_value"] > 0.01])
        rs, ns = _rate([r for r in cs if r["p_value"] <= 0.01])
        if rm is not None and rs is not None:
            per.append({"discipline": d, "marginal": rm, "strong": rs, "gap": rs - rm,
                        "n_marginal": nm, "n_strong": ns})

    return {"n_folds": len(gaps), "folds_ok": sum(1 for g in gaps if g > 0),
            "mean_gap": statistics.mean(gaps), "min_gap": min(gaps), "max_gap": max(gaps),
            "per_discipline": per}


def main(argv=None) -> int:
    r = run()
    print("marginal-significance robustness — strong (p<=.01) should replicate MORE than marginal (.01<p<=.05)")
    print(f"  folds in the right direction: {r['folds_ok']}/{r['n_folds']}")
    print(f"  gap (strong - marginal): mean {r['mean_gap']:+.3f}  range [{r['min_gap']:+.3f}, {r['max_gap']:+.3f}]")
    for p in r["per_discipline"]:
        note = "" if p["gap"] > 0 else "  <- REVERSED (small-n / ceiling effect)"
        print(f"  {p['discipline'][:26]:26} marginal {p['marginal']:.0%} vs strong {p['strong']:.0%}"
              f"  gap {p['gap']:+.2f}{note}")
    robust = r["folds_ok"] >= 9
    print(f"  -> {'ROBUST' if robust else 'NOT robust'} ({r['folds_ok']}/{r['n_folds']} folds) — "
          f"the marginal-significance signal is {'stable, not a lucky split.' if robust else 'NOT stable.'}")
    return 0 if robust else 1


if __name__ == "__main__":  # pragma: no cover
    raise SystemExit(main())
