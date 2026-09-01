"""Counting sources rather than voices, and a stop signal that actually stops.

Two rules have lived in prose and been enforced by memory: corroboration needs
independent sources, and a stop signal must be able to end a pursuit rather than
annotate it. Both are cheap to violate by accident — asking one model twice feels like
agreement, and an advisory ALERT is easier to ship than a real veto. These tests are
where those rules stop being remembered.
"""
from __future__ import annotations

import pytest

from verity.quorum import (
    HALT_AT, Assessment, Kind, Signal, Source, State, assess, independent, revive)

CLAUDE_A = Source("claude-a", Kind.MODEL, model="claude-opus-5")
CLAUDE_B = Source("claude-b", Kind.MODEL, model="claude-opus-5")
CLAUDE_C = Source("claude-c", Kind.MODEL, model="claude-opus-5")
GROK = Source("grok-1", Kind.MODEL, model="grok-4")
HUMAN = Source("alex", Kind.HUMAN)
TOOL = Source("pytest", Kind.TOOL)
EXTERNAL = Source("nvd", Kind.EXTERNAL)


# ------------------------------------------------------------- independence

def test_two_instances_of_one_model_are_one_source():
    """The gate. This is the rule that has always been enforced by memory."""
    n, groups = independent([CLAUDE_A, CLAUDE_B])
    assert n == 1
    assert sorted(groups["model:claude-opus-5"]) == ["claude-a", "claude-b"]


def test_ten_instances_of_one_model_are_still_one_source():
    fleet = [Source(f"c{i}", Kind.MODEL, model="claude-opus-5") for i in range(10)]
    assert independent(fleet)[0] == 1


def test_different_models_are_different_sources():
    assert independent([CLAUDE_A, GROK])[0] == 2


def test_a_model_and_a_human_are_two_sources():
    assert independent([CLAUDE_A, HUMAN])[0] == 2


def test_two_tools_are_two_sources():
    """Two independent measurements genuinely are two measurements — collapsing
    them the way model instances collapse would understate real evidence."""
    assert independent([TOOL, Source("semgrep", Kind.TOOL)])[0] == 2


def test_two_humans_are_two_sources():
    assert independent([HUMAN, Source("sam", Kind.HUMAN)])[0] == 2


def test_an_unnamed_model_does_not_collapse_with_other_unnamed_models():
    """Folding every anonymous model into one source would understate wildly —
    an unknown model is treated as its own family, not as a shared bucket."""
    a = Source("mystery-a", Kind.MODEL)
    b = Source("mystery-b", Kind.MODEL)
    assert independent([a, b])[0] == 2


def test_a_compromised_source_is_not_counted():
    bad = Source("leaky", Kind.TOOL, compromised=True)
    assert independent([CLAUDE_A, bad])[0] == 1


# ------------------------------------------------------------- quorum

def test_same_model_agreement_does_not_reach_quorum():
    a = assess([Signal(CLAUDE_A, True), Signal(CLAUDE_B, True)])
    assert a.state is State.INSUFFICIENT and a.independent_support == 1
    assert not a.ok


def test_the_collapse_is_named_in_the_explanation():
    """A number the caller must take on trust is not much better than a rule
    nobody applied — the fold has to be auditable."""
    text = assess([Signal(CLAUDE_A, True), Signal(CLAUDE_B, True)]).explain()
    assert "counted as ONE source" in text and "claude-a" in text and "claude-b" in text


def test_two_independent_sources_reach_quorum():
    a = assess([Signal(CLAUDE_A, True), Signal(TOOL, True)])
    assert a.state is State.CORROBORATED and a.ok


def test_quorum_is_configurable():
    sigs = [Signal(CLAUDE_A, True), Signal(TOOL, True)]
    assert assess(sigs, quorum=3).state is State.INSUFFICIENT
    assert assess(sigs, quorum=2).state is State.CORROBORATED


def test_a_single_source_never_corroborates():
    assert assess([Signal(HUMAN, True)]).state is State.INSUFFICIENT


def test_weight_collapses_with_identity():
    """Three instances of one model shouting must not outweigh one other source,
    or the collapse would be cosmetic."""
    shout = assess([Signal(CLAUDE_A, True, 1.0), Signal(CLAUDE_B, True, 1.0),
                    Signal(CLAUDE_C, True, 1.0)])
    assert shout.support_weight == 1.0


# ------------------------------------------------------------- cross-inhibition

def test_a_stop_signal_halts_a_corroborated_claim():
    """The second gate: it terminates, it does not annotate."""
    a = assess([Signal(CLAUDE_A, True), Signal(GROK, True), Signal(TOOL, True),
                Signal(HUMAN, False, 1.0, "reproduced the opposite")])
    assert a.state is State.HALTED and not a.ok


def test_more_support_does_not_revive_a_halt():
    """A pursuit that resumes because someone advocated harder was never stopped —
    that is the advisory ALERT this mechanism replaces."""
    base = [Signal(HUMAN, False, 1.0)]
    loud = base + [Signal(s, True, 5.0) for s in (CLAUDE_A, GROK, TOOL, EXTERNAL)]
    assert assess(loud).state is State.HALTED


def test_a_weak_stop_signal_contests_without_halting():
    a = assess([Signal(CLAUDE_A, True), Signal(TOOL, True),
                Signal(GROK, False, 0.4, "unconvinced")])
    assert a.state is State.CONTESTED and not a.ok


def test_weak_stops_from_one_model_family_do_not_accumulate_into_a_halt():
    """Otherwise the veto could be manufactured by running one model repeatedly —
    the exact asymmetry the independence rule exists to prevent."""
    a = assess([Signal(CLAUDE_A, True), Signal(TOOL, True), Signal(EXTERNAL, True),
                Signal(CLAUDE_B, False, 0.5), Signal(CLAUDE_C, False, 0.5)])
    assert a.stop_weight == 0.5 and a.state is State.CONTESTED


def test_weak_stops_from_independent_sources_do_accumulate():
    a = assess([Signal(CLAUDE_A, True), Signal(TOOL, True),
                Signal(GROK, False, 0.5), Signal(HUMAN, False, 0.5)])
    assert a.stop_weight == pytest.approx(1.0) and a.state is State.HALTED


def test_a_compromised_source_cannot_veto():
    saboteur = Source("captured", Kind.MODEL, model="x", compromised=True)
    a = assess([Signal(CLAUDE_A, True), Signal(TOOL, True), Signal(saboteur, False, 9.0)])
    assert a.state is State.CORROBORATED and "captured" in a.ignored


def test_halting_is_reported_in_the_explanation():
    a = assess([Signal(CLAUDE_A, True), Signal(TOOL, True), Signal(HUMAN, False)])
    assert "further support does not revive" in a.explain()


# ------------------------------------------------------------- revival

def test_reviving_a_halt_is_explicit_and_attributed():
    a = assess([Signal(CLAUDE_A, True), Signal(TOOL, True), Signal(HUMAN, False)])
    r = revive(a, by=HUMAN, reason="the reproduction used a stale fixture")
    assert r.state is State.CONTESTED


def test_reviving_requires_a_reason():
    a = assess([Signal(CLAUDE_A, True), Signal(TOOL, True), Signal(HUMAN, False)])
    with pytest.raises(ValueError, match="requires a reason"):
        revive(a, by=HUMAN, reason="  ")


def test_reviving_something_that_is_not_halted_is_refused():
    a = assess([Signal(CLAUDE_A, True), Signal(TOOL, True)])
    with pytest.raises(ValueError, match="not halted"):
        revive(a, by=HUMAN, reason="x")


def test_a_compromised_source_cannot_revive():
    a = assess([Signal(CLAUDE_A, True), Signal(TOOL, True), Signal(HUMAN, False)])
    bad = Source("captured", Kind.MODEL, model="x", compromised=True)
    with pytest.raises(ValueError, match="compromised"):
        revive(a, by=bad, reason="trust me")


# ------------------------------------------------------------- purity

def test_assess_is_a_pure_function_of_its_arguments():
    sigs = [Signal(CLAUDE_A, True), Signal(TOOL, True)]
    assert assess(sigs) == assess(sigs)
    assert isinstance(assess(sigs), Assessment)


def test_no_signals_is_insufficient_not_corroborated():
    assert assess([]).state is State.INSUFFICIENT


def test_the_default_halt_threshold_is_one_full_source():
    """A single independent source at full weight can stop a pursuit. That is the
    point: in a colony, indecision is the fatal outcome, not a wrong turn."""
    assert HALT_AT == 1.0
    assert assess([Signal(CLAUDE_A, True), Signal(TOOL, True),
                   Signal(GROK, False, 1.0)]).state is State.HALTED
