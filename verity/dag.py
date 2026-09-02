"""A mergeable audit chain — the same integrity guarantee without the mutex.

``AuditChain`` is a line. Each entry names the one before it by hash and carries a
``seq``, so integrity and *ordering* are the same guarantee. That is exactly right for
one writer and it is why the docstring there says to honour the single-writer rule:
two processes reading the same tip and appending both produce ``seq`` N with the same
``prev_hash``, and ``verify()`` correctly calls the result broken. The lock is not
protecting the data, it is protecting the *shape*.

A colony is massively concurrent, and no amount of care makes a line concurrent. So the
shape changes: an entry names **every parent its writer had actually seen**, and the
chain becomes a directed acyclic graph. The integrity guarantee is untouched — each node
still commits to its parents by hash, so no ancestor can be edited without breaking
every descendant. What is given up is total order, which was never real anyway; what is
gained is that two agents writing at the same instant produce a *fork*, which is a
legitimate recorded state rather than corruption.

Three things this deliberately does not do:

**It does not merge on your behalf.** ``append`` records the tips the writer actually
read. If another agent wrote in between, the result is two tips, and it stays two tips
until somebody calls ``merge`` and says why. Auto-merging on the next write would have
one agent silently assert it had seen work it never saw — inventing causality is a
worse failure than an unmerged fork, because the fork is visible.

**It does not decide what a conflict is.** A fork is concurrency, not disagreement.
Two agents recording unrelated findings at the same moment conflict about nothing. A
conflict is two *concurrent* nodes making claims about the same subject, and what
counts as "the same subject" is domain knowledge this module does not have. So it
supplies causality — ``concurrent(a, b)`` — and takes a key function from the caller.

**It does not resolve one.** ``conflicts()`` returns pairs. Nothing here picks a winner.
A resolution that happens automatically is a resolution nobody reviewed.

Threat model is inherited from ``audit`` verbatim and is worth re-reading there: unkeyed
is integrity, not tamper-evidence. Anyone who can rewrite the file can recompute a
self-consistent DAG. Keying and anchoring apply here the same way and for the same
reasons.
"""
from __future__ import annotations

import hashlib
import json
import os
from dataclasses import dataclass
from pathlib import Path

from .audit import GENESIS, _now_iso, entry_hash

#: fields every well-formed node carries
NODE_FIELDS = frozenset(
    {"parents", "actor", "event_type", "event_data", "timestamp", "node_hash"})


def node_hash(parents, actor: str, event_type: str, event_data: dict) -> str:
    """Content address for a node. Parents are sorted so the hash cannot depend on
    the order a writer happened to read its tips in.

    The timestamp is excluded, exactly as in the linear chain, so re-stamping cannot
    silently rewrite links. A consequence worth stating rather than discovering: two
    agents who record the identical event against the identical parents produce the
    identical node, and the second is a no-op. That is idempotence, and it is the
    behaviour you want when a retry is indistinguishable from a duplicate.
    """
    canonical = json.dumps(
        {"parents": sorted(parents), "actor": actor,
         "event_type": event_type, "event_data": event_data},
        sort_keys=True, separators=(",", ":"), ensure_ascii=False)
    return hashlib.sha256(canonical.encode("utf-8")).hexdigest()


@dataclass(frozen=True)
class Node:
    hash: str
    parents: tuple[str, ...]
    actor: str
    event_type: str
    event_data: dict
    timestamp: str

    @property
    def is_merge(self) -> bool:
        return len(self.parents) > 1

    @property
    def is_root(self) -> bool:
        return self.parents == (GENESIS,)


class MergeableChain:
    """Append-only JSONL DAG at ``path``. Safe for concurrent *processes*.

    There is no lock. A write is one ``O_APPEND`` write of a single line, which the
    kernel will not interleave with another process's line — so concurrency produces
    two well-formed sibling nodes rather than one torn one. That is the whole trick,
    and it is why the shape had to change first: interleaving was never the danger,
    two writers claiming the same position was.
    """

    def __init__(self, path: str | Path) -> None:
        self.path = Path(path)

    # ------------------------------------------------------------------ reading

    def read(self) -> list[dict]:
        if not self.path.exists():
            return []
        rows = []
        for line in self.path.read_text(encoding="utf-8").splitlines():
            if line.strip():
                rows.append(json.loads(line))
        return rows

    def nodes(self) -> dict[str, Node]:
        out: dict[str, Node] = {}
        for r in self.read():
            out[r["node_hash"]] = Node(
                hash=r["node_hash"], parents=tuple(r["parents"]), actor=r["actor"],
                event_type=r["event_type"], event_data=r["event_data"],
                timestamp=r.get("timestamp", ""))
        return out

    def tips(self) -> list[str]:
        """Nodes nobody has built on. One tip is a line; more than one is a fork."""
        ns = self.nodes()
        claimed = {p for n in ns.values() for p in n.parents}
        return sorted(h for h in ns if h not in claimed)

    def forked(self) -> bool:
        return len(self.tips()) > 1

    # ------------------------------------------------------------------ writing

    def append(self, event_type: str, event_data: dict, actor: str = "agent",
               parents: list[str] | None = None) -> dict:
        """Record an event against the tips this writer has seen.

        Passing ``parents`` explicitly is how a writer says "this is what I had read"
        — which is the honest thing when the read and the write are far apart. The
        default reads the tips now.
        """
        if parents is None:
            parents = self.tips() or [GENESIS]
        parents = sorted(set(parents))
        h = node_hash(parents, actor, event_type, event_data)
        entry = {"parents": parents, "actor": actor, "event_type": event_type,
                 "event_data": event_data, "timestamp": _now_iso(), "node_hash": h}
        line = (json.dumps(entry, ensure_ascii=False) + "\n").encode("utf-8")
        self.path.parent.mkdir(parents=True, exist_ok=True)
        # O_APPEND + a single write: the kernel places the whole line at the current
        # end of file atomically, so two processes racing produce two intact lines.
        fd = os.open(self.path, os.O_WRONLY | os.O_CREAT | os.O_APPEND, 0o644)
        try:
            os.write(fd, line)
        finally:
            os.close(fd)
        return entry

    def merge(self, actor: str = "agent", reason: str = "", *,
              parents: list[str] | None = None) -> dict:
        """Join open tips into one, deliberately and with a reason recorded.

        This exists as its own verb rather than as a side effect of the next append
        because a merge is a claim: *these two histories are compatible and I say so.*
        Somebody has to make it, and the record should say who and why.
        """
        tips = sorted(set(parents if parents is not None else self.tips()))
        if len(tips) < 2:
            raise ValueError("nothing to merge — the chain has a single tip")
        if not str(reason).strip():
            raise ValueError(
                "merging requires a reason — an unexplained merge is indistinguishable "
                "from an automatic one, which is the thing this verb exists to prevent")
        return self.append("merge", {"reason": str(reason).strip(),
                                     "merged": tips}, actor, parents=tips)

    # ------------------------------------------------------------------ causality

    def ancestors(self, h: str) -> set[str]:
        """Every node ``h`` descends from. Iterative — a deep chain must not blow
        the interpreter stack just because it got long."""
        ns = self.nodes()
        seen: set[str] = set()
        stack = list(ns[h].parents) if h in ns else []
        while stack:
            cur = stack.pop()
            if cur == GENESIS or cur in seen:
                continue
            seen.add(cur)
            if cur in ns:
                stack.extend(ns[cur].parents)
        return seen

    def concurrent(self, a: str, b: str) -> bool:
        """True when neither node descends from the other — they were written
        without either writer having seen the other."""
        if a == b:
            return False
        return b not in self.ancestors(a) and a not in self.ancestors(b)

    def conflicts(self, key) -> list[tuple[Node, Node]]:
        """Concurrent nodes that speak about the same subject, as ``key`` defines it.

        ``key`` maps a Node to a hashable subject, or to ``None`` for "this node makes
        no claim worth contending". Returned, never resolved: picking a winner here
        would be a resolution nobody reviewed.
        """
        ns = list(self.nodes().values())
        buckets: dict[object, list[Node]] = {}
        for n in ns:
            k = key(n)
            if k is not None:
                buckets.setdefault(k, []).append(n)
        out: list[tuple[Node, Node]] = []
        for group in buckets.values():
            for i, a in enumerate(group):
                for b in group[i + 1:]:
                    if self.concurrent(a.hash, b.hash):
                        out.append(tuple(sorted((a, b), key=lambda n: n.hash)))
        return sorted(out, key=lambda p: (p[0].hash, p[1].hash))

    # ------------------------------------------------------------------ integrity

    def verify(self, *, expected_tips: list[str] | None = None,
               min_nodes: int | None = None) -> tuple[bool, str]:
        """Walk the DAG and check integrity, returning ``(ok, message)``.

        A fork is **not** a failure. Reporting concurrency as corruption is precisely
        the confusion the linear chain forced, and the reason a colony could not use
        it. Forks are counted and named in the message.
        """
        rows = self.read()
        ns: dict[str, Node] = {}
        for i, r in enumerate(rows):
            missing = NODE_FIELDS - set(r)
            if missing:
                return False, f"malformed node at line {i}: missing {sorted(missing)}"
            h = node_hash(r["parents"], r["actor"], r["event_type"], r["event_data"])
            if r["node_hash"] != h:
                return False, f"hash mismatch at line {i} — tampered"
            ns[h] = Node(h, tuple(r["parents"]), r["actor"], r["event_type"],
                         r["event_data"], r.get("timestamp", ""))

        for h, n in ns.items():
            for p in n.parents:
                if p != GENESIS and p not in ns:
                    return False, f"dangling parent {p[:12]}… referenced by {h[:12]}…"

        # A hash cycle is not constructible without breaking SHA-256, but a
        # hand-edited file can assert one, and an unchecked cycle would hang callers.
        colour: dict[str, int] = {}
        for start in ns:
            if colour.get(start):
                continue
            stack = [(start, iter(ns[start].parents))]
            colour[start] = 1
            while stack:
                cur, it = stack[-1]
                nxt = next(it, None)
                if nxt is None:
                    colour[cur] = 2
                    stack.pop()
                    continue
                if nxt == GENESIS or nxt not in ns:
                    continue
                if colour.get(nxt) == 1:
                    return False, f"cycle through {nxt[:12]}…"
                if colour.get(nxt) != 2:
                    colour[nxt] = 1
                    stack.append((nxt, iter(ns[nxt].parents)))

        tips = self.tips()
        if min_nodes is not None and len(ns) < min_nodes:
            return False, f"truncated: {len(ns)} nodes < expected {min_nodes}"
        if expected_tips is not None and sorted(tips) != sorted(expected_tips):
            return False, f"tip mismatch: expected {len(expected_tips)}, got {len(tips)}"
        shape = "linear" if len(tips) <= 1 else f"forked into {len(tips)} tips"
        return True, f"intact: {len(ns)} nodes, {shape}"


# ------------------------------------------------------------------ linear bridge

#: the fields a well-formed linear ``AuditChain`` record carries
LINEAR_FIELDS = frozenset(
    {"seq", "prev_hash", "actor", "event_type", "event_data", "entry_hash"})

def linear_nodes(rows: list[dict]) -> dict[str, Node]:
    """Read linear ``AuditChain`` records as DAG nodes. Pure; nothing is written.

    A linear record already carries everything a node needs: ``entry_hash`` is its
    content address and ``prev_hash`` is its single parent. The only thing the linear
    format adds is ``seq``, an assertion of total order — and that assertion is the
    part that breaks under concurrency, not the data.
    """
    return {
        r["entry_hash"]: Node(
            hash=r["entry_hash"], parents=(r["prev_hash"],), actor=r["actor"],
            event_type=r["event_type"], event_data=r["event_data"],
            timestamp=r.get("timestamp", ""))
        for r in rows
    }


def verify_linear(rows: list[dict]) -> tuple[bool, str, dict]:
    """Verify a linear chain under DAG rules, and say what shape it is really in.

    This exists because of a real chain that ``AuditChain.verify()`` called BROKEN.
    Three records shared ``seq`` 462 — and all three shared one ``prev_hash``, every
    ``entry_hash`` recomputed, and a later record continued one of the branches. That
    is not corruption. It is three writers who read the same tip, which the linear
    model has no way to express and therefore reports as damage.

    The distinction matters more than it looks. Calling concurrency "corruption"
    means the fix appears to be *repairing* the file — renumbering ``seq`` until the
    walk passes — which would rewrite an append-only audit chain to satisfy a model
    it never fitted. Under DAG rules nothing needs repairing, and nothing is written.

    Returns ``(ok, message, info)`` where ``info`` names the tips, so abandoned
    branches are visible rather than merely not-fatal.
    """
    # Validate every record's shape BEFORE reading any of them as nodes. Building
    # first meant a record missing `entry_hash` raised KeyError instead of saying so,
    # which turns a clear finding into a stack trace at exactly the moment a reader
    # most needs a sentence.
    for i, r in enumerate(rows):
        missing = LINEAR_FIELDS - set(r)
        if missing:
            return False, f"malformed record at line {i}: missing {sorted(missing)}", {}
        h = entry_hash(r["seq"], r["prev_hash"], r["actor"], r["event_type"],
                       r["event_data"])
        if h != r["entry_hash"]:
            return False, f"hash mismatch at line {i} — tampered", {}

    nodes = linear_nodes(rows)

    for h, n in nodes.items():
        for p in n.parents:
            if p != GENESIS and p not in nodes:
                return False, f"dangling parent {p[:12]}… referenced by {h[:12]}…", {}

    claimed = {p for n in nodes.values() for p in n.parents}
    tips = sorted(h for h in nodes if h not in claimed)
    # A linear chain has one child per parent. More than one is a concurrent write.
    children: dict[str, list[str]] = {}
    for h, n in nodes.items():
        for p in n.parents:
            children.setdefault(p, []).append(h)
    forks = {p: sorted(c) for p, c in children.items() if len(c) > 1}

    # The live head is the record written last, which is file order — not the
    # alphabetical last tip. Getting this wrong names the wrong branch abandoned,
    # which is worse than not naming one at all.
    head = rows[-1]["entry_hash"] if rows else ""
    abandoned = sorted(t for t in tips if t != head)

    info = {"nodes": len(nodes), "tips": tips, "forks": forks,
            "head": head, "abandoned": abandoned}
    if len(tips) <= 1:
        shape = "linear"
    else:
        widest = max((len(c) for c in forks.values()), default=0)
        shape = (f"{len(forks)} concurrent write(s) (widest {widest}-way), "
                 f"{len(abandoned)} abandoned branch(es)")
    return True, f"intact: {len(nodes)} records, {shape}", info
