"""verity-core — the verification primitive.

A Reality Anchor that refuses to believe unverified result-claims, plus a
tamper-evident, append-only audit chain. The same discipline, in one place.

As a library::

    from verity import check, load_truth, AuditChain
    result = check(claim, load_truth("truth.yaml"))   # REFUSE | WARN | PASS

As an MCP tool (any agent can call the gate to check itself)::

    verity-mcp        # console script — register in .mcp.json
"""
from .audit import AuditChain, entry_hash
from .gate import check, format_block, load_truth

__version__ = "0.1.0"
__all__ = ["check", "load_truth", "format_block", "AuditChain", "entry_hash"]
