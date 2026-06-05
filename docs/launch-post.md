# A linter for your ML result-claims

Your README says **95% accuracy**. Your model card says **0.98 AUC**. Your paper says **SOTA**.

Did anyone *check*?

## The problem

ML and research repos report their headline numbers in prose — a README badge, a model card, a
results table. Almost nobody verifies those numbers against basic statistical hygiene before they
ship. So the claims that slip through are exactly the dangerous ones:

- **No lift over the base rate.** A fraud detector at "98.5% accuracy" when fraud is 1.5% of the
  data is barely better than `return "not fraud"`.
- **Tiny samples.** A metric on 40 rows is noise wearing a number.
- **In-sample / leaked.** Evaluated on data the model trained on.
- **Best-of-N fishing.** The winning config out of 50 tried, reported as if it were the only one.

A human reviewer sees a big confident number and nods. The number is the thing that should have
been gated — and wasn't.

## The fix: gate result-claims like you gate code

[**verity-check**](https://github.com/StellarRequiem/verity-core) is a CI Action that does for
result-claims what a linter does for code. Put your metrics in a `claims.jsonl`:

```json
{"name": "sentiment-clf v2", "accuracy": 0.873, "sample_size": 5000, "out_of_sample": true, "leakage_checked": true, "base_rate": 0.51}
```

Add six lines of workflow:

```yaml
- uses: StellarRequiem/verity-core@v0.1.0
  with:
    claims: results/claims.jsonl
    truth:  results/truth.yaml
```

Now every pull request that touches your numbers gets checked. Exit code gates CI:
**0 PASS · 1 WARN · 2 REFUSE.**

## Watch it catch a real mistake

In [**verity-demo**](https://github.com/StellarRequiem/verity-demo), a pull request adds a
fraud-detector claiming **98.5% accuracy** — and CI fails it:

```
[REFUSE] fraud-detector v3 — sample 90 < hard floor 100 — noise
         accuracy 0.985 ≤ base rate 0.98 — no real lift over the majority class
         not validated out-of-sample · leakage unchecked
```

The base rate is 98%. The model barely beats "always predict not-fraud." A reviewer waves it
through; CI does not. ([the PR →](https://github.com/StellarRequiem/verity-demo/pull/1))

## What it checks

- **Structural:** sample floors, out-of-sample required, leakage affirmatively checked,
  suspicious-accuracy (tunable per domain).
- **Statistical rigor** (when disclosed): a reported z / p-value must be significant; "best of N"
  must be multiplicity-corrected; accuracy must beat the base rate; optional confidence-interval.
- Thresholds live in a `truth.yaml` you tune to your domain — the demo ships ML-classifier
  defaults; the library defaults are tuned for trading / quant edges.

A **PASS** means *trustworthy*, not *profitable* — it clears the hygiene bar, nothing more. That
honesty is the point.

Apache-2.0. Also a Python library and an MCP tool — so an AI agent can verify its own claims before
believing them. → [**verity-core**](https://github.com/StellarRequiem/verity-core)
