# External benchmark — real claims, independent labels

`verity eval` is a *circular* regression (the gate graded against its own rules). **This** is the
opposite: published result-claims with their real statistics **and an independent, real-world label
of whether the claim held up** — sourced from large, pre-registered replication efforts, not from us.

## The data

`score-replication.jsonl` — 132 social-science result-claims (one per original finding), each with
the original effect size, sample size, and p-value, plus `replicated: true/false`, the verdict of a
high-powered independent replication.

- **Source:** the DARPA SCORE Phase-1 test set, as consolidated in the **FORRT Replication Database
  (FReD)**.
- **License:** **CC-BY 4.0** — redistributed here with attribution.
- **Cite:** Röseler, L. et al. *The FORRT Replication Database.* Journal of Open Psychology Data
  (2024). https://openpsychologydata.metajnl.com/articles/10.5334/jopd.101 · data
  https://osf.io/9r62x/ · pipeline https://github.com/forrtproject/fred-data · DARPA SCORE
  https://www.cos.io/score
- Effect sizes harmonized to a Cohen's-d scale where convertible (d, f², r); claims whose effect
  type is not on a comparable scale carry no `effect_size` and are scored on sample + p-value only.

## The result (run `verity eval-external`)

Scored under `replication-truth.yaml` (verity's defaults; the ML-only checks disabled as N/A):

| | flag-rate (WARN/REFUSE) |
|---|---|
| claims that **FAILED** to replicate | **33%** |
| claims that **REPLICATED** | **23%** |

**A claim that failed to replicate is ~1.66× more likely to be flagged than one that held up
(+10 percentage points).** The signal runs in the right direction and is driven by exactly the
predictors the replication literature blames — under-power, small samples, small effects.

## What this does and does not show — honestly

- **It is real, external, and non-circular.** The labels come from independent replications, not from
  verity's rules. This is genuine evidence the checks track real trustworthiness.
- **The effect is modest, by nature.** verity sees only the *disclosed statistics*. Replication
  failure also stems from causes a stats-gate cannot see — questionable research practices, fraud,
  context-sensitivity, publication bias. verity catches the *statistically-detectable* slice
  (mainly under-power), which is why the separation is ~10 points, not 50.
- **Coverage is replication-targeted social science, not "all claims in the wild."** A PASS here
  means "no statistical red flag," not "will replicate."
- **It is not a leaderboard.** No threshold was tuned to this data; the numbers are what the default
  gate produces. Improving them honestly means better *checks*, validated on *held-out* labels — not
  fitting this set.
