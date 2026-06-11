# The Reality Anchor — phased build spec

A live, cross-referential reality anchor that catches hallucinations by reconciling every
actionable claim against **non-generative ground truth** — so that even with many agents on one
process, agent *agreement* counts for nothing and reconciliation against the running system counts
for everything.

## Locked decisions (operator, 2026-06-08)
- **Trust root / first sources:** Yggdrasil **live DB** + **git** (hard-to-forge, already running).
- **Home:** `verity-core` (this package — it already calls itself "A Reality Anchor").
- **First claim-kinds:** numbers + file-state.
- **Cross-referential minimum:** **2** independent sources to corroborate a PASS.

## Architecture — compose, don't reinvent
verity-core already provides the two hardest pieces; the anchor adds the one missing layer.

| Layer | Where | Role |
|---|---|---|
| **Comparator** | `verity.verify` (existing) | **Pure, deterministic, NO I/O.** Reconciles a claim against *resolved* facts. GROUNDING: a source asserting a different value → CRITICAL → REFUSE. |
| **Ledger** | `verity.audit.AuditChain` (existing) | Hash-chained, append-only, tamper-evident. `verify()` catches any after-the-fact edit. |
| **Anchor** | `verity.anchor` (**new**) | The **I/O layer**: `Source.fetch()` pulls live truth from the running system → feeds `verify()` → cross-source policy → logs to the ledger. No LLM in the loop. |

**Why this works at scale:** the verifier never asks a model, only the running system; the grader is
isolated from the generator (un-gameability lives in that isolation — proven by the arena test). A
claim that ≥`min_sources` independent sources can't corroborate is **UNVERIFIABLE** = *don't believe
it*, and does not propagate.

## Firewall split (verity-core is PUBLIC; Yggdrasil DB is LOCAL)
- **Public-safe engine** (in-repo): `Source` ABC, `GitSource`, `FileSource`, `anchor()`, `_decide`, ledger glue. Generic git/file I/O — safe to publish.
- **Local-only adapter** (gitignored, built next): `YggdrasilDBSource` — binds to the local paper-trading DB schema. Stays off the public repo.
- **No push.** The operator publishes the engine when ready; the agent never pushes / flips visibility.

## Phased priority list
| P | Phase | Status |
|---|---|---|
| **P0** | Pin sources + **MVVC**: single/over-min source → verify → ledger, one claim-kind | ✅ **DONE** — caught a real fabrication (see below) |
| **P0** | Yggdrasil **DB source** (local, gitignored) — the 2nd independent leg | next |
| **P1** | **Cross-referential** corroboration: ≥2 *independent* sources must agree; per-key counting | partial (count is per-source; per-key = this phase) |
| **P1** | **Multi-workflow cross-checking** — producer / verifier / adversary / consistency workflows check each other (RAM-capped) | — |
| **P2** | **Tool-contract verification** — emergent tool admitted only with a verified contract + provenance → experimental ring | — |
| **P2** | **Tool governance + registry** — kernel/ring split, promotion gate (operator-enact for gate-touching), provenance ledger | — |
| **P3** | **Scale + calibration** — N-agent run, anchor mandatory, calibrate its own false-pos/neg + Brier, kill-switch | — |

## P0 MVVC — proof it bites (the advancement gate)
`examples/anchor_live_demo.py`, single `GitSource` vs. this repo's own committed code:
- TRUE claim (`version == 0.1.0`) → **PASS** (corroborated by git)
- FABRICATED claim (`version == 9.9.9`) → **REFUSE** (git asserts otherwise — the hallucination is caught)
- UNGROUNDABLE claim → **UNVERIFIABLE** (no source can adjudicate → not believed)
- Ledger: 3 entries, hash-chain **intact**.

Tested: `tests/test_anchor.py` 6/6 (incl. 2-source agree/contradict/under-corroborate, crashing-source-is-silent, tamper-evidence); full verity suite 289/289.

## Honest gaps (must close before trusting it wide)
1. **Cross-ref is currently per-*source*, not per-*key*.** A PASS today means ≥`min_sources` returned facts and none contradicted; it does not yet require ≥`min_sources` to assert the *same key*. → P1 tightening.
2. **Comparator, not oracle.** It authenticates claims *against the ground truth it's fed*. If the trust root is poisoned (e.g. a DB written by a hallucinating agent), it verifies against the poison. → the trust root must be operator-pinned + hardest-to-forge; the Yggdrasil DB leg must read the *daemon-authoritative* state, not agent-written rows.
3. **Only git so far.** Real cross-referential robustness needs the 2nd independent leg (Yggdrasil DB) — next.
4. **Ungroundable ≠ false.** Claims with no checkable referent return UNVERIFIABLE; that's protective, not complete.
