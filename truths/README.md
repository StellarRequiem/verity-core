# Domain truth packs

`verity check` scores a claim against a `truth.yaml` — thresholds (and optional ground-truth facts)
tuned to your domain. These are ready-to-use packs; point `--truth` at one, or copy and adjust:

```sh
verity check-batch claims.jsonl --truth truths/ml-classification.yaml
```
```yaml
# in a GitHub Action:
- uses: StellarRequiem/verity-core@v0.1.0
  with:
    claims: results/claims.jsonl
    truth:  truths/trading.yaml
```

| Pack | For | The bar it sets |
|---|---|---|
| `ml-classification.yaml` | supervised classifiers | high accuracy OK; real sample, out-of-sample, leakage, **lift over the base rate** |
| `trading.yaml` | quant / trading signals | **>0.65 win-rate auto-suspect**; out-of-sample + no look-ahead mandatory |
| `ab-test.yaml` | A/B / online experiments | big sample + **statistical significance**; the test is its own holdout |
| `research.yaml` | empirical papers | strict: significance + **confidence interval** + replication |

The library defaults (no `--truth`) match `trading.yaml`. The gate reads the file live, so tune any
pack to your own thresholds and facts.
