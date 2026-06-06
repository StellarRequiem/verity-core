# Does a result-claim linter predict replication?

`verity` is a CI gate that flags result-claims that *look* statistically untrustworthy — samples too
small, p-values that don't clear the bar, effects too small to matter. The obvious question: **do
those automated checks actually predict whether a result holds up?** So we benchmarked it against
reality — not against its own rules.

## The benchmark

**1,772 published social-science findings** from the [FORRT Replication Database](https://openpsychologydata.metajnl.com/articles/10.5334/jopd.101)
(CC-BY 4.0; consolidating RPP, Many Labs, SSRP, RP:CB, DARPA SCORE). Each carries its original effect
size, sample size, and p-value — **and an independent label**: a high-powered replication either
succeeded (985) or failed (787). We scored each *original* claim with verity's default checks (the
ML-specific out-of-sample / leakage checks disabled as N/A; **no threshold tuned to the data**) and
asked: does the gate flag the failures more than the survivors? Run it yourself: `verity eval-external`.

## The headline — significant, and then substantial

The **base** statistical checks already flag a failed-to-replicate claim more than a survivor — but
modestly. Mining *why* (below) pointed to one principled, held-out-validated improvement that nearly
doubled the gap:

| gate | failed flagged | replicated flagged | separation | odds | z |
|---|---|---|---|---|---|
| base checks | 61.1% | 52.8% | +8.3 pp | 1.41× | 3.51 |
| **+ marginal-significance** | **78.3%** | **62.7%** | **+15.5 pp** | **2.14×** | **7.06** |

(n = 1,772; final p = 1.6 × 10⁻¹²). The number matters less than *how* we got it: by adding a check
the literature and the held-out data both endorse — never by fitting a knob to this benchmark.

## What's doing the work (and what isn't)

The per-check breakdown is humbling:

| check | Δ flag-rate (failed − replicated) |
|---|---|
| **sample_size** | **+7.9%** ← essentially the whole signal |
| significance (p > 0.05) | −1.6% (backfires) |
| effect_size floor | +0.1% |
| underpowered | −0.3% |

**Almost the entire signal is one check: sample size.** Failed studies simply had smaller samples
(median 85 vs 101). Their effect sizes (0.63 vs 0.62) and p-values (0.01 vs 0.01) are
indistinguishable. The fancier rigor checks add ~nothing here; the binary p>0.05 check even
backfires. And it's **discipline-dependent** — strong in Social Psychology (+12 pp) and Marketing
(+24 pp), but it *reverses* in Cognitive Psychology (−20 pp). A universal "will-replicate" oracle
this is not.

## Two ways to improve — one honest, one not

The mining said the binary `p > 0.05` cut is the wrong tool while the p-value *continuously* carries
signal. Two ways to exploit that — and the choice between them is the whole point.

**The overfit (declined).** A 3-feature logistic (log-sample, effect, log-p) fit on a train split
scored **0.707** held-out AUC vs the gate's 0.638 — ~+0.07 headroom. But a model fit to one corpus
of social-science replications would overfit to one domain *and* violate the tool's whole principle:
a verifier shipping an un-validated, corpus-tuned number is the exact thing it exists to catch. We
did **not** bake it in.

**The principled (added).** The replication literature is unambiguous that *marginal* p-values —
"just significant," 0.01 < p ≤ 0.05 — are fragile. We tested that on the corpus before writing a
line of code: marginal claims replicated **42% vs 59%** for strongly-significant ones (p ≤ 0.01) — a
16-pt gap, z = 6.1, **confirmed out-of-sample** (held-out 48% vs 62%, z = 2.8). So we added exactly
one check — `marginal_significance` (a MEDIUM caution), using the standard **0.01** literature cut,
*not* a threshold searched over the data. That single check took the gate from 1.41× to **2.14×**.

The difference is everything: we improved the gate with a check the *literature and the held-out
data both endorse* — not by fitting a knob to make this benchmark look good. The first would be
science; the second would be the thing verity exists to flag.

## The meta-honesty

The first run was under-powered (132 cases, z = 1.30, p = 0.19) — and `verity verify` flagged **our
own claim** as not-yet-established. We got the full corpus; the base signal held at significance, but
`verity verify` on it still **WARNed the effect was modest** (1.41×, separation 0.083 < the 0.1
floor). We didn't bury that WARN — we *answered* it the principled way: the marginal-significance
check lifted the gate to 2.14× (separation 0.155, clearing the floor). At every step the tool was
held to its own bar — including when its verdict on its own result pointed straight at the next fix.

## Takeaway

Lightweight automated checks on result-claims **do** carry real, statistically-significant signal
about whether a result will replicate — and with the right *principled* checks the signal is
substantial (2.14× odds), not just present. But the discipline is the actual contribution: mine
where the signal really lives (mostly under-power and marginal significance), improve only with
checks the literature **and** held-out data both endorse, and refuse the corpus-fitted shortcut even
when it would flatter the number. A verifier honest enough to hold itself to that — to flag its own
under-powered claim, then improve itself the principled way — is one you can trust to do the same to
your results.

**Honest gaps.** Validated on one corpus (FORRT, social science) with a held-out split, not yet on an
independent corpus; a PASS means "no statistical red flag," not "will replicate"; the gate still sees
only the *disclosed* statistics, so QRPs, fraud, and context-sensitivity remain invisible to it.

---
*Reproduce: `verity eval-external`. Data + method: [`eval/external/`](../eval/external/SOURCES.md).
Built by Alex Price ([@StellarRequiem](https://github.com/StellarRequiem) ·
[𝕏](https://x.com/StellarRequiem)).*
