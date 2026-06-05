"""The verity eval harness, as a runnable package.

The runner itself lives in :mod:`verity.eval` (so it ships inside the installed wheel and is
importable as ``from verity import eval``). This package is a thin, repo-local entrypoint so the
documented ``python -m eval.harness`` invocation works from a checkout, and so the benchmark file
(``eval/benchmark.jsonl``) sits next to its runner. ``run`` / ``main`` / ``load_cases`` are
re-exported verbatim — there is exactly one implementation, never a divergent copy.
"""
from verity.eval import load_cases, main, run

__all__ = ["run", "main", "load_cases"]
