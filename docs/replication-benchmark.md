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

## The headline — significant, but modest

| | flagged (WARN/REFUSE) |
|---|---|
| claims that **failed** to replicate | **61.1%** |
| claims that **replicated** | **52.8%** |

Separation **+8.3 pp**, odds **1.41×**, **z = 3.51, p = 0.00044**. So *yes* — verity's checks
**significantly** predict real replication outcomes. But modestly: 1.41× is real, not large.

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

## Can we do better? An honest held-out test

70/30 split; a 3-feature logistic (log-sample, effect, log-p) fit on **train**, scored on **held-out test** (n=108):

| ranker | held-out AUC |
|---|---|
| sample size alone | 0.674 |
| the verity gate | 0.638 |
| fitted logistic | **0.707** |

So there is **modest, validated headroom** (≈ +0.07 AUC) — mostly from treating the p-value
*continuously* (a p of 0.001 is more robust than a marginal 0.04) instead of a binary cutoff. The
held-out sample is small, so treat the exact number as indicative.

**We did not bake that model into verity.** A logistic fit to one corpus of social-science
replications would overfit to one domain *and* violate the tool's whole principle — it would be a
verifier shipping an un-validated, corpus-tuned number, the exact thing it exists to catch. The
headroom is a **finding and a roadmap** (a *principled, general* continuous-significance check is
worth exploring), not a benchmark-flattering change.

## The meta-honesty

The first run was under-powered (132 cases, z = 1.30, p = 0.19) — and `verity verify` flagged **our
own claim** as not-yet-established. We got the full corpus; the signal held at significance. Then
`verity verify` on the *confirmed* result **passed significance but WARNed the effect is modest**
(1.41×, effect 0.083 < 0.1). At every step the tool was held to its own bar — including about itself.

## Takeaway

Lightweight automated checks on result-claims **do** carry real, statistically-significant signal
about whether a result will replicate — but the honest version is narrower than the headline: it is
mostly *"this study was under-powered,"* it is modest, and it is domain-dependent. The contribution
isn't a magic oracle. It's a verifier rigorous and honest enough to tell you exactly that — including
where it falls short, and including about its own claims.

---
*Reproduce: `verity eval-external`. Data + method: [`eval/external/`](../eval/external/SOURCES.md).
Built by Alex Price ([@StellarRequiem](https://github.com/StellarRequiem) ·
[𝕏](https://x.com/StellarRequiem)).*
