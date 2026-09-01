"""The mergeable chain: integrity without the mutex.

The claim under test is narrow and falsifiable — that giving up total order buys real
concurrency and costs nothing in integrity. So the linear chain is kept in these tests
as the control. If ``test_the_linear_chain_breaks_under_the_same_load`` ever passes,
this whole module is unnecessary and should be deleted.
"""
from __future__ import annotations

import multiprocessing as mp
from pathlib import Path

import pytest

from verity.audit import GENESIS, AuditChain
from verity.dag import MergeableChain, Node, node_hash


@pytest.fixture
def chain(tmp_path: Path) -> MergeableChain:
    return MergeableChain(tmp_path / "c.jsonl")


# ---------------------------------------------------------------- shape

def test_an_empty_chain_verifies(chain):
    ok, msg = chain.verify()
    assert ok and "0 nodes" in msg


def test_the_first_node_roots_at_genesis(chain):
    e = chain.append("claim", {"x": 1}, "alice")
    assert e["parents"] == [GENESIS]
    assert chain.nodes()[e["node_hash"]].is_root


def test_sequential_writes_form_a_line(chain):
    a = chain.append("claim", {"x": 1}, "alice")
    b = chain.append("claim", {"x": 2}, "alice")
    assert b["parents"] == [a["node_hash"]]
    assert chain.tips() == [b["node_hash"]] and not chain.forked()


def test_two_writers_on_the_same_tip_fork_rather_than_corrupt(chain):
    root = chain.append("claim", {"x": 0}, "alice")["node_hash"]
    chain.append("claim", {"x": 1}, "alice", parents=[root])
    chain.append("claim", {"x": 2}, "bob", parents=[root])
    ok, msg = chain.verify()
    assert ok, msg
    assert chain.forked() and len(chain.tips()) == 2
    assert "forked into 2 tips" in msg


def test_a_fork_is_not_reported_as_corruption(chain):
    """Reporting concurrency as corruption is the confusion that made the linear
    chain unusable for a colony."""
    root = chain.append("a", {}, "alice")["node_hash"]
    chain.append("b", {}, "alice", parents=[root])
    chain.append("c", {}, "bob", parents=[root])
    ok, _ = chain.verify()
    assert ok


# ---------------------------------------------------------------- merging

def test_merge_joins_the_tips(chain):
    root = chain.append("a", {}, "alice")["node_hash"]
    chain.append("b", {}, "alice", parents=[root])
    chain.append("c", {}, "bob", parents=[root])
    m = chain.merge("alice", reason="both findings stand")
    assert len(chain.tips()) == 1
    assert chain.nodes()[m["node_hash"]].is_merge


def test_merge_requires_a_reason(chain):
    root = chain.append("a", {}, "alice")["node_hash"]
    chain.append("b", {}, "alice", parents=[root])
    chain.append("c", {}, "bob", parents=[root])
    with pytest.raises(ValueError, match="requires a reason"):
        chain.merge("alice", reason="   ")


def test_merge_refuses_when_there_is_nothing_to_merge(chain):
    chain.append("a", {}, "alice")
    with pytest.raises(ValueError, match="nothing to merge"):
        chain.merge("alice", reason="x")


def test_append_does_not_silently_merge_a_fork(chain):
    """The writer records the tips it actually saw. Auto-merging on the next write
    would have one agent assert it had seen work it never saw, and inventing
    causality is worse than an unmerged fork because the fork is visible."""
    root = chain.append("a", {}, "alice")["node_hash"]
    b = chain.append("b", {}, "alice", parents=[root])["node_hash"]
    chain.append("c", {}, "bob", parents=[root])
    # alice writes again against only what she had read
    d = chain.append("d", {}, "alice", parents=[b])
    assert d["parents"] == [b]
    assert len(chain.tips()) == 2      # bob's branch is still open, not absorbed


# ---------------------------------------------------------------- causality

def test_ancestors_walk_through_a_merge(chain):
    root = chain.append("a", {}, "alice")["node_hash"]
    b = chain.append("b", {}, "alice", parents=[root])["node_hash"]
    c = chain.append("c", {}, "bob", parents=[root])["node_hash"]
    m = chain.merge("alice", reason="join")["node_hash"]
    assert chain.ancestors(m) == {root, b, c}


def test_concurrency_is_the_absence_of_descent(chain):
    root = chain.append("a", {}, "alice")["node_hash"]
    b = chain.append("b", {}, "alice", parents=[root])["node_hash"]
    c = chain.append("c", {}, "bob", parents=[root])["node_hash"]
    assert chain.concurrent(b, c)
    assert not chain.concurrent(root, b)     # b descends from root
    assert not chain.concurrent(b, b)


def test_a_deep_chain_does_not_blow_the_stack(chain):
    h = chain.append("a", {"i": 0}, "alice")["node_hash"]
    for i in range(1, 1500):
        h = chain.append("a", {"i": i}, "alice", parents=[h])["node_hash"]
    assert len(chain.ancestors(h)) == 1499
    assert chain.verify()[0]


# ---------------------------------------------------------------- conflict

def _key(n: Node):
    return n.event_data.get("subject")


def test_concurrent_claims_about_the_same_subject_are_surfaced(chain):
    root = chain.append("open", {}, "alice")["node_hash"]
    chain.append("claim", {"subject": "edges", "value": 17}, "alice", parents=[root])
    chain.append("claim", {"subject": "edges", "value": 22}, "bob", parents=[root])
    (pair,) = chain.conflicts(_key)
    assert {n.actor for n in pair} == {"alice", "bob"}


def test_a_fork_about_different_subjects_is_not_a_conflict(chain):
    root = chain.append("open", {}, "alice")["node_hash"]
    chain.append("claim", {"subject": "edges"}, "alice", parents=[root])
    chain.append("claim", {"subject": "pins"}, "bob", parents=[root])
    assert chain.conflicts(_key) == []


def test_sequential_claims_about_one_subject_are_not_a_conflict(chain):
    """Revising your own earlier claim is not disagreement — the later node descends
    from the earlier one, so someone saw it and moved on."""
    a = chain.append("claim", {"subject": "edges", "value": 17}, "alice")["node_hash"]
    chain.append("claim", {"subject": "edges", "value": 22}, "alice", parents=[a])
    assert chain.conflicts(_key) == []


def test_conflicts_are_returned_never_resolved(chain):
    root = chain.append("open", {}, "alice")["node_hash"]
    chain.append("claim", {"subject": "s", "value": 1}, "alice", parents=[root])
    chain.append("claim", {"subject": "s", "value": 2}, "bob", parents=[root])
    before = len(chain.read())
    chain.conflicts(_key)
    assert len(chain.read()) == before      # inspecting wrote nothing
    assert chain.forked()                   # and resolved nothing


def test_nodes_making_no_claim_are_not_contended(chain):
    root = chain.append("open", {}, "alice")["node_hash"]
    chain.append("heartbeat", {}, "alice", parents=[root])
    chain.append("heartbeat", {}, "bob", parents=[root])
    assert chain.conflicts(_key) == []      # key() returned None for both


# ---------------------------------------------------------------- integrity

def test_tampering_with_an_ancestor_is_caught(chain):
    chain.append("claim", {"x": 1}, "alice")
    chain.append("claim", {"x": 2}, "alice")
    text = chain.path.read_text().replace('"x": 1', '"x": 99')
    chain.path.write_text(text)
    ok, msg = chain.verify()
    assert not ok and "tampered" in msg


def test_a_dangling_parent_is_caught(chain):
    chain.append("claim", {"x": 1}, "alice")
    orphan = {"parents": ["0" * 64], "actor": "mallory", "event_type": "claim",
              "event_data": {}, "timestamp": "", "node_hash": ""}
    orphan["node_hash"] = node_hash(orphan["parents"], orphan["actor"],
                                    orphan["event_type"], orphan["event_data"])
    with chain.path.open("a") as f:
        import json
        f.write(json.dumps(orphan) + "\n")
    ok, msg = chain.verify()
    assert not ok and "dangling parent" in msg


def test_a_malformed_line_is_caught(chain):
    chain.append("claim", {"x": 1}, "alice")
    with chain.path.open("a") as f:
        f.write('{"actor": "mallory"}\n')
    ok, msg = chain.verify()
    assert not ok and "malformed" in msg


def test_truncation_is_caught_when_a_floor_is_given(chain):
    for i in range(3):
        chain.append("claim", {"i": i}, "alice")
    lines = chain.path.read_text().splitlines()[:2]
    chain.path.write_text("\n".join(lines) + "\n")
    assert chain.verify()[0]                                  # bare walk cannot see it
    assert not chain.verify(min_nodes=3)[0]                   # a floor can


def test_identical_events_against_identical_parents_are_idempotent(chain):
    """Two agents recording the same thing produce the same node. Worth stating
    rather than discovering — it is the behaviour you want when a retry is
    indistinguishable from a duplicate."""
    root = chain.append("a", {}, "alice")["node_hash"]
    x = chain.append("claim", {"v": 1}, "alice", parents=[root])
    y = chain.append("claim", {"v": 1}, "alice", parents=[root])
    assert x["node_hash"] == y["node_hash"]
    assert len(chain.nodes()) == 2 and len(chain.read()) == 3   # 3 lines, 2 nodes
    assert chain.verify()[0]


def test_parent_order_does_not_change_the_hash(chain):
    a = chain.append("a", {}, "alice")["node_hash"]
    b = chain.append("b", {}, "bob", parents=[a])["node_hash"]
    assert node_hash([a, b], "x", "t", {}) == node_hash([b, a], "x", "t", {})


# ---------------------------------------------------------------- the gate

def _writer(args):
    path, who, each = args
    c = MergeableChain(path)
    for i in range(each):
        c.append("finding", {"agent": who, "n": i}, actor=f"agent-{who}")


def _linear_writer(args):
    path, who, each = args
    c = AuditChain(path)
    for i in range(each):
        c.append("finding", {"agent": who, "n": i}, actor=f"agent-{who}")


@pytest.mark.parametrize("writers,each", [(6, 12)])
def test_concurrent_processes_write_and_the_chain_stays_intact(tmp_path, writers, each):
    """The Phase-4 gate: agents write concurrently and integrity still holds."""
    p = tmp_path / "concurrent.jsonl"
    with mp.Pool(writers) as pool:
        pool.map(_writer, [(p, k, each) for k in range(writers)])
    c = MergeableChain(p)
    ok, msg = c.verify()
    assert ok, msg
    assert len(c.read()) == writers * each          # nothing lost, nothing torn
    assert len(c.nodes()) == writers * each         # and nothing collided


@pytest.mark.parametrize("writers,each", [(6, 12)])
def test_the_linear_chain_breaks_under_the_same_load(tmp_path, writers, each):
    """The control. If this ever passes, the DAG is unnecessary — delete it.

    The lock in AuditChain is in-process; two processes reading the same tip both
    claim the same seq. The data is not torn, the *shape* is contradicted.
    """
    p = tmp_path / "linear.jsonl"
    with mp.Pool(writers) as pool:
        pool.map(_linear_writer, [(p, k, each) for k in range(writers)])
    ok, msg = AuditChain(p).verify()
    assert not ok
    assert "seq mismatch" in msg or "broken link" in msg
