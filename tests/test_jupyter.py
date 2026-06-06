"""The Jupyter surface — gate the JSON claim(s) typed into a ``%%verity`` cell.

These tests exercise the IPython-free heart of the magic (``_parse_claims`` / ``verify_cell`` /
``render_cell``) so the whole suite runs WITHOUT IPython installed — which is exactly the
contract: ``import verity.jupyter`` must work in a plain interpreter, and the gate logic lives in
a function the magic merely calls. DETERMINISTIC by design: only structured JSON / JSONL is read
(never prose), and a malformed line / block is skipped — never raised. These pin all of it.
"""
from verity.jupyter import _parse_claims, render_cell, verify_cell

# A clean, honest result-claim — clears the default gate (small accuracy, real n, oos + leakage).
_CLEAN = (
    '{"name": "honest", "accuracy": 0.51, "sample_size": 300, '
    '"out_of_sample": true, "leakage_checked": true}'
)

# The launch hook in the flesh: a cell bragging a number that does NOT clear the bar
# (97% on 12 bets, no holdout) — a fabrication-class REFUSE.
_JUNK = '{"name": "too-good", "win_rate": 0.97, "sample_size": 12, "out_of_sample": false}'


def test_module_imports_without_ipython():
    """The whole point of the optional-import guard: this module loads with no IPython present."""
    import verity.jupyter as j

    # In this test env IPython is absent — the guard must have set the flag and provided no-op decos.
    assert j._HAVE_IPYTHON is False
    # The registrar exists and is callable; it must NOT have raised at import time.
    assert callable(j.load_ipython_extension)


def test_clean_single_object_cell_passes():
    results = verify_cell(_CLEAN)
    assert len(results) == 1
    assert results[0]["verdict"] == "PASS"
    assert results[0]["claim"]["name"] == "honest"
    assert results[0]["issues"] == []
    # the full verify() result is carried for rendering — multi-dimension shape, not just a verdict
    assert "dimensions" in results[0]["result"]
    assert results[0]["result"]["dimensions"]["empirical"]["verdict"] == "PASS"


def test_junk_claim_cell_refuses():
    results = verify_cell(_JUNK)
    assert len(results) == 1
    assert results[0]["verdict"] == "REFUSE"
    # the noise-floor sample size (12 < hard floor 30) is the fabrication-class reason
    assert any(i["severity"] == "CRITICAL" for i in results[0]["issues"])


def test_pretty_printed_multiline_object_is_one_claim():
    """A single claim pretty-printed across many lines parses as ONE claim, not many garbage lines."""
    cell = """{
    "name": "pretty",
    "accuracy": 0.51,
    "sample_size": 300,
    "out_of_sample": true,
    "leakage_checked": true
}"""
    results = verify_cell(cell)
    assert len(results) == 1
    assert results[0]["claim"]["name"] == "pretty"
    assert results[0]["verdict"] == "PASS"


def test_jsonl_multiple_claims_in_line_order():
    """JSONL: one claim per line, verified independently, in line order."""
    cell = (
        '{"name": "first", "accuracy": 0.51, "sample_size": 300, '
        '"out_of_sample": true, "leakage_checked": true}\n'
        '{"name": "second", "win_rate": 0.99, "sample_size": 10}\n'
    )
    results = verify_cell(cell)
    assert [r["claim"]["name"] for r in results] == ["first", "second"]
    assert results[0]["verdict"] == "PASS"
    assert results[1]["verdict"] == "REFUSE"          # 99% on n=10 — noise floor


def test_json_array_of_claims_yields_one_per_object():
    """A whole-cell JSON ARRAY is treated as a list of claims (one per object element)."""
    cell = """[
    {"name": "a", "accuracy": 0.51, "sample_size": 300, "out_of_sample": true, "leakage_checked": true},
    {"name": "b", "win_rate": 0.99, "sample_size": 8}
]"""
    results = verify_cell(cell)
    assert [r["claim"]["name"] for r in results] == ["a", "b"]
    assert results[0]["verdict"] == "PASS"
    assert results[1]["verdict"] == "REFUSE"


def test_malformed_jsonl_line_is_skipped_not_raised():
    """One broken JSONL line is skipped; a valid line in the same cell still verifies."""
    cell = (
        "{not valid json at all\n"
        '{"name": "ok", "accuracy": 0.51, "sample_size": 300, '
        '"out_of_sample": true, "leakage_checked": true}\n'
    )
    results = verify_cell(cell)                        # must NOT raise
    assert len(results) == 1                           # only the parseable line survives
    assert results[0]["claim"]["name"] == "ok"
    assert results[0]["verdict"] == "PASS"


def test_blank_lines_in_jsonl_are_ignored():
    """Blank separator lines between JSONL claims are skipped, not treated as empty claims."""
    cell = (
        '{"name": "x", "accuracy": 0.51, "sample_size": 300, '
        '"out_of_sample": true, "leakage_checked": true}\n'
        "\n"
        "   \n"
        '{"name": "y", "accuracy": 0.52, "sample_size": 400, '
        '"out_of_sample": true, "leakage_checked": true}\n'
    )
    results = verify_cell(cell)
    assert [r["claim"]["name"] for r in results] == ["x", "y"]


def test_empty_and_whitespace_cells_yield_no_claims():
    """An empty (or whitespace-only) cell claims nothing — no claim, no crash."""
    assert verify_cell("") == []
    assert verify_cell("   \n\t  \n") == []
    assert _parse_claims("") == []


def test_non_string_cell_is_inert():
    """A non-string cell body is inert (returns []), never a crash — can't take the gate down."""
    assert _parse_claims(None) == []
    assert _parse_claims(42) == []
    assert verify_cell(None) == []


def test_bare_scalar_and_array_of_scalars_are_not_claims():
    """A bare JSON scalar is not a claim; an array's non-object elements are skipped."""
    assert _parse_claims("42") == []                  # bare scalar — not a result-claim
    assert _parse_claims('"just a string"') == []
    assert _parse_claims("[1, 2, 3]") == []           # array of scalars — no objects to keep
    # an array MIXING objects and scalars keeps only the objects
    mixed = _parse_claims('[{"accuracy": 0.5, "sample_size": 100}, 7, "noise"]')
    assert len(mixed) == 1 and mixed[0]["sample_size"] == 100


def test_render_cell_emits_verified_block_with_verdict():
    """``render_cell`` produces the canonical VERIFIED block text — the magic just prints this."""
    out = render_cell(_JUNK)
    assert "VERIFIED" in out
    assert "Verdict: REFUSE" in out
    assert "Dimensions:" in out                        # the multi-dimension block, not the single one


def test_render_cell_on_empty_cell_is_explicit_not_blank():
    """An empty cell renders one explicit line — the notebook never shows a silent blank."""
    out = render_cell("")
    assert "no JSON claim" in out


def test_render_cell_renders_one_block_per_claim():
    """A JSONL cell of two claims renders two VERIFIED blocks (one per claim)."""
    cell = (
        '{"name": "first", "accuracy": 0.51, "sample_size": 300, '
        '"out_of_sample": true, "leakage_checked": true}\n'
        '{"name": "second", "win_rate": 0.99, "sample_size": 10}\n'
    )
    out = render_cell(cell)
    assert out.count("VERIFIED") == 2
