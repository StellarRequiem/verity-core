"""verity.anchor — the *live* Reality Anchor + a grounding tool with provenance.

``verify()`` is a pure, deterministic comparator: it reconciles a claim against
*resolved* facts you hand it, and never does I/O. That purity is the seam this
module builds on. The anchor is the I/O layer ON TOP of ``verify``:

    1. FETCH  — each :class:`Source` pulls ground truth from the *running system*
                (a git ref, a file on disk, a DB query, an HTTP endpoint) for the
                claim's ``proof`` locator. Sources never raise — an error or an
                unreachable source returns ``None`` (silent), never a verdict.
    2. RECONCILE — the fetched facts are fed to ``verify(claim, sources=...)`` so the
                deterministic GROUNDING dimension does the comparison. A source that
                asserts a different value than the claim → CRITICAL → REFUSE.
    3. CORROBORATE — cross-referential policy: a PASS requires that ≥ ``min_sources``
                *independent* sources adjudicated the claim and none contradicted it.
                Fewer than that, or any ungrounded key → UNVERIFIABLE (= *do not believe
                it*, not *it is true*).
    4. PROVENANCE — every fact is tagged with WHERE it came from (source id + locator)
                and its STANCE (support / contradict / silent), so the verdict shows its
                work: which live source asserted what, fetched from where.
    5. LOG    — verdict + provenance is appended to a tamper-evident
                :class:`~verity.audit.AuditChain` (the claim ledger).

This is what keeps many agents aligned: agent agreement counts for nothing; only
reconciliation against the non-generative sources counts, and a claim ≥``min_sources``
of them can't corroborate does not propagate. NO LLM is in this loop — the fetch is a
subprocess/read, the comparison is ``verify``'s deterministic field reconciliation. The
grader is isolated from the generator; the verifier only ever asks the running system.
"""
from __future__ import annotations

import re
import subprocess
from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from pathlib import Path

from .audit import AuditChain
from .gate import _norm, _num
from .verify import verify

PASS, REFUSE, UNVERIFIABLE = "PASS", "REFUSE", "UNVERIFIABLE"

# A truth profile for fact/code claims. The trading-rigor structural requirements
# (out-of-sample / leakage) that the empirical gate enforces by default do NOT apply
# to a "does the running system actually say X" claim — they would spuriously WARN
# every code/config fact. GROUNDING + EVIDENCE reconciliation still run in full. An
# empirical (win-rate/accuracy) claim should pass its own trading truth instead.
FACTS_PROFILE = {"thresholds": {"require_out_of_sample": False,
                                "require_leakage_check": False}, "facts": []}


def _coerce(s: str):
    """Best-effort scalar from a captured string: bool, then int, then float, else str.

    A captured value compared against a numeric claim field must read back as a number
    (so ``verify`` does numeric-within-tolerance, not string compare); a dotted version
    like ``0.1.0`` stays a string. Deterministic, never raises.
    """
    t = (s or "").strip()
    low = t.lower()
    if low in ("true", "false"):
        return low == "true"
    try:
        return int(t)
    except ValueError:
        pass
    try:
        return float(t)
    except ValueError:
        return t


class Source(ABC):
    """A pinned, independent, non-generative ground-truth source.

    ``id`` is stable + unique (identifies the source in the ledger + corroboration count).
    ``kind`` matches a proof probe's ``source`` field (``git`` / ``file`` / ``db`` / …) so
    the anchor can attribute each fact's locator. ``fetch`` returns a resolved facts dict, or
    ``None`` when this source cannot adjudicate (silent — never a verdict, never a crash).
    """

    id: str = "source"
    kind: str = "generic"

    @abstractmethod
    def fetch(self, claim: dict, proof: list[dict]) -> dict | None:  # pragma: no cover - interface
        ...


class GitSource(Source):
    """Ground truth from a git ref — what the repo *actually* committed.

    Probe shape: ``{"source":"git", "path", "ref"?, "field", "pattern"? | "contains"?}``.
    ``git show <ref>:<path>`` is read; ``pattern``'s first capture group (coerced) becomes the
    field value, or ``contains`` yields a bool presence. A missing file / failed command /
    no-match contributes nothing (silent on that field) rather than forcing a verdict.
    """

    kind = "git"

    def __init__(self, repo: str | Path = ".", id: str = "git") -> None:
        self.repo = str(repo)
        self.id = id

    def _show(self, ref: str, path: str) -> str | None:
        try:
            r = subprocess.run(["git", "-C", self.repo, "show", f"{ref}:{path}"],
                               capture_output=True, text=True, timeout=10)
            return r.stdout if r.returncode == 0 else None
        except Exception:
            return None

    def fetch(self, claim: dict, proof: list[dict]) -> dict | None:
        facts: dict = {}
        for p in proof:
            if p.get("source", "git") != "git":
                continue
            content = self._show(p.get("ref", "HEAD"), p["path"])
            if content is None:
                continue
            facts.update(_apply_probe(content, p))
        return facts or None


class FileSource(Source):
    """Ground truth from a file on disk *right now* — the working-tree state.

    Independent of :class:`GitSource` for catching *uncommitted drift* (HEAD says one thing,
    the live file another). Same probe shape, ``source: "file"``.
    """

    kind = "file"

    def __init__(self, root: str | Path = ".", id: str = "file") -> None:
        self.root = Path(root)
        self.id = id

    def fetch(self, claim: dict, proof: list[dict]) -> dict | None:
        facts: dict = {}
        for p in proof:
            if p.get("source") != "file":
                continue
            try:
                content = (self.root / p["path"]).read_text(encoding="utf-8")
            except Exception:
                continue
            facts.update(_apply_probe(content, p))
        return facts or None


class CompilerSource(Source):
    """Ground a code claim against a real compiler/checker — language-agnostic.

    ONE source covers every language because the probe carries the exact toolchain command:
      C / C++ : ["clang", "-fsyntax-only", path]     Java : ["javac", "-d", "/tmp", path]
      shell   : ["bash", "-n", path]                 JS   : ["node", "--check", path]
      Ruby    : ["ruby", "-c", path]                 TS   : ["tsc", "--noEmit", path]
    Probe: ``{"source":"compile", "field":"compiles", "cmd":[...], "cwd"?, "timeout"?}``.
    Returns ``{field: bool}`` = did the command exit 0? A missing toolchain / crash is silent
    (None), never a verdict. Commands run in the sandbox — use SYNTAX/COMPILE checks (no side
    effects), not arbitrary execution; that's the deterministic, non-generative oracle per language.
    """

    kind = "compile"

    def __init__(self, id: str = "compile") -> None:
        self.id = id

    def fetch(self, claim: dict, proof: list[dict]) -> dict | None:
        facts: dict = {}
        for p in proof:
            if p.get("source") != "compile":
                continue
            fld = p.get("field", "compiles")
            cmd = p.get("cmd")
            if not cmd:
                continue
            try:
                r = subprocess.run(cmd, capture_output=True, text=True,
                                   timeout=p.get("timeout", 30), cwd=p.get("cwd"))
                facts[fld] = (r.returncode == 0)
            except Exception:
                pass   # missing toolchain / timeout / crash → silent on this field
        return facts or None


def _apply_probe(content: str, p: dict) -> dict:
    """Extract one field from text via a probe. Deterministic, never raises."""
    field_name = p.get("field")
    if not field_name:
        return {}
    if "contains" in p:
        return {field_name: p["contains"] in content}
    pat = p.get("pattern")
    if pat:
        try:
            m = re.search(pat, content)
        except re.error:
            return {}
        if m:
            return {field_name: _coerce(m.group(1) if m.groups() else m.group(0))}
    return {}


def _locator(p: dict) -> str:
    """A human-readable 'where from' for a probe — the provenance trail."""
    src = p.get("source", "git")
    if src == "git":
        loc = f"git {p.get('ref', 'HEAD')}:{p.get('path', '?')}"
    elif src == "file":
        loc = f"file {p.get('path', '?')}"
    elif src in ("db", "sql"):
        return f"db: {p.get('query', p.get('locator', '?'))}"
    else:
        loc = f"{src}:{p.get('path', p.get('locator', '?'))}"
    if p.get("pattern"):
        loc += f"  /{p['pattern']}/"
    elif "contains" in p:
        loc += f"  contains {p['contains']!r}"
    return loc


def _stance(claim_val, src_val) -> str:
    """How a fetched value relates to the claim: support | contradict | asserts | silent.

    For DISPLAY/provenance only — the authoritative verdict is ``verify``'s. Mirrors verify's
    bool-first → numeric-within-tolerance → normalized-string order so the trail agrees with
    the verdict. ``asserts`` = source provides a value the claim never carried (extra context).
    """
    if src_val is None:
        return "silent"
    if claim_val is None:
        return "asserts"
    if isinstance(claim_val, bool) or isinstance(src_val, bool):
        return "support" if claim_val == src_val else "contradict"
    cn, sn = _num(claim_val), _num(src_val)
    if cn is not None and sn is not None:
        return "support" if abs(cn - sn) <= max(1e-9, 0.01 * abs(sn)) else "contradict"
    return "support" if _norm(str(claim_val)) == _norm(str(src_val)) else "contradict"


def _provenance(claim: dict, proof: list[dict], sources: list[Source], fetched: dict) -> list[dict]:
    """Join (sources × their probes × fetched values) into a where-from trail."""
    prov: list[dict] = []
    for s in sources:
        facts = fetched.get(s.id)
        for p in proof:
            if p.get("source", "git") != getattr(s, "kind", s.id):
                continue
            fld = p.get("field")
            if not fld:
                continue
            val = facts.get(fld) if isinstance(facts, dict) else None
            prov.append({"source_id": s.id, "source_kind": getattr(s, "kind", ""),
                         "field": fld, "value": val, "locator": _locator(p),
                         "stance": _stance(claim.get(fld), val)})
    return prov


@dataclass
class AnchorResult:
    verdict: str                       # PASS | REFUSE | UNVERIFIABLE
    detail: str
    n_corroborating: int               # how many sources returned facts
    fetched: dict = field(default_factory=dict)        # {source_id: facts | None}
    provenance: list = field(default_factory=list)     # [{source_id, field, value, locator, stance}]
    verify_result: dict = field(default_factory=dict)


def _decide(res: dict, n_asserting: int, min_sources: int) -> tuple[str, str]:
    """Map a verify() result + corroboration count → (verdict, detail)."""
    if res.get("verdict") == REFUSE:
        return REFUSE, "a source contradicts the claim (or it is internally impossible)"
    g = res.get("dimensions", {}).get("grounding")
    if g is None:
        return UNVERIFIABLE, "no source could adjudicate this claim"
    if g.get("verdict") != PASS:
        return UNVERIFIABLE, "at least one claimed field is not asserted by any source"
    if n_asserting < min_sources:
        return UNVERIFIABLE, f"grounded by {n_asserting} source(s) < required {min_sources}"
    return PASS, f"corroborated by {n_asserting} independent source(s), no contradiction"


def anchor(claim: dict, sources: list[Source], *, ledger: AuditChain | None = None,
           truth: dict | None = None, min_sources: int = 2, actor: str = "anchor") -> AnchorResult:
    """Reconcile ``claim`` against live ``sources``, with provenance, and (optionally) log it."""
    proof = claim.get("proof") or []
    pure = {k: v for k, v in claim.items() if k != "proof"}

    fetched: dict = {}
    for s in sources:
        try:
            fetched[s.id] = s.fetch(pure, proof)
        except Exception:
            fetched[s.id] = None   # a crashing source is silent, never a verdict

    resolved = [{"id": sid, "facts": f} for sid, f in fetched.items() if isinstance(f, dict) and f]
    n_asserting = len(resolved)

    res = verify(pure, sources=(resolved or None), truth=truth or FACTS_PROFILE)
    verdict, detail = _decide(res, n_asserting, min_sources)
    prov = _provenance(pure, proof, sources, fetched)

    if ledger is not None:
        ledger.append("anchor_verdict",
                      {"claim": pure, "provenance": prov, "verify": res,
                       "verdict": verdict, "n_sources": n_asserting,
                       "min_sources": min_sources, "detail": detail},
                      actor=actor)
    return AnchorResult(verdict, detail, n_asserting, fetched, prov, res)


def format_anchor_block(claim: dict, r: AnchorResult) -> str:
    """Render a REALITY-ANCHOR block: verdict + the provenance trail (where each fact is from)."""
    name = claim.get("name", claim.get("text", "?"))
    lines = ["REALITY-ANCHOR",
             f"  Claim:    {name}",
             f"  Verdict:  {r.verdict}   ({r.detail})",
             f"  Sources:  {r.n_corroborating} corroborating of {len(r.fetched)} queried",
             "  Provenance (where each fact is from):"]
    if r.provenance:
        for pv in r.provenance:
            lines.append(f"    [{pv['stance']:10}] {pv['field']} = {pv['value']!r}")
            lines.append(f"                 from {pv['source_id']} :: {pv['locator']}")
    else:
        lines.append("    (no probe ran — claim carried no proof locator)")
    lines.append("  Note:     non-generative grounding — sources are the running system, not a model.")
    return "\n".join(lines)
