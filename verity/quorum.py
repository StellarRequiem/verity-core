"""Corroboration that counts sources, not voices.

The rule this exists to mechanise has been written down in every version of the
protocol and enforced by memory: *corroboration needs real, independent sources — not
two instances of the same model in different hats.* Memory is exactly the wrong place
for it. Asking one model twice and getting the same answer feels like agreement and
costs almost nothing, so it happens by default, and a claim that two instances agree
reads identically to a claim that two sources agree.

So independence is counted rather than assumed. Two instances of the same model are
one source. A model and a human are two. A model and a tool that measured something
are two. The number that matters is how many *independent* sources a claim has, and
that number is computed here instead of remembered.

The other mechanism worth importing from a colony is **cross-inhibition**. When scouts
disagree about a site they do not merely advertise harder; they deliver stop signals
that decrement a rival's recruitment directly. Without it a swarm can deadlock between
two good options forever, which is fatal — a colony with no home dies. An advisory
ALERT nobody is obliged to act on is the deadlock. A stop signal has to be able to
*end* a pursuit, and here it does: past the halt threshold the state is HALTED, and
further support does not revive it. Reviving takes an explicit, recorded override,
because a pursuit that quietly resumes was never really stopped.

The disanalogy that has to be engineered around: bee cooperation is underwritten by
shared genes. A worker has no separate interest to defend, so a stop signal can be
trusted. Agents have no such guarantee — nothing stops a source from inhibiting a
rival's claim because it is a rival. Verifiable provenance is the substitute, and it
is only a partial one: this module weighs *who* is speaking and can be told a source
is compromised, but it cannot detect a plausible liar. That limit is real and stated
rather than papered over.

Pure. No I/O, no clock, no network — every function here is a computation over the
arguments it is given.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from enum import Enum

#: independent sources required before a claim counts as corroborated
QUORUM = 2
#: total stop weight at which a pursuit is halted rather than merely discouraged
HALT_AT = 1.0


class Kind(str, Enum):
    MODEL = "model"        #: an LLM instance — collapses with its siblings
    HUMAN = "human"        #: a person
    TOOL = "tool"          #: a deterministic measurement — a test run, a scanner
    EXTERNAL = "external"  #: a third party outside this system


class State(str, Enum):
    INSUFFICIENT = "insufficient"   #: not enough independent sources to say anything
    CORROBORATED = "corroborated"   #: quorum met, not halted
    CONTESTED = "contested"         #: quorum met, but stop signals are live
    HALTED = "halted"               #: stop weight reached the threshold; pursuit ends


@dataclass(frozen=True)
class Source:
    """Who is speaking, and what they are an instance of.

    ``identity`` is what collapses. For a model it is the model name, so two
    instances of it are one source however differently they were prompted. For a
    human or a tool it defaults to the actor, because two people genuinely are two
    sources and two independent measurements genuinely are two measurements.
    """
    actor: str
    kind: Kind = Kind.MODEL
    model: str | None = None
    compromised: bool = False

    @property
    def identity(self) -> str:
        if self.kind is Kind.MODEL:
            # an unnamed model is treated as its own family rather than collapsing
            # every anonymous model into one source, which would understate wildly
            return f"model:{self.model or self.actor}"
        return f"{self.kind.value}:{self.model or self.actor}"


@dataclass(frozen=True)
class Signal:
    source: Source
    supports: bool          #: True to advocate, False to inhibit
    weight: float = 1.0
    note: str = ""


@dataclass(frozen=True)
class Assessment:
    state: State
    independent_support: int
    independent_stop: int
    support_weight: float
    stop_weight: float
    collapsed: dict = field(default_factory=dict)   #: identity -> actors folded into it
    ignored: list = field(default_factory=list)     #: compromised sources, named

    @property
    def ok(self) -> bool:
        return self.state is State.CORROBORATED

    def explain(self) -> str:
        lines = [f"{self.state.value.upper()} — {self.independent_support} independent "
                 f"supporting source(s), {self.independent_stop} stopping"]
        for ident, actors in sorted(self.collapsed.items()):
            if len(actors) > 1:
                lines.append(f"  {len(actors)} voices counted as ONE source ({ident}): "
                             f"{', '.join(sorted(actors))}")
        for a in sorted(self.ignored):
            lines.append(f"  ignored as compromised: {a}")
        if self.state is State.HALTED:
            lines.append(f"  stop weight {self.stop_weight:g} reached the halt "
                         f"threshold — further support does not revive this")
        return "\n".join(lines)


def independent(sources) -> tuple[int, dict]:
    """How many independent sources these voices amount to, and what collapsed.

    Returns ``(count, {identity: [actors]})`` so the collapse is auditable rather
    than a number the caller has to take on trust.
    """
    groups: dict[str, list[str]] = {}
    for s in sources:
        if s.compromised:
            continue
        groups.setdefault(s.identity, []).append(s.actor)
    return len(groups), groups


def assess(signals, *, quorum: int = QUORUM, halt_at: float = HALT_AT) -> Assessment:
    """Weigh advocacy against inhibition, counting sources rather than voices."""
    live = [s for s in signals if not s.source.compromised]
    ignored = sorted({s.source.actor for s in signals if s.source.compromised})

    sup = [s for s in live if s.supports]
    stop = [s for s in live if not s.supports]
    n_sup, sup_groups = independent([s.source for s in sup])
    n_stop, stop_groups = independent([s.source for s in stop])

    # weights collapse the same way: three instances of one model shouting is one
    # source's worth of weight, or the collapse would be cosmetic
    def _weight(sigs) -> float:
        by_ident: dict[str, float] = {}
        for s in sigs:
            by_ident[s.source.identity] = max(by_ident.get(s.source.identity, 0.0),
                                              float(s.weight))
        return sum(by_ident.values())

    w_sup, w_stop = _weight(sup), _weight(stop)

    if w_stop >= halt_at and n_stop >= 1:
        state = State.HALTED
    elif n_sup < quorum:
        state = State.INSUFFICIENT
    elif n_stop:
        state = State.CONTESTED
    else:
        state = State.CORROBORATED

    return Assessment(state, n_sup, n_stop, w_sup, w_stop,
                      collapsed={**sup_groups, **stop_groups}, ignored=ignored)


def revive(assessment: Assessment, *, by: Source, reason: str) -> Assessment:
    """Explicitly overturn a halt. Refuses without a reason and a named source.

    A halted pursuit that resumed because someone added more support was never
    stopped — the stop signal would be advisory again, which is the deadlock this
    mechanism exists to break. Reviving is therefore a separate, attributed act.
    """
    if assessment.state is not State.HALTED:
        raise ValueError("nothing to revive — this pursuit is not halted")
    if not str(reason).strip():
        raise ValueError("reviving a halted pursuit requires a reason")
    if by.compromised:
        raise ValueError(f"{by.actor} is marked compromised and cannot revive a halt")
    return Assessment(State.CONTESTED, assessment.independent_support,
                      assessment.independent_stop, assessment.support_weight,
                      assessment.stop_weight, assessment.collapsed, assessment.ignored)
