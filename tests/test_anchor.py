"""Tests for the live Reality Anchor (verity.anchor).

Uses stub sources so the cross-referential policy, the verdict mapping, and the
tamper-evident ledger are tested without needing git/DB I/O. One stub returns canned
facts (the 'live ground truth'); the anchor's job is to reconcile + corroborate + log.
"""
import json

from verity.anchor import anchor, Source, PASS, REFUSE, UNVERIFIABLE
from verity.audit import AuditChain


class StubSource(Source):
    """A source that returns canned facts (or None = silent / cannot adjudicate)."""

    def __init__(self, id: str, facts: dict | None):
        self.id = id
        self._facts = facts

    def fetch(self, claim, proof):
        return dict(self._facts) if self._facts is not None else None


class BoomSource(Source):
    id = "boom"

    def fetch(self, claim, proof):
        raise RuntimeError("source is down")


CLAIM = {"name": "x", "version": "0.1.0"}


def test_two_independent_sources_agree_pass(tmp_path):
    led = AuditChain(tmp_path / "l.jsonl")
    r = anchor(CLAIM, [StubSource("a", {"version": "0.1.0"}),
                       StubSource("b", {"version": "0.1.0"})],
               ledger=led, min_sources=2)
    assert r.verdict == PASS
    assert r.n_corroborating == 2
    assert led.verify()[0]            # ledger intact, one entry appended


def test_contradiction_is_refuse_even_with_a_supporter():
    # 'a' supports, 'b' contradicts -> CONTRADICTION beats SUPPORT -> REFUSE.
    r = anchor(CLAIM, [StubSource("a", {"version": "0.1.0"}),
                       StubSource("b", {"version": "9.9.9"})], min_sources=2)
    assert r.verdict == REFUSE


def test_under_corroborated_is_unverifiable():
    # grounded, but by 1 source when 2 are required -> not believed, not false.
    r = anchor(CLAIM, [StubSource("a", {"version": "0.1.0"})], min_sources=2)
    assert r.verdict == UNVERIFIABLE


def test_no_source_can_adjudicate_is_unverifiable():
    r = anchor(CLAIM, [StubSource("a", None), StubSource("b", None)], min_sources=1)
    assert r.verdict == UNVERIFIABLE


def test_a_crashing_source_is_silent_never_a_verdict():
    # A boom source must not raise and must not force a verdict; the good source still grounds.
    r = anchor(CLAIM, [StubSource("a", {"version": "0.1.0"}), BoomSource()], min_sources=1)
    assert r.verdict == PASS
    assert r.fetched["boom"] is None


def test_ledger_is_tamper_evident(tmp_path):
    led = AuditChain(tmp_path / "l.jsonl")
    anchor(CLAIM, [StubSource("a", {"version": "0.1.0"})], ledger=led, min_sources=1)
    assert led.verify()[0]
    # tamper with the recorded verdict, then the hash-chain must catch it
    rec = json.loads(led.path.read_text().splitlines()[0])
    rec["event_data"]["verdict"] = "PASS_FORGED"
    led.path.write_text(json.dumps(rec) + "\n")
    assert not led.verify()[0]


def test_provenance_records_where_each_fact_is_from():
    """The live tool shows its work: a real git source + the where-from + stance trail."""
    from pathlib import Path
    from verity.anchor import GitSource, format_anchor_block

    repo = Path(__file__).resolve().parent.parent
    claim = {"name": "v", "version": "0.1.0",
             "proof": [{"source": "git", "path": "verity/__init__.py", "ref": "HEAD",
                        "field": "version", "pattern": r'__version__ = "([^"]+)"'}]}
    r = anchor(claim, [GitSource(repo, id="git")], min_sources=1)
    assert r.verdict == PASS
    pv = next(p for p in r.provenance if p["field"] == "version")
    assert pv["source_id"] == "git" and pv["stance"] == "support"
    assert pv["value"] == "0.1.0" and "verity/__init__.py" in pv["locator"]
    assert "Provenance" in format_anchor_block(claim, r)


def test_compiler_source_grounds_code_claims_polyglot(tmp_path):
    """The polyglot oracle: ground a 'does this compile' claim against a REAL compiler."""
    import shutil
    import pytest
    from verity.anchor import CompilerSource

    cc = shutil.which("clang") or shutil.which("gcc")
    if not cc:
        pytest.skip("no C compiler available")
    good = tmp_path / "good.c"; good.write_text("int main(void){return 0;}\n")
    bad = tmp_path / "bad.c"; bad.write_text("int main(void){return\n")  # unterminated -> syntax error
    cs = CompilerSource(id="clang")

    ok = anchor({"name": "good", "compiles": True,
                 "proof": [{"source": "compile", "field": "compiles",
                            "cmd": [cc, "-fsyntax-only", str(good)]}]}, [cs], min_sources=1)
    assert ok.verdict == PASS                      # the compiler agrees it compiles

    no = anchor({"name": "bad", "compiles": True,
                 "proof": [{"source": "compile", "field": "compiles",
                            "cmd": [cc, "-fsyntax-only", str(bad)]}]}, [cs], min_sources=1)
    assert no.verdict == REFUSE                    # the compiler says it does NOT — claim refuted
