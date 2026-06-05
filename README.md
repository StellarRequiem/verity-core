# verity-core

**The verification primitive — as a library and an MCP tool. Make any AI agent check itself.**

verity-core is the small, hard core of trustworthy AI: a **Reality Anchor** that refuses to believe a result-claim until it clears basic empirical hygiene, plus a **tamper-evident audit chain**. Use it as a library — or run it as an **MCP server** so any agent (including Claude) can call the gate on its own outputs *before* believing a number.

## As a library

```sh
pip install "git+https://github.com/StellarRequiem/verity-core"
```
```python
from verity import check, load_truth

truth = load_truth("truth.yaml")
check({"name": "x", "accuracy": 0.72, "sample_size": 18,
       "out_of_sample": False, "text": "72% win rate backtest"}, truth)
# {'verdict': 'REFUSE', ...}   # sample too small, accuracy auto-suspect, no holdout
```

## As an MCP tool (the point)

```sh
pip install "verity-core[mcp] @ git+https://github.com/StellarRequiem/verity-core"
```
Register it in `.mcp.json`:
```json
{ "mcpServers": { "verity": { "command": "verity-mcp" } } }
```
Now any session has three tools:
- **`verify_claim`** — REFUSE / WARN / PASS a result-claim against ground truth.
- **`gate_thresholds`** — show the active bar.
- **`audit_verify`** — confirm a hash-chained log is intact / tamper-evident.

*An agent that can call `verify_claim` on its own findings is an agent that can refuse to fool you.*

## As a CLI / CI gate

```sh
pip install "git+https://github.com/StellarRequiem/verity-core"
verity check       --claim '{"accuracy":0.92,"sample_size":40}'   # one claim → REFUSE/WARN/PASS
verity check-batch claims.jsonl                                   # a backlog → rolled-up verdict
```
The **exit code is the worst verdict** (`0` PASS · `1` WARN · `2` REFUSE), so it gates CI like a
linter. Drop the bundled **GitHub Action** into any workflow:
```yaml
- uses: StellarRequiem/verity-core@main
  with:
    claims: results/claims.jsonl      # JSONL, one result-claim per line
    truth:  results/truth.yaml         # optional ground-truth (thresholds + facts)
```
A pull request that claims "95% accuracy" now fails CI unless the claim clears the hygiene bar.

## What it checks

- **structural** — sample floors (too small = noise), suspicious accuracy (most real edges are
  small), out-of-sample / holdout required, look-ahead affirmatively checked;
- **statistical rigor** (only when the claim discloses it) — a reported z / p-value must be
  significant, "best of N tries" must be multiplicity-corrected, accuracy must beat the base
  rate, and (opt-in) a point estimate must carry a confidence interval;
- **ground-truth facts** — look-ahead tells, fantasy fills — contradictions flagged at severity.

Edit `truth.yaml` to your domain; the gate reads it live. A `PASS` means *trustworthy*, not *profitable* — and nothing is believed until it clears.

## Tests

```sh
pip install -e ".[dev]"
pytest
```

## License

Apache-2.0. Built by [@StellarRequiem](https://github.com/StellarRequiem).
