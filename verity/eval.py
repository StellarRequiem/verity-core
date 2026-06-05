"""verity.eval — the honest, self-authored regression harness for the gate.

=============================================================================
 BRUTAL HONESTY (read this before quoting any number this module prints).
=============================================================================
This harness measures EXACTLY ONE thing: does verity's gate catch a set of
KNOWN, HAND-CONSTRUCTED failure modes, and does it leave KNOWN-CLEAN claims
alone (the false-positive side). That is all.

It is NOT an external benchmark of real-world claim quality. Every case in
``eval/benchmark.jsonl`` is authored by us, against the rules the gate itself
implements, so this is a CIRCULAR benchmark by construction — the verifier is
graded against its own rules. A 100% catch rate here therefore means the rules
are *internally consistent and wired up*; it says NOTHING about whether the
rules are *sufficient*, whether they *generalize* to claims we didn't think of,
or whether a PASS is *profitable*. (Per the Measurable Work Standard: a circular
benchmark proves nothing on its own and must be labelled as such — it is, here.)

What it IS good for: a regression. If a future edit silently breaks a check or
makes the gate start flagging honest claims, ``catch_rate`` or
``false_positive_rate`` moves and ``run()`` returns a nonzero exit — so the
harness is itself CI-gateable.

Every case carries a ``label_source`` tag stating WHERE its expected verdict
comes from (``definitional`` = the rule's own threshold makes it true, and we
say so; ``statistical`` = a textbook stat fact; ``real-incident`` = mirrors an
actual logged Yggdrasil claim, cited). Honest provenance, not a borrowed label.

----------------------------------------------------------------------------
 Scoring (per dimension, then totals):
   * a "failure" case is one whose expected verdict != PASS;
   * a "clean"  case is one whose expected verdict == PASS (a negative control);
   * catch_rate          = caught_failures / expected_failures
       (caught = gate did NOT say PASS on a failure case);
   * false_positive_rate = clean_flagged   / clean_total
       (flagged = gate did NOT say PASS on a clean case — a false alarm);
   * checks_fired_correctly counts cases where every id in ``expect_checks``
     actually appeared in the gate's issues (the RIGHT rule fired, not merely
     the right verdict).
 A case is CONSISTENT iff its verdict matches the label AND every expect_check
 fired. ``run()`` returns exit 0 only if every *scored* case is consistent.

 The EVIDENCE and CONSISTENCY dimensions are exercised through ``verity.verify``
 (deterministic field reconciliation). If that module has not landed yet, those
 cases are reported as ``skipped`` rather than failed — the empirical/rigor
 cases score via ``gate.check`` directly and are always runnable. The harness
 auto-upgrades to full coverage the moment ``verify`` is importable.
=============================================================================
"""
from __future__ import annotations

import json
import sys
from pathlib import Path

from .gate import check, load_truth

# Resolve package + repo roots so default paths work regardless of CWD.
_PKG_ROOT = Path(__file__).resolve().parent          # .../verity
_REPO_ROOT = _PKG_ROOT.parent                        # repo root
_DEFAULT_BENCHMARK = _REPO_ROOT / "eval" / "benchmark.jsonl"
_DEFAULT_TRUTH = _PKG_ROOT / "truth.yaml"            # packaged default pack
_TRUTHS_DIR = _REPO_ROOT / "truths"                 # named domain packs

# Dimensions that need verity.verify (field reconciliation); empirical/rigor don't.
_VERIFY_DIMENSIONS = frozenset({"evidence", "consistency"})

# ── verity.verify is an optional sibling (built in parallel). Detect, don't require.
try:  # pragma: no cover - import-time branch, both arms exercised by tests via _verify_available
    from .verify import verify as _verify  # type: ignore
    _HAS_VERIFY = True
except Exception:  # ModuleNotFoundError today; any import error => fall back to gate-only
    _verify = None  # type: ignore
    _HAS_VERIFY = False


def verify_available() -> bool:
    """True iff verity.verify is importable (so evidence/consistency cases can run)."""
    return _HAS_VERIFY


def _resolve_truth(pack: str | None) -> dict:
    """Load a named truth pack from truths/, or the packaged default when pack is falsy."""
    if not pack:
        return load_truth(_DEFAULT_TRUTH)
    p = Path(pack)
    if not p.is_absolute() and not p.exists():
        p = _TRUTHS_DIR / pack          # bare name like "trading.yaml" -> truths/trading.yaml
    return load_truth(p)


def load_cases(cases_path: str | Path = _DEFAULT_BENCHMARK) -> list[dict]:
    """Parse the JSONL benchmark. Blank lines and any object whose ``id`` starts
    with ``_`` (metadata, e.g. the honesty header) are skipped — only real cases
    are returned."""
    path = Path(cases_path)
    cases: list[dict] = []
    for lineno, raw in enumerate(path.read_text(encoding="utf-8").splitlines(), 1):
        line = raw.strip()
        if not line:
            continue
        try:
            obj = json.loads(line)
        except json.JSONDecodeError as e:
            raise ValueError(f"{path}:{lineno}: invalid JSON — {e}") from e
        if not isinstance(obj, dict):
            raise ValueError(f"{path}:{lineno}: each line must be a JSON object")
        if str(obj.get("id", "")).startswith("_"):
            continue                    # metadata line (honesty header etc.)
        cases.append(obj)
    return cases


def _score_case(case: dict) -> dict:
    """Run one case through the gate (or verify) and return a per-case result dict.

    Result keys: id, dimension, label, got (verdict or None if skipped),
    skipped(bool), match(bool), checks_fired(bool), missing_checks(list),
    fired(sorted list of check ids), is_failure(bool), is_clean(bool).
    """
    dim = case.get("dimension", "empirical")
    label = case["verdict"]
    claim = case["claim"]
    truth = _resolve_truth(case.get("truth_pack"))
    needs_verify = dim in _VERIFY_DIMENSIONS or case.get("evidence") is not None \
        or case.get("prior") is not None

    base = {
        "id": case.get("id", "?"),
        "dimension": dim,
        "label": label,
        "is_failure": label != "PASS",
        "is_clean": label == "PASS",
    }

    # A case that needs field reconciliation but verify hasn't landed -> skipped, not failed.
    if needs_verify and not _HAS_VERIFY:
        return {**base, "got": None, "skipped": True, "match": False,
                "checks_fired": False, "missing_checks": list(case.get("expect_checks", [])),
                "fired": []}

    if needs_verify:
        res = _verify(claim, evidence=case.get("evidence"), prior=case.get("prior"),
                      sources=case.get("sources"), truth=truth)
    else:
        res = check(claim, truth)

    fired = sorted({i.get("check") for i in res["issues"] if i.get("check") is not None})
    expect = list(case.get("expect_checks", []))
    missing = [c for c in expect if c not in fired]
    return {
        **base,
        "got": res["verdict"],
        "skipped": False,
        "match": res["verdict"] == label,
        "checks_fired": not missing,
        "missing_checks": missing,
        "fired": fired,
    }


def run(cases_path: str | Path = _DEFAULT_BENCHMARK) -> dict:
    """Score the whole benchmark. Returns a dict::

        {<dimension>: {"n", "expected_failures", "caught_failures",
                       "clean_total", "clean_flagged",
                       "catch_rate", "false_positive_rate",
                       "checks_fired_correctly"},
         ...,
         "_totals": {<same shape, summed>},
         "_cases": [<per-case result dicts>],
         "_mismatches": [<case results that failed to match or whose checks didn't fire>],
         "_skipped": [<ids skipped because verify is unavailable>],
         "_verify_available": bool,
         "_exit": 0|1}

    Exit is 0 iff every SCORED (non-skipped) case is consistent — verdict matches
    its label AND every expect_check fired. Skipped cases never fail the run (they
    are not scored), but they are surfaced in ``_skipped`` and the printed table.
    """
    cases = load_cases(cases_path)
    per_case = [_score_case(c) for c in cases]

    dims: dict[str, dict] = {}
    for r in per_case:
        d = dims.setdefault(r["dimension"], {
            "n": 0, "expected_failures": 0, "caught_failures": 0,
            "clean_total": 0, "clean_flagged": 0, "checks_fired_correctly": 0,
            "skipped": 0,
        })
        d["n"] += 1
        if r["skipped"]:
            d["skipped"] += 1
            continue
        if r["is_failure"]:
            d["expected_failures"] += 1
            if r["got"] != "PASS":
                d["caught_failures"] += 1
        if r["is_clean"]:
            d["clean_total"] += 1
            if r["got"] != "PASS":
                d["clean_flagged"] += 1
        if r["checks_fired"]:
            d["checks_fired_correctly"] += 1

    def _rates(d: dict) -> dict:
        ef, ct = d["expected_failures"], d["clean_total"]
        return {
            **d,
            "catch_rate": (d["caught_failures"] / ef) if ef else None,
            "false_positive_rate": (d["clean_flagged"] / ct) if ct else None,
        }

    out: dict = {dim: _rates(d) for dim, d in sorted(dims.items())}

    totals = {"n": 0, "expected_failures": 0, "caught_failures": 0,
              "clean_total": 0, "clean_flagged": 0, "checks_fired_correctly": 0, "skipped": 0}
    for d in dims.values():
        for k in totals:
            totals[k] += d[k]
    out["_totals"] = _rates(totals)

    mismatches = [r for r in per_case
                  if not r["skipped"] and (not r["match"] or not r["checks_fired"])]
    out["_cases"] = per_case
    out["_mismatches"] = mismatches
    out["_skipped"] = [r["id"] for r in per_case if r["skipped"]]
    out["_verify_available"] = _HAS_VERIFY
    out["_exit"] = 0 if not mismatches else 1
    return out


# ── honesty banner (printed verbatim by main(); kept here so it ships with the code) ──
_BANNER = (
    "=" * 78 + "\n"
    "verity eval — KNOWN-FAILURE-MODE REGRESSION (not an external benchmark)\n"
    + "=" * 78 + "\n"
    "This scores whether the gate catches HAND-CONSTRUCTED failure modes and leaves\n"
    "KNOWN-CLEAN claims alone. Every case is self-authored against the gate's own\n"
    "rules, so this is a CIRCULAR benchmark by construction. 100% here means the\n"
    "rules are internally consistent and wired — NOT that they are sufficient, NOT\n"
    "that they generalize, NOT that a PASS is profitable. Labels are provenance-\n"
    "tagged (definitional | statistical | real-incident).\n"
    + "=" * 78
)


def _fmt_rate(r) -> str:
    return "  n/a" if r is None else f"{r:5.0%}"


def main(argv: list[str] | None = None) -> int:
    """Print the honesty banner + per-dimension table, then exit 0 iff fully consistent."""
    argv = sys.argv[1:] if argv is None else argv
    cases_path = argv[0] if argv else _DEFAULT_BENCHMARK
    res = run(cases_path)

    print(_BANNER)
    if not res["_verify_available"]:
        print("NOTE: verity.verify is not importable — evidence/consistency cases are SKIPPED\n"
              "      (empirical/rigor scored via gate.check). They run once verify.py lands.")
    print(f"{'dimension':<14}{'n':>4}{'catch':>8}{'FP-rate':>9}{'checks-ok':>11}{'skipped':>9}")
    print("-" * 78)
    for dim in sorted(k for k in res if not k.startswith("_")):
        d = res[dim]
        print(f"{dim:<14}{d['n']:>4}{_fmt_rate(d['catch_rate']):>8}"
              f"{_fmt_rate(d['false_positive_rate']):>9}"
              f"{d['checks_fired_correctly']:>11}{d['skipped']:>9}")
    t = res["_totals"]
    print("-" * 78)
    print(f"{'TOTAL':<14}{t['n']:>4}{_fmt_rate(t['catch_rate']):>8}"
          f"{_fmt_rate(t['false_positive_rate']):>9}"
          f"{t['checks_fired_correctly']:>11}{t['skipped']:>9}")

    if res["_mismatches"]:
        print("\nMISMATCHES (expected vs got / missing checks):")
        for m in res["_mismatches"]:
            why = []
            if not m["match"]:
                why.append(f"verdict {m['label']} != {m['got']}")
            if not m["checks_fired"]:
                why.append(f"missing checks {m['missing_checks']} (fired {m['fired']})")
            print(f"  [{m['id']}] " + "; ".join(why))
    else:
        scored = t["n"] - t["skipped"]
        print(f"\nAll {scored} scored case(s) consistent (verdict + expected checks). "
              "Regression intact.")

    return res["_exit"]


if __name__ == "__main__":  # pragma: no cover
    sys.exit(main())
