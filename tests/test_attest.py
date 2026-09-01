"""Portable provenance: what a stranger can check without trusting you.

The property under test is narrow. An attestation cannot show a claim is true — it can
only be pinned well enough that a lie survives exactly until one reader looks. So the
tests are mostly about what is *refused*: a format that accepts unverifiable provenance
is decoration, and would be worse than nothing because it would look like a guarantee.
"""
from __future__ import annotations

import json

import pytest

from verity.attest import (
    REQUIRED, build, check, check_batch, digest)

SHA = "a" * 40
REPO = "https://github.com/example/project"


def good(**over):
    base = dict(claim="accuracy reproduces", metric="accuracy", value=0.9,
                tolerance=0.001, proof="python3 examples/eval.py", repo=REPO,
                commit=SHA, produced_at="2026-09-01T00:00:00Z")
    base.update(over)
    return build(**base)


def reseal(att):
    """Re-seal after an edit — how an honest author revises, and how a forger would
    try to hide one."""
    att = dict(att)
    att["digest"] = digest(att)
    return att


# ------------------------------------------------------------------ accepts

def test_a_fully_pinned_claim_is_checkable():
    r = check(good())
    assert r.ok and not r.reasons


def test_checking_needs_nothing_but_the_object():
    """No network, no credentials, no interpreter — the whole point of the layer."""
    att = json.loads(json.dumps(good()))
    assert check(att).ok


def test_the_digest_covers_every_field():
    a = good()
    assert digest(a) == a["digest"]
    assert digest(dict(a, value=0.91)) != a["digest"]


# ------------------------------------------------------------------ refuses

@pytest.mark.parametrize("field", REQUIRED)
def test_every_required_field_is_required(field):
    a = reseal({k: v for k, v in good().items() if k != field})
    r = check(a)
    assert not r.ok and any(field in x for x in r.reasons)


def test_a_branch_is_refused_as_provenance():
    """A claim pinned to a branch is pinned to nothing — the branch can move under
    the reader after they check it."""
    r = check(reseal(dict(good(), commit="main")))
    assert not r.ok and any("moving reference" in x for x in r.reasons)


def test_a_short_sha_is_refused():
    r = check(reseal(dict(good(), commit="a1b2c3d")))
    assert not r.ok


def test_a_tag_is_refused():
    r = check(reseal(dict(good(), commit="v1.2.3")))
    assert not r.ok


def test_a_local_path_repo_is_refused():
    r = check(reseal(dict(good(), repo="/Users/someone/project")))
    assert not r.ok and any("unreachable" in x for x in r.reasons)


def test_a_proof_naming_an_absolute_path_is_refused():
    r = check(reseal(dict(good(), proof="python3 /Users/someone/project/eval.py")))
    assert not r.ok and any("absolute local path" in x for x in r.reasons)


def test_a_proof_naming_a_home_path_is_refused():
    r = check(reseal(dict(good(), proof="python3 ~/project/eval.py")))
    assert not r.ok


def test_a_relative_proof_command_is_fine():
    assert check(good(proof="python3 examples/eval.py")).ok


def test_an_altered_record_is_caught():
    a = dict(good(), value=99.0)      # edited, digest NOT re-sealed
    r = check(a)
    assert not r.ok and any("altered after sealing" in x for x in r.reasons)


def test_a_missing_digest_is_refused():
    a = {k: v for k, v in good().items() if k != "digest"}
    r = check(a)
    assert not r.ok and any("nothing commits" in x for x in r.reasons)


def test_a_non_numeric_value_is_refused():
    r = check(reseal(dict(good(), value="about ninety percent")))
    assert not r.ok and any("not a number" in x for x in r.reasons)


def test_a_boolean_value_is_refused():
    """`True` is an int in Python and would silently pass a numeric check."""
    r = check(reseal(dict(good(), value=True)))
    assert not r.ok


def test_a_non_object_is_refused():
    assert not check(["not", "an", "object"]).ok


# ------------------------------------------------------------------ warns

def test_a_bare_python_invocation_warns():
    """Found the hard way. This repo's own example proof said `python`, passed in CI
    where setup-python provides it, and failed on a machine that has only `python3`."""
    r = check(good(proof="python examples/eval.py"))
    assert r.ok                                        # portable enough to check
    assert any("python3" in w for w in r.warnings)     # but it will fail for a reader


def test_python3_does_not_warn():
    assert not any("python3" in w for w in check(good()).warnings)


def test_a_missing_tolerance_warns_without_refusing():
    a = {k: v for k, v in good().items() if k != "tolerance"}
    r = check(reseal(a))
    assert r.ok and any("tolerance" in w for w in r.warnings)


def test_a_missing_metric_warns_without_refusing():
    a = {k: v for k, v in good().items() if k != "metric"}
    r = check(reseal(a))
    assert r.ok and any("metric" in w for w in r.warnings)


def test_the_explanation_disclaims_being_a_signature():
    """An unkeyed digest proves consistency, not authorship. Saying so in the output
    is the difference between a useful record and a false guarantee."""
    assert "not a signature" in check(good()).explain()


# ------------------------------------------------------------------ batch + cli

def test_batch_fails_if_any_member_fails():
    ok, reports = check_batch([good(), reseal(dict(good(), commit="main"))])
    assert not ok and [r.ok for _, r in reports] == [True, False]


def test_cli_accepts_a_jsonl_batch(tmp_path, capsys):
    from verity.cli import main
    p = tmp_path / "a.jsonl"
    p.write_text(json.dumps(good()) + "\n", encoding="utf-8")
    assert main(["attest", str(p)]) == 0
    assert "CHECKABLE" in capsys.readouterr().out


def test_cli_accepts_a_single_json_object(tmp_path, capsys):
    from verity.cli import main
    p = tmp_path / "a.json"
    p.write_text(json.dumps(good()), encoding="utf-8")
    assert main(["attest", str(p)]) == 0


def test_cli_fails_on_unverifiable_provenance(tmp_path, capsys):
    from verity.cli import main
    p = tmp_path / "a.jsonl"
    p.write_text(json.dumps(reseal(dict(good(), commit="main"))) + "\n", encoding="utf-8")
    assert main(["attest", str(p)]) == 1
    assert "GATE FAILED" in capsys.readouterr().out


def test_cli_json_output(tmp_path, capsys):
    from verity.cli import main
    p = tmp_path / "a.jsonl"
    p.write_text(json.dumps(good()) + "\n", encoding="utf-8")
    main(["attest", str(p), "--json"])
    d = json.loads(capsys.readouterr().out)
    assert d["ok"] and d["count"] == 1


def test_cli_rejects_empty_input(tmp_path, capsys):
    from verity.cli import main
    p = tmp_path / "a.jsonl"
    p.write_text("   \n", encoding="utf-8")
    assert main(["attest", str(p)]) == 2


def test_this_repos_own_attestation_is_checkable():
    """Dogfood. If the shipped example stops being checkable, this fails."""
    from pathlib import Path
    f = Path(__file__).resolve().parent.parent / "examples" / "attestations.jsonl"
    atts = [json.loads(l) for l in f.read_text().splitlines() if l.strip()]
    ok, _ = check_batch(atts)
    assert ok and atts
