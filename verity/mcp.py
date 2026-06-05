"""verity MCP server — the verification gate, as a tool any agent can call.

Exposes the Reality Anchor over MCP (stdio). Give it a result-claim and it
answers REFUSE / WARN / PASS against ground truth — so an agent can check itself
*before* believing a number. Also verifies hash-chained audit logs.

Run:        verity-mcp                       (after `pip install "verity-core[mcp]"`)
Register:   add to .mcp.json as an stdio server with command "verity-mcp".

The heavy ``mcp`` dependency is imported lazily, so importing this module (and the
rest of verity-core) never requires it.
"""
from __future__ import annotations

import json
from pathlib import Path

from .audit import AuditChain
from .gate import check, format_block, format_verify_block, load_truth

_DEFAULT_TRUTH = Path(__file__).resolve().parent / "truth.yaml"


def build_server():
    from mcp.server.fastmcp import FastMCP  # lazy — only needed to actually serve

    server = FastMCP("verity")

    @server.tool()
    def verify_claim(claim: dict, truth_path: str = "") -> str:
        """Check an empirical result-claim against ground truth.

        Returns a VERIFIED block with the verdict (REFUSE | WARN | PASS). Use this
        before believing any reported number. Example claim:
        {"name": "x", "accuracy": 0.72, "sample_size": 18, "out_of_sample": false,
         "leakage_checked": false, "text": "72% win rate backtest"}
        """
        truth = load_truth(truth_path or _DEFAULT_TRUTH)
        return format_block(claim, check(claim, truth))

    @server.tool()
    def verify(claim: dict, evidence: dict | None = None, prior: dict | None = None,
               sources: list | None = None, truth_path: str = "") -> str:
        """Verify a claim across all applicable dimensions before acting on it.

        EMPIRICAL hygiene always; EVIDENCE-match if `evidence` is given (deterministic
        field reconciliation, not fuzzy); CONSISTENCY vs `prior` if given. Returns a
        multi-dimension VERIFIED block (overall REFUSE | WARN | PASS). This is the
        recommended agent entrypoint; `verify_claim` remains for empirical-only checks.
        """
        truth = load_truth(truth_path or _DEFAULT_TRUTH)
        from .verify import verify as _verify
        return format_verify_block(claim, _verify(
            claim, evidence=evidence, prior=prior, sources=sources, truth=truth))

    @server.tool()
    def gate_thresholds(truth_path: str = "") -> str:
        """Show the active verification thresholds and ground-truth facts (JSON)."""
        return json.dumps(load_truth(truth_path or _DEFAULT_TRUTH), indent=2)

    @server.tool()
    def audit_verify(path: str) -> str:
        """Verify a hash-chained audit log is intact / tamper-evident."""
        ok, msg = AuditChain(path).verify()
        return f"{'OK' if ok else 'BROKEN'}: {msg}"

    return server


def main() -> None:
    build_server().run()


if __name__ == "__main__":
    main()
