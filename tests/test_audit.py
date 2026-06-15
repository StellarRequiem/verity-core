"""The audit chain must verify clean and detect any tampering.

Beyond the base integrity walk, these pin the honest threat model: the unkeyed
chain is integrity-only (a rehashed forgery fools it), while an HMAC-keyed chain
is tamper-evident; anchoring (head/expected_head) and min_entries close the
tail-truncation gap the bare walk cannot see. The unkeyed on-disk format stays
byte-for-byte unchanged.
"""
import json

from verity.audit import GENESIS, RECORD_FIELDS, AuditChain, entry_hash, entry_hmac


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


# ── additive primitive surface ────────────────────────────────────────────────

def test_unkeyed_record_is_byte_format_unchanged(tmp_path):
    """The default (unkeyed) on-disk record must carry exactly the original
    fields and no `hmac` — existing ledgers must keep verifying unchanged."""
    p = tmp_path / "u.jsonl"
    e = AuditChain(p).append("evt", {"x": 1})
    assert "hmac" not in e
    row = json.loads(p.read_text().splitlines()[0])
    assert set(row) == set(RECORD_FIELDS)


def test_head_is_genesis_when_empty_then_tracks_tip(tmp_path):
    c = AuditChain(tmp_path / "e.jsonl")
    assert c.head() == GENESIS
    e1 = c.append("evt", {"x": 1})
    assert c.head() == e1["entry_hash"]
    e2 = c.append("evt", {"x": 2})
    assert c.head() == e2["entry_hash"]


def test_min_entries_detects_tail_truncation(tmp_path):
    """Dropping whole records off the tail leaves an internally-valid chain the
    bare walk accepts; min_entries is the anti-truncation guard."""
    p = tmp_path / "t.jsonl"
    c = AuditChain(p)
    for x in range(3):
        c.append("evt", {"x": x})
    lines = p.read_text().splitlines()
    p.write_text("\n".join(lines[:-1]) + "\n")          # drop the last record
    assert AuditChain(p).verify()[0] is True            # plain walk can't see it
    ok, msg = AuditChain(p).verify(min_entries=3)
    assert ok is False and "truncated" in msg


def test_expected_head_anchors_against_tail_rewrite(tmp_path):
    p = tmp_path / "h.jsonl"
    c = AuditChain(p)
    c.append("evt", {"x": 1})
    c.append("evt", {"x": 2})
    anchored = c.head()                                  # publish this to a witness
    assert c.verify(expected_head=anchored)[0]
    c.append("evt", {"x": 3})                            # chain legitimately grows…
    ok, msg = c.verify(expected_head=anchored)           # …but the anchor flags drift
    assert ok is False and "head mismatch" in msg
    assert c.head() != anchored


def test_keyed_hmac_catches_a_rehashed_forgery_that_fools_unkeyed(tmp_path):
    """The point of keying: an adversary who can rewrite the file and recompute
    the *public* unkeyed hashes defeats an unkeyed chain, but cannot forge the
    HMAC, so a keyed verify catches it."""
    p = tmp_path / "k.jsonl"
    key = b"verifier-held-secret"
    c = AuditChain(p, key=key)
    c.append("evt", {"x": 1})
    c.append("evt", {"x": 2})
    assert c.verify()[0]

    rows = [json.loads(line) for line in p.read_text().splitlines()]
    rows[0]["event_data"] = {"x": 999}                   # the forgery
    prev = GENESIS                                       # recompute the unkeyed chain…
    for i, r in enumerate(rows):
        r["seq"] = i
        r["prev_hash"] = prev
        r["entry_hash"] = entry_hash(i, prev, r["actor"], r["event_type"], r["event_data"])
        prev = r["entry_hash"]                            # …leaving the stale hmac fields
    p.write_text("\n".join(json.dumps(r) for r in rows) + "\n")

    assert AuditChain(p).verify()[0] is True             # unkeyed chain is fooled
    ok, msg = AuditChain(p, key=key).verify()            # keyed chain is not
    assert ok is False and "hmac" in msg


def test_wrong_key_fails_verification(tmp_path):
    p = tmp_path / "w.jsonl"
    AuditChain(p, key=b"right-key").append("evt", {"x": 1})
    ok, msg = AuditChain(p, key=b"wrong-key").verify()
    assert ok is False and "hmac" in msg


def test_keyed_chain_verifies_clean_with_its_key(tmp_path):
    p = tmp_path / "ok.jsonl"
    key = b"k"
    c = AuditChain(p, key=key)
    e = c.append("evt", {"x": 1})
    assert e["hmac"] == entry_hmac(key, e["entry_hash"])
    assert c.verify()[0] is True


def test_keyed_verify_rejects_unkeyed_entry(tmp_path):
    """A keyed chain must not silently accept a record written without an hmac."""
    p = tmp_path / "mix.jsonl"
    AuditChain(p).append("evt", {"x": 1})                # unkeyed write
    ok, msg = AuditChain(p, key=b"k").verify()
    assert ok is False and "missing hmac" in msg
