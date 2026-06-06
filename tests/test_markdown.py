"""The markdown surface — pull ```` ```json ```` claims out of a README and gate each one.

DETERMINISTIC by design: only fenced json blocks are read (never prose), a non-json fence is
ignored, and malformed json is skipped — never raised. These tests pin all four.
"""
from verity.markdown import extract_claims, verify_markdown

# A clean, honest result-claim — clears the default gate (small accuracy, real n, oos + leakage).
_CLEAN = """# My Model

We're proud of this one.

```json
{"name": "honest", "accuracy": 0.51, "sample_size": 300, "out_of_sample": true, "leakage_checked": true}
```
"""

# The launch hook in the flesh: a README that brags a number which does NOT clear the bar
# (99% on 8 samples, no holdout) — a fabrication-class REFUSE.
_JUNK = """# Amazing Model — 99% accurate!!

```json
{"name": "too-good", "accuracy": 0.99, "sample_size": 8, "out_of_sample": false}
```
"""


def test_clean_json_block_passes():
    results = verify_markdown(_CLEAN)
    assert len(results) == 1
    assert results[0]["verdict"] == "PASS"
    assert results[0]["claim"]["name"] == "honest"
    assert results[0]["issues"] == []


def test_junk_claim_block_refuses():
    results = verify_markdown(_JUNK)
    assert len(results) == 1
    assert results[0]["verdict"] == "REFUSE"
    # the noise-floor sample size is the fabrication-class reason
    assert any(i["severity"] == "CRITICAL" for i in results[0]["issues"])


def test_non_json_fence_is_ignored():
    """A plain (or other-language) code fence is documentation, not a claim — never extracted."""
    md = """Here is how you call it:

```python
result = check(claim, truth)   # {"accuracy": 0.99}  <- this is NOT a claim
```

And some shell:

```
verity check --claim '{"accuracy": 0.5}'
```
"""
    assert extract_claims(md) == []
    assert verify_markdown(md) == []


def test_malformed_json_is_skipped_not_raised():
    """A json fence whose body doesn't parse is skipped; a valid block in the same doc still reads."""
    md = """Broken block first:

```json
{"accuracy": 0.51, "sample_size": 300,   <- trailing comma, not valid JSON
```

Then a good one:

```json
{"accuracy": 0.51, "sample_size": 300, "out_of_sample": true, "leakage_checked": true}
```
"""
    claims = extract_claims(md)            # must NOT raise
    assert len(claims) == 1               # only the parseable block survives
    assert claims[0]["sample_size"] == 300
    assert verify_markdown(md)[0]["verdict"] == "PASS"


def test_extracts_multiple_blocks_in_document_order():
    md = """```json
{"name": "first", "accuracy": 0.51, "sample_size": 300, "out_of_sample": true, "leakage_checked": true}
```

```json
{"name": "second", "win_rate": 0.99, "sample_size": 10}
```
"""
    results = verify_markdown(md)
    assert [r["claim"]["name"] for r in results] == ["first", "second"]
    assert results[0]["verdict"] == "PASS"
    assert results[1]["verdict"] == "REFUSE"   # 99% on n=10 — noise floor


def test_non_object_json_and_non_string_input_are_skipped():
    """A bare JSON array/scalar is not a result-claim (claims are dicts); a non-str input is inert."""
    md = """```json
[1, 2, 3]
```

```json
42
```
"""
    assert extract_claims(md) == []
    assert extract_claims(None) == []         # never crashes on a non-string


def test_uppercase_and_spaced_json_info_string_still_matches():
    """The ``json`` language tag is matched case-insensitively with tolerant surrounding space."""
    md = """``` JSON
{"accuracy": 0.51, "sample_size": 300, "out_of_sample": true, "leakage_checked": true}
```
"""
    assert len(extract_claims(md)) == 1


def test_crlf_line_endings_are_handled():
    """A model card authored with Windows (CRLF) line endings still extracts — not a silent miss."""
    md = '```json\r\n{"accuracy": 0.51, "sample_size": 300}\r\n```\r\n'
    claims = extract_claims(md)
    assert len(claims) == 1 and claims[0]["sample_size"] == 300
