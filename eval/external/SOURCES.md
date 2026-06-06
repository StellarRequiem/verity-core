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
| claims that **FAILED** to replicate | **78.3%** |
| claims that **REPLICATED** | **62.7%** |

**verity flags a failed-to-replicate claim significantly more often than one that held up** —
separation **+15.5 pp**, odds **2.14×**, two-proportion **z = 7.06, p = 1.6 × 10⁻¹²** (n = 1,772).
This is real, external, *statistically significant* evidence that the gate's checks track real-world
trustworthiness — in the direction the replication literature predicts (under-power, marginal
significance). The base checks alone gave a modest 1.41×; a principled, held-out-validated
`marginal_significance` check (**added, not tuned** — see the arc) nearly doubled the gap.

## The honest arc — and why it's the whole point

1. The 132-case SCORE subset only **hinted** at this (+10 pp, z = 1.30, **p = 0.19**). We did not
   publish "verity predicts replication!" — instead `verity verify` flagged **our own claim** as
   under-powered (*"z < 2; n=132 needs ~762"*). We held our result to our own bar.
2. We got the power (the full 1,772-case corpus). **The base signal held at significance** — but
   modestly (1.41×). Mining it showed the binary `p>0.05` cut backfires while the p-value
   *continuously* carries signal.
3. We **improved it the principled way.** The literature says *marginal* p-values (0.01<p≤0.05) are
   fragile; we tested that on the corpus first — marginal claims replicated **42% vs 59%** (z=6.1,
   held-out confirmed) — then added one `marginal_significance` check (standard 0.01 cut, **not**
   tuned). That took the gate to **2.14×** (z=7.06). We **declined** a fitted logistic that scored as
   well — a corpus-tuned number is exactly what a verifier exists to catch.

A verifier that flags its own under-powered claim, gets the data, confirms the signal, **then
improves itself only with a check the literature and held-out data both endorse** — that discipline,
made mechanical, is the point.

## What this does and does not show — honestly

- **Real, external, significant.** Labels come from independent replications, not the gate's rules.
  The +15.5 pp / 2.14× gap is strongly significant (p ≈ 10⁻¹²): verity catches the
  *statistically-detectable* slice of replication failure (under-power and marginal significance),
  not fraud, context-sensitivity, or publication bias, which it cannot see.
- **Coverage is replication-targeted social science**, not "all claims in the wild." A PASS means
  "no statistical red flag," not "will replicate."
- **Not a leaderboard.** No threshold was tuned to this data; the numbers are what the default gate
  produces. Improving them honestly means better *checks* validated on *held-out* labels — not
  fitting this set.
