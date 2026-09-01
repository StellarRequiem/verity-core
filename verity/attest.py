"""Portable provenance — a claim a stranger can check without trusting you.

A beacon does not move ships. It makes the rocks visible. Nothing published here can
reach into a system that is being misused and correct it; what it can do is make honest
work cheap to verify and dishonest work expensive to fake.

``prove`` already closes the loop for the *author*: a claim carries a re-runnable
command and the gate runs it. That does not travel. `python examples/eval_demo.py` means
nothing to someone who does not have the repository, at the revision the number came
from — and the honest problem underneath is that running a stranger's command is
trusting a stranger's code. ``prove``'s own documentation says so: it is not a sandbox.

So the layer that has to travel is the one that needs **no execution at all**. An
attestation pins what was claimed, which repository at which immutable commit produced
it, and the command that would reproduce it — then commits to all of that with a
content hash. Checking it needs no credentials, no network, no interpreter and no trust:

    every field present · the digest recomputes · the commit is immutable ·
    the repository is reachable by someone who is not you

That last pair is what makes fabrication expensive. A claim pinned to a branch is
pinned to nothing, because the branch can move under the reader after they check it. A
proof command that names ``/Users/someone/project`` is unreachable by construction. Both
are refused here rather than warned about, because a provenance format that accepts
unverifiable provenance is decoration.

What this deliberately does **not** claim:

*It is not a signature.* An unkeyed digest proves the record is internally consistent,
not that it came from who it says. Anyone can mint an attestation naming any repository.
What they cannot do is make the pinned commit contain a result it does not contain — so
the fabrication survives exactly until one reader looks, which is the property that
matters for a public record.

*It does not run anything.* Re-running is opt-in and belongs to ``prove``, where the
security note about executing someone else's recipe already lives.
"""
from __future__ import annotations

import hashlib
import json
import re
from dataclasses import dataclass, field

#: the fields a well-formed attestation carries; pinned so the format cannot drift
REQUIRED = ("claim", "value", "proof", "repo", "commit", "produced_at")
#: an immutable revision. A branch or tag is a moving reference, which is not provenance
RE_COMMIT = re.compile(r"^[0-9a-f]{40}$")
#: a repository someone who is not you can actually fetch
RE_REPO = re.compile(r"^(https://|git://|ssh://|git@)\S+$")
#: a local absolute path in a proof command — unreachable by construction
RE_LOCAL_PATH = re.compile(r"(^|[\s\"'=])(/(?!/)[A-Za-z0-9_.-]+/|~/)")
#: `python` rather than `python3`. Found the hard way: this repo's own example proof
#: passes in CI, where setup-python provides both, and fails on a machine that has only
#: `python3` — which is most of them, including current macOS.
RE_BARE_PYTHON = re.compile(r"(^|[\s;&|])python(?![0-9._-])")


def digest(payload: dict) -> str:
    """Content address over everything but the digest itself."""
    body = {k: v for k, v in payload.items() if k != "digest"}
    canonical = json.dumps(body, sort_keys=True, separators=(",", ":"),
                           ensure_ascii=False)
    return hashlib.sha256(canonical.encode("utf-8")).hexdigest()


def build(*, claim: str, value, proof: str, repo: str, commit: str,
          produced_at: str, metric: str | None = None, tool: str | None = None,
          tolerance: float | None = None, **extra) -> dict:
    """Assemble an attestation and seal it with its digest."""
    att = {"claim": claim, "value": value, "proof": proof, "repo": repo,
           "commit": commit, "produced_at": produced_at}
    if metric is not None:
        att["metric"] = metric
    if tool is not None:
        att["tool"] = tool
    if tolerance is not None:
        att["tolerance"] = tolerance
    att.update(extra)
    att["digest"] = digest(att)
    return att


@dataclass
class Report:
    ok: bool
    reasons: list = field(default_factory=list)
    warnings: list = field(default_factory=list)

    def explain(self) -> str:
        head = "CHECKABLE — provenance is complete and internally consistent" if self.ok \
            else "REFUSED — this claim cannot be checked by an outsider"
        lines = [head]
        lines += [f"  ✗ {r}" for r in self.reasons]
        lines += [f"  ! {w}" for w in self.warnings]
        if self.ok:
            lines.append("  (not a signature: this proves the record is consistent, "
                         "not who wrote it)")
        return "\n".join(lines)


def check(att: dict) -> Report:
    """Can a stranger check this? No execution, no network, no credentials."""
    reasons: list[str] = []
    warnings: list[str] = []

    if not isinstance(att, dict):
        return Report(False, ["not an object"])

    missing = [f for f in REQUIRED if f not in att or att[f] in (None, "")]
    if missing:
        reasons.append(f"missing required field(s): {', '.join(missing)}")

    if "digest" not in att:
        reasons.append("no digest — nothing commits to these fields")
    elif att["digest"] != digest(att):
        reasons.append("digest does not match the content — altered after sealing")

    commit = str(att.get("commit", ""))
    if commit and not RE_COMMIT.match(commit):
        reasons.append(
            f"commit {commit!r} is not a full 40-character SHA — a branch or tag is a "
            f"moving reference, and can change under the reader after they check it")

    repo = str(att.get("repo", ""))
    if repo and not RE_REPO.match(repo):
        reasons.append(
            f"repo {repo!r} is not a fetchable URL — a local path is unreachable by "
            f"anyone who is not on that machine")

    proof = str(att.get("proof", ""))
    if proof and RE_LOCAL_PATH.search(proof):
        reasons.append(
            "the proof command names an absolute local path — it cannot run anywhere "
            "but the machine that wrote it")
    if proof and not proof.strip():
        reasons.append("empty proof command")

    v = att.get("value")
    if v is not None and not isinstance(v, (int, float)) or isinstance(v, bool):
        reasons.append(f"value {v!r} is not a number — nothing to compare a re-run to")

    if proof and RE_BARE_PYTHON.search(proof):
        warnings.append(
            "the proof invokes `python`, which does not exist on many systems that "
            "have `python3` — it will pass in CI and fail for a reader")

    if "tolerance" not in att:
        warnings.append("no tolerance — an exact-equality comparison on a float will "
                        "usually fail for reasons that have nothing to do with honesty")
    if "metric" not in att:
        warnings.append("no metric named — a bare number is harder to extract from a "
                        "re-run's output unambiguously")

    return Report(not reasons, reasons, warnings)


def check_batch(atts: list) -> tuple[bool, list]:
    """Check many. Returns ``(all_ok, [(index, Report)])``."""
    out = [(i, check(a)) for i, a in enumerate(atts)]
    return all(r.ok for _, r in out), out
