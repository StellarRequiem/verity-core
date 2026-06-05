# External benchmark — real claims, independent labels

`verity eval` is a *circular* regression (the gate graded against its own rules). **This** is the
opposite: published result-claims with their real statistics **and an independent, real-world label
of whether the claim held up** — from large, pre-registered replication efforts, not from us.

## The data

`fred-replication.jsonl` — **1,772 social-science result-claims** (one per original finding), each
with the original effect size, sample size, and p-value, plus `replicated: true/false`, the verdict
of an independent high-powered replication (985 replicated / 787 failed). `score-replication.jsonl`
is the balanced 132-case DARPA-SCORE subset.

- **Source:** the **FORRT Replication Database (FReD)**, consolidating RPP, Many Labs, SSRP, RP:CB,
  DARPA SCORE, and more.
- **License:** **CC-BY 4.0** — redistributed here with attribution.
- **Cite:** Röseler, L. et al. *The FORRT Replication Database.* Journal of Open Psychology Data
  (2024). https://openpsychologydata.metajnl.com/articles/10.5334/jopd.101 · data
  https://osf.io/9r62x/ · pipeline https://github.com/forrtproject/fred-data · DARPA SCORE
  https://www.cos.io/score
- Effect sizes harmonized to a Cohen's-d scale where convertible (d, f², r); claims whose effect type
  is not on a comparable scale carry no `effect_size` and are scored on sample + p-value only.

## The result (`verity eval-external`)

Scored under `replication-truth.yaml` (verity's defaults; ML-only checks disabled as N/A — **not
tuned to the data**):

| | flag-rate (WARN/REFUSE) |
|---|---|
| claims that **FAILED** to replicate | **61.1%** |
| claims that **REPLICATED** | **52.8%** |

**verity flags a failed-to-replicate claim significantly more often than one that held up** —
separation **+8.3 pp**, odds **1.41×**, two-proportion **z = 3.51, p = 0.00044** (n = 1,772).
This is real, external, *statistically significant* evidence that the gate's checks track real-world
trustworthiness — in the direction the replication literature predicts (under-power, small samples).

## The honest arc — and why it's the whole point

1. The 132-case SCORE subset only **hinted** at this (+10 pp, z = 1.30, **p = 0.19**). We did not
   publish "verity predicts replication!" — instead `verity verify` flagged **our own claim** as
   under-powered (*"z < 2; n=132 needs ~762"*). We held our result to our own bar.
2. We got the power (the full 1,772-case corpus). **The signal held up at significance** (p < 0.001).
3. **Significant ≠ large.** The effect is *modest* (odds 1.41×). Run `verity verify` on this very
   result and it **PASSES significance but WARNs on effect size** (0.083 < 0.1 — "practically
   modest"). The tool confirms its signal is real **and** refuses to oversell its size.

A verifier that flags its own under-powered claim, gets the data, confirms the signal, **and then
flags that the confirmed effect is still modest** — that discipline, made mechanical, is the point.

## What this does and does not show — honestly

- **Real, external, significant — but modest.** Labels come from independent replications, not the
  gate's rules. The +8 pp / 1.41× gap is significant (p < 0.001) yet small: verity catches the
  *statistically-detectable* slice of replication failure (mainly under-power), not fraud,
  context-sensitivity, or publication bias, which it cannot see.
- **Coverage is replication-targeted social science**, not "all claims in the wild." A PASS means
  "no statistical red flag," not "will replicate."
- **Not a leaderboard.** No threshold was tuned to this data; the numbers are what the default gate
  produces. Improving them honestly means better *checks* validated on *held-out* labels — not
  fitting this set.
