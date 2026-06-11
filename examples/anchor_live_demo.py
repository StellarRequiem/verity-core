"""Live Reality-Anchor demo — catch a real fabrication against the running repo.

Three claims about verity-core's OWN code, each grounded by git (the committed truth):
  * a TRUE claim            -> PASS
  * a FABRICATED claim      -> REFUSE  (the hallucination is caught — git says otherwise)
  * an UNGROUNDABLE claim   -> UNVERIFIABLE (no source can adjudicate -> don't believe)

Then the ledger's tamper-evident chain is verified. No LLM anywhere — the anchor only
asks the running system.  Run:  python examples/anchor_live_demo.py
"""
from pathlib import Path
import tempfile

from verity.anchor import GitSource, anchor
from verity.audit import AuditChain

REPO = Path(__file__).resolve().parent.parent  # the verity-core checkout

# proof: read verity/__init__.py at HEAD, capture __version__ into field "version"
PROOF = [{"source": "git", "path": "verity/__init__.py", "ref": "HEAD",
          "field": "version", "pattern": r'__version__ = "([^"]+)"'}]

TRUE_CLAIM    = {"name": "verity version (true)",  "version": "0.1.0", "proof": PROOF}
FABRICATED    = {"name": "verity version (fabricated)", "version": "9.9.9", "proof": PROOF}
UNGROUNDABLE  = {"name": "ungroundable", "version": "0.1.0",
                 "proof": [{"source": "git", "path": "verity/__init__.py", "ref": "HEAD",
                            "field": "version", "pattern": r"NoSuchToken_=_\"([^\"]+)\""}]}


def main() -> int:
    git = GitSource(REPO)
    ledger = AuditChain(Path(tempfile.gettempdir()) / "anchor_demo_ledger.jsonl")
    # fresh ledger each run so the demo is reproducible
    if ledger.path.exists():
        ledger.path.unlink()

    cases = [("TRUE", TRUE_CLAIM, "PASS"),
             ("FABRICATED", FABRICATED, "REFUSE"),
             ("UNGROUNDABLE", UNGROUNDABLE, "UNVERIFIABLE")]

    print("=== live anchor vs the running repo (single git source, min_sources=1) ===")
    ok = True
    for label, claim, expected in cases:
        r = anchor(claim, [git], ledger=ledger, min_sources=1)
        flag = "OK" if r.verdict == expected else "*** MISMATCH ***"
        print(f"  {label:13} -> {r.verdict:13} (expected {expected})  {flag}")
        print(f"                  git returned: {r.fetched.get('git')}  ::  {r.detail}")
        ok &= (r.verdict == expected)

    intact, msg = ledger.verify()
    print(f"\n  ledger: {msg}  -> {'INTACT ✓' if intact else '*** TAMPERED ***'}")
    print("  (every verdict is now an immutable, hash-chained ledger entry)")
    return 0 if (ok and intact) else 1


if __name__ == "__main__":
    raise SystemExit(main())
