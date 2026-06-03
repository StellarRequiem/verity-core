"""The audit chain must verify clean and detect any tampering."""
import json

from verity.audit import GENESIS, AuditChain, entry_hash


def test_append_and_verify(tmp_path):
    c = AuditChain(tmp_path / "a.jsonl")
    c.append("evt", {"x": 1})
    c.append("evt", {"x": 2})
    ok, msg = c.verify()
    assert ok
    assert "2 entries" in msg


def test_tamper_is_detected(tmp_path):
    p = tmp_path / "a.jsonl"
    c = AuditChain(p)
    c.append("evt", {"x": 1})
    c.append("evt", {"x": 2})
    lines = p.read_text().splitlines()
    row = json.loads(lines[0])
    row["event_data"] = {"x": 999}
    lines[0] = json.dumps(row)
    p.write_text("\n".join(lines) + "\n")
    ok, _ = c.verify()
    assert not ok


def test_hash_is_deterministic_and_timestamp_free():
    h1 = entry_hash(0, GENESIS, "a", "e", {"x": 1})
    h2 = entry_hash(0, GENESIS, "a", "e", {"x": 1})
    assert h1 == h2
