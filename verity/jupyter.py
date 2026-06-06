"""verity.jupyter — the notebook surface: a ``%%verity`` cell magic.

The launch hook for the notebook: *you typed a result-claim into a cell — did
anyone gate it?* A data scientist pasting ``{"accuracy": 0.97, ...}`` into a
notebook gets the SAME Reality Anchor an agent gets over MCP, inline, the moment
the cell runs::

    %load_ext verity.jupyter

    %%verity
    {"name": "btc-momentum", "win_rate": 0.97, "sample_size": 12, "out_of_sample": false}

The cell body is read as a JSON claim (a single object — even pretty-printed
across many lines), a JSON array of claims, or JSONL (one claim per line). Each
claim is run through ``verity.verify`` and its multi-dimension VERIFIED block is
printed back into the notebook.

DETERMINISTIC by construction — and that determinism is the point of trust:

  * the cell body is parsed ONLY as structured JSON / JSONL, NEVER fuzzy-read out
    of prose ("we hit 97%"). Guessing a number out of a sentence is exactly the
    unreliable NLP this project refuses to do; a claim has to be written as JSON,
    on purpose, to be checked. (Same stance as ``verity.markdown``.)
  * a line / block that does not ``json.loads`` is SKIPPED, never raised — one
    malformed line must not take the magic (or the surrounding notebook run) down.
    Only a parsed JSON *object* is a result-claim (a bare array element that is a
    scalar is skipped); an array OF objects yields one claim per object.

IPython is an OPTIONAL dependency — guarded with try/except so this module
*imports cleanly without IPython installed*. The check logic lives in the plain,
IPython-free ``verify_cell`` function (deterministic, no I/O, unit-testable on
its own); the magic is a thin shell that calls it and renders the result. The
registrar ``load_ipython_extension`` raises a clear ``RuntimeError`` ONLY if the
extension is actually loaded without IPython present — never at import time.

``truth`` is a *resolved* truth dict or ``None`` (``verify`` loads the packaged
default) — this module does no truth I/O of its own, mirroring ``verify``'s
no-I/O contract.
"""
from __future__ import annotations

import json

from .gate import format_verify_block
from .verify import verify

# IPython is OPTIONAL: guard the import so `import verity.jupyter` works in a plain interpreter,
# in CI, and in the test suite — none of which have IPython. The magic class and the registrar
# only need IPython when actually USED inside a live kernel, and they raise a clear message then.
try:                                            # pragma: no cover - import-guard, exercised by env
    from IPython.core.magic import Magics, cell_magic, magics_class
    _HAVE_IPYTHON = True
except ImportError:                             # the module still imports + verify_cell still runs
    Magics = object                             # a base so the class body below is always def"able"
    _HAVE_IPYTHON = False

    def magics_class(cls):                       # no-op stand-ins so the decorated class still builds
        return cls

    def cell_magic(_fn=None, *a, **k):           # accept bare or called form, return an identity deco
        def deco(fn):
            return fn
        return deco(_fn) if callable(_fn) else deco


def _parse_claims(cell_text: str) -> list[dict]:
    """Parse a notebook cell body into a list of claim dicts. DETERMINISTIC; never raises.

    Three accepted shapes, tried in order — every one structured JSON, never prose:

      1. the WHOLE cell ``json.loads`` to an OBJECT          → exactly that one claim
         (covers a single pretty-printed claim spanning many lines);
      2. the WHOLE cell ``json.loads`` to an ARRAY           → one claim per object element
         (non-object elements — bare scalars / nested arrays — are skipped);
      3. otherwise treat the cell as JSONL                   → parse each non-blank line; keep
         the parsed OBJECTs in line order; a blank line or a line that does not parse is
         skipped (never raised, mirroring ``verity.markdown``'s skip-don't-crash discipline).

    A non-string input yields ``[]`` rather than crashing (an input that can take the parser
    down is a way to bypass the gate).
    """
    if not isinstance(cell_text, str):
        return []
    stripped = cell_text.strip()
    if not stripped:
        return []
    # (1)/(2): the whole body as one JSON value — object → single claim, array → many.
    try:
        whole = json.loads(stripped)
    except ValueError:
        whole = None                            # not a single JSON value — fall through to JSONL
    else:
        if isinstance(whole, dict):
            return [whole]
        if isinstance(whole, list):
            return [x for x in whole if isinstance(x, dict)]  # array OF claims; skip non-objects
        return []                               # a bare scalar (number/string/bool/null) is not a claim
    # (3): JSONL — one claim per line; skip blanks and unparseable lines, never raise.
    claims: list[dict] = []
    for line in stripped.splitlines():
        line = line.strip()
        if not line:
            continue
        try:
            obj = json.loads(line)
        except ValueError:
            continue                            # a malformed line is skipped, not fatal
        if isinstance(obj, dict):               # only an object is a result-claim
            claims.append(obj)
    return claims


def verify_cell(cell_text: str, truth: dict | None = None) -> list[dict]:
    """Parse a notebook cell body into claims and verify EACH through ``verity.verify``.

    This is the plain, IPython-free heart of the ``%%verity`` magic — pure, deterministic, no I/O —
    so it is unit-testable WITHOUT IPython installed. Returns one entry per parsed claim, in order::

        [{"claim":   <the parsed claim dict>,
          "verdict": "REFUSE"|"WARN"|"PASS",      # mirrors verify()'s top-level verdict (convenience)
          "issues":  [ ...the flattened issues from verify... ],
          "result":  { ...the FULL verify() dict (verdict + dimensions + issues)... }}]

    ``verdict`` / ``issues`` mirror ``verify_markdown``'s shape (easy assertions); ``result`` carries
    the full multi-dimension verdict so the magic can render the canonical ``format_verify_block``.
    ``truth`` is a resolved truth dict or ``None`` — passed straight to ``verify`` (which loads the
    packaged default when None); this surface does no truth I/O. A cell with no JSON claim yields
    ``[]`` (nothing claimed → nothing to refuse); the CALLER decides what an empty result means.
    """
    out: list[dict] = []
    for claim in _parse_claims(cell_text):
        res = verify(claim, truth=truth)
        out.append({"claim": claim, "verdict": res["verdict"], "issues": res["issues"], "result": res})
    return out


def render_cell(cell_text: str, truth: dict | None = None) -> str:
    """Verify a cell body and render every claim's VERIFIED block as one printable string.

    The exact text the ``%%verity`` magic prints — factored out (and IPython-free) so it is
    testable on its own. Each claim's block comes from the canonical ``gate.format_verify_block``
    (one renderer, one vocabulary, shared with every other surface). An empty cell — or one with no
    JSON claim — renders a single explicit line so the notebook never shows a silent blank.
    """
    results = verify_cell(cell_text, truth=truth)
    if not results:
        return ("verity: no JSON claim found in this cell — write the claim as a JSON object "
                "(or JSONL, one per line) to gate it. Nothing claimed, nothing to verify.")
    return "\n\n".join(format_verify_block(r["claim"], r["result"]) for r in results)


@magics_class
class VerityMagics(Magics):
    """The ``%%verity`` cell magic — gate the JSON claim(s) in a notebook cell, inline.

    Registered via ``%load_ext verity.jupyter``. The whole cell body is the argument; its parsing
    and verification are delegated to the IPython-free ``verify_cell`` / ``render_cell`` helpers, so
    this class is a thin rendering shell with no gate logic of its own. (Defined unconditionally —
    when IPython is absent the decorators are no-ops and the class is simply never registered.)
    """

    @cell_magic("verity")
    def verity(self, line, cell):  # noqa: D401 - IPython magic signature (line args, cell body)
        """``%%verity`` — read the cell as a JSON claim / JSONL of claims and print each verdict.

        The magic-line (text after ``%%verity``) is reserved for future flags and currently ignored;
        the CELL BODY carries the claim(s). Prints the rendered VERIFIED block(s) and returns ``None``
        (a magic that printed its result should not also echo a value into the notebook's Out[...]).
        """
        print(render_cell(cell))


def load_ipython_extension(ipython) -> None:
    """Register ``%%verity`` with a running IPython — the ``%load_ext verity.jupyter`` entrypoint.

    Raises ``RuntimeError`` with a clear message ONLY if invoked without IPython actually present
    (the guarded optional import failed) — this can only happen if a caller invokes the registrar
    by hand in a non-IPython process; under a real ``%load_ext`` IPython is, by definition, loaded.
    Never raises at import time: the cost of a missing optional dependency is paid at USE, not at
    ``import verity.jupyter``.
    """
    if not _HAVE_IPYTHON:                        # pragma: no cover - needs an IPython-less invocation
        raise RuntimeError(
            "verity.jupyter requires IPython to register the %%verity magic, but IPython is not "
            "installed. Install it (pip install ipython) to use the notebook surface. The rest of "
            "verity — verify(), the CLI, the MCP gate — works without it."
        )
    ipython.register_magics(VerityMagics)
