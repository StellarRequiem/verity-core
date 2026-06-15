"""Hash-linked, append-only audit chain.

Each entry commits to the previous one by hash, so any after-the-fact edit to an
earlier record breaks the chain and ``verify()`` catches it. The timestamp is
recorded but deliberately NOT part of the hash, so re-stamping can't silently
rewrite the links.

Honest threat model — read this before you trust it:

* **UNKEYED (default): integrity, not tamper-evidence.** The hash is plain
  SHA-256, so anyone who can rewrite the file can recompute a fully
  self-consistent chain from any edit point forward and ``verify()`` will accept
  it. That catches accidental corruption, mid-chain truncation, reordering, and
  edit-and-forget — *not* a determined rewrite by someone with write access.
* **KEYED (``AuditChain(path, key=...)``): tamper-evidence.** Each entry also
  carries an HMAC-SHA256 over its ``entry_hash``. A rewrite then needs the key,
  so a verifier who holds the key — and whom the writer cannot impersonate —
  gets genuine tamper-evidence. Key custody is the caller's job: the key must
  live with the *verifier*, not the writer, or it buys nothing.
* **ANCHORING (``head()`` + ``verify(expected_head=...)``): tamper-evidence
  without a shared key.** ``head()`` returns the current tip hash; publish it to
  an append-only/witnessed place and check it back to close the tail-truncation
  and wholesale-rewrite gaps.

Unkeyed = integrity. Keyed and/or anchored = tamper-evidence. Don't claim the
latter from the former.
"""
from __future__ import annotations

import hashlib
import hmac as _hmac
import json
import threading
from datetime import datetime, timezone
from pathlib import Path

GENESIS = "GENESIS"

# The exact set of fields a well-formed unkeyed record carries (``hmac`` is added
# only on keyed chains). Pinned so the on-disk format can't drift unnoticed.
RECORD_FIELDS = frozenset(
    {"seq", "prev_hash", "actor", "event_type", "event_data", "timestamp", "entry_hash"})


def _now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


def entry_hash(seq: int, prev_hash: str, actor: str,
               event_type: str, event_data: dict) -> str:
    canonical = json.dumps(
        {"seq": seq, "prev_hash": prev_hash, "actor": actor,
         "event_type": event_type, "event_data": event_data},
        sort_keys=True, separators=(",", ":"), ensure_ascii=False)
    return hashlib.sha256(canonical.encode("utf-8")).hexdigest()


def entry_hmac(key: bytes, entry_hash_hex: str) -> str:
    """Authenticity tag over an entry's hash. Only a key-holder can produce it,
    which is what upgrades the unkeyed integrity chain to tamper-evidence. Binding
    to ``entry_hash`` suffices because that hash already commits to seq, prev_hash,
    actor, event_type and event_data."""
    return _hmac.new(key, entry_hash_hex.encode("utf-8"), hashlib.sha256).hexdigest()


class AuditChain:
    """Append-only JSONL chain at ``path``. Thread-safe within a process.

    Unkeyed by default (integrity). Pass ``key=<bytes>`` for HMAC tamper-evidence:
    the keyed path adds an ``hmac`` field and leaves the unkeyed on-disk format
    byte-for-byte unchanged, so chains written without a key keep verifying exactly
    as before. The in-process ``RLock`` does not guard against a second *process*
    appending concurrently — honour the single-writer rule for that.
    """

    def __init__(self, path: str | Path, *, key: bytes | None = None) -> None:
        self.path = Path(path)
        self._key = key
        self._lock = threading.RLock()

    def read(self) -> list[dict]:
        if not self.path.exists():
            return []
        return [json.loads(line) for line
                in self.path.read_text(encoding="utf-8").splitlines() if line.strip()]

    def head(self) -> str:
        """The current tip hash (last ``entry_hash``), or ``GENESIS`` if empty.
        Publish this to an external witness to anchor the chain against a rewrite
        that an unkeyed ``verify()`` cannot otherwise detect."""
        rows = self.read()
        return rows[-1]["entry_hash"] if rows else GENESIS

    def append(self, event_type: str, event_data: dict, actor: str = "agent") -> dict:
        with self._lock:
            rows = self.read()
            seq = len(rows)
            prev = rows[-1]["entry_hash"] if rows else GENESIS
            h = entry_hash(seq, prev, actor, event_type, event_data)
            entry = {"seq": seq, "prev_hash": prev, "actor": actor,
                     "event_type": event_type, "event_data": event_data,
                     "timestamp": _now_iso(), "entry_hash": h}
            if self._key is not None:
                entry["hmac"] = entry_hmac(self._key, h)
            self.path.parent.mkdir(parents=True, exist_ok=True)
            with self.path.open("a", encoding="utf-8") as f:
                f.write(json.dumps(entry, ensure_ascii=False) + "\n")
            return entry

    def verify(self, *, expected_head: str | None = None,
               min_entries: int | None = None) -> tuple[bool, str]:
        """Walk the chain and check integrity, returning ``(ok, message)``.

        Default behaviour is unchanged: seq order, prev-hash linkage, and per-entry
        content hash. Additive, opt-in stronger checks:

        * if this chain has a ``key``, each entry's ``hmac`` is verified too
          (tamper-evidence — catches a rewrite that recomputed the unkeyed hash);
        * ``min_entries`` rejects a chain shorter than expected (tail truncation,
          which the bare hash-walk cannot see);
        * ``expected_head`` rejects a chain whose tip is not the anchored hash.
        """
        prev = GENESIS
        rows = self.read()
        for i, r in enumerate(rows):
            if r.get("seq") != i:
                return False, f"seq mismatch at index {i}"
            if r.get("prev_hash") != prev:
                return False, f"broken link at seq {i}"
            h = entry_hash(i, prev, r["actor"], r["event_type"], r["event_data"])
            if r.get("entry_hash") != h:
                return False, f"hash mismatch at seq {i} — tampered"
            if self._key is not None:
                if "hmac" not in r:
                    return False, f"missing hmac at seq {i} — unkeyed entry in keyed chain"
                if not _hmac.compare_digest(r["hmac"], entry_hmac(self._key, h)):
                    return False, f"hmac mismatch at seq {i} — forged or wrong key"
            prev = r["entry_hash"]
        if min_entries is not None and len(rows) < min_entries:
            return False, f"truncated: {len(rows)} entries < expected {min_entries}"
        if expected_head is not None and prev != expected_head:
            return False, f"head mismatch: expected {expected_head[:12]}…, got {prev[:12]}…"
        return True, f"intact: {len(rows)} entries"
