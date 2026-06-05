"""``python -m eval.harness`` — the documented entrypoint for the regression harness.

Delegates to :mod:`verity.eval` (the single implementation). Lets the harness be run directly
from a repo checkout via ``python -m eval.harness`` while the shippable logic lives in the
installed package. ``run`` / ``main`` / ``load_cases`` are re-exported so importers can use either
module name interchangeably.
"""
import sys

from verity.eval import load_cases, main, run

__all__ = ["run", "main", "load_cases"]


if __name__ == "__main__":  # pragma: no cover - exercised via the CLI/`-m` path
    sys.exit(main())
