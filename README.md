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
Now any session has these tools:
- **`verify`** — the recommended entrypoint: REFUSE / WARN / PASS a claim across **all
  applicable dimensions** at once (empirical hygiene, plus evidence-match and consistency when you
  supply them — see below).
- **`verify_claim`** — empirical-only check of a result-claim against ground truth.
- **`gate_thresholds`** — show the active bar.
- **`audit_verify`** — confirm a hash-chained log is intact / tamper-evident.

*An agent that can call `verify` on its own findings is an agent that can refuse to fool you.*

## Agent-native verification — the `verify` surface

`verify` is the unified entrypoint an agent calls **before acting** on a number. It is a thin
orchestrator over three independent, deterministic dimensions — each emitting the same issue shape,
all judged by one verdict ladder (worst severity wins: `REFUSE` ≥ CRITICAL · `WARN` any · `PASS`
clean). A dimension only runs when you give it the input, so the result distinguishes *"checked and
clean"* from *"not applicable"*.

| Dimension | Runs when | What it catches |
|---|---|---|
| **empirical** | always | sample floors, suspicious / impossible accuracy, out-of-sample + leakage affirmation, statistical rigor (significance, effect-size floor, power/MDE, CI coherence, multiplicity, base-rate) |
| **evidence** | `evidence=` given | the claim's fields vs **recomputed** ground truth — a number that disagrees beyond tolerance is a fabrication-class **CRITICAL** (deterministic field reconciliation, *never* fuzzy NLP) |
| **consistency** | `prior=` given | the claim vs a **previously-asserted** claim — a silently-revised number is a story-change (HIGH); a sign-flip on a signed effect is a direct contradiction (**CRITICAL**) |

```python
from verity import verify, load_truth

verify(
    {"name": "money-printer", "accuracy": 0.91, "sample_size": 12,
     "out_of_sample": "false", "leakage_checked": "no"},   # deceptive string booleans don't slip
    evidence={"accuracy": 0.58},                            # recomputed → 0.91 is a fabrication
    prior={"name": "money-printer", "accuracy": 0.40},      # quietly revised up from 0.40
    truth=load_truth("truths/trading.yaml"),
)["verdict"]                                                # -> "REFUSE"
```

Same thing from the shell (CI-gateable: exit `0`/`1`/`2` = PASS/WARN/REFUSE):

```sh
verity verify --claim '{"name":"money-printer","accuracy":0.91,"sample_size":12,
                        "out_of_sample":"false","leakage_checked":"no"}' \
              --evidence '{"accuracy":0.58}' \
              --prior    '{"name":"money-printer","accuracy":0.40}' \
              --sources  '[]' --truth truths/trading.yaml
# VERIFIED → REFUSE: sample 12 < floor; accuracy auto-suspect; not out-of-sample; leakage unchecked;
#            evidence:accuracy 0.91 disagrees with 0.58; consistency:accuracy 0.40 -> 0.91; sources empty
```
`--evidence`, `--prior`, `--sources` accept inline JSON or `@file`; `--sources` also takes a bare
`a,b,c` list. (MCP: same arguments, returns the VERIFIED block.)

### The eval harness — `verity eval`

```sh
verity eval                          # runs eval/benchmark.jsonl; exit 0 iff fully consistent
python -m eval.harness               # same, as a module
```
A **self-authored regression** that proves each check is wired and that honest claims are left
alone — 20 hand-built cases across all four dimensions (16 known-failure + 4 clean negative
controls), every case provenance-tagged (`definitional | statistical | real-incident`). The harness
prints a banner saying exactly what it is **and is not**: it is a **CIRCULAR benchmark by
construction** (the verifier graded against the rules it implements), so 100% here means the rules
are internally consistent and wired — **not** that they are sufficient, that they generalize, or
that a PASS is profitable.

## As a CLI / CI gate

```sh
pip install "git+https://github.com/StellarRequiem/verity-core"
verity check       --claim '{"accuracy":0.92,"sample_size":40}'   # one claim → REFUSE/WARN/PASS
verity check-batch claims.jsonl                                   # a backlog → rolled-up verdict
verity check-batch claims.jsonl --truth truths/trading.yaml       # tuned to your domain (see truths/)
```

Ready-made **domain packs** live in [`truths/`](truths/) — `ml-classification`, `trading`,
`ab-test`, `research` — so the same `0.72` is auto-suspect for a trading signal but fine for a
classifier. Point `--truth` at one, or tune your own.
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

- **structural** — sample floors (too small = noise), suspicious **and impossible** accuracy
  (outside `[0,1]` is a unit error / fabrication → CRITICAL), out-of-sample / holdout required,
  look-ahead affirmatively checked. Affirmation flags resist deceptive truthiness: a string
  `"false"` / `"no"` / `"0"` does **not** pass as "yes";
- **statistical rigor** (only when the claim discloses it) — a reported z / p-value must be
  significant, "best of N tries" must be multiplicity-corrected, accuracy must beat the base
  rate, a disclosed **effect size** must clear a practical floor (significant-but-tiny is large-n
  p-hacking), a disclosed effect + n must be **adequately powered** (MDE at 80%), a disclosed
  **confidence interval** must bracket its estimate with a sane width, and (opt-in) a point
  estimate must carry an interval at all;
- **ground-truth facts** — look-ahead tells, fantasy fills — contradictions flagged at severity.

Edit `truth.yaml` to your domain; the gate reads it live. A `PASS` means *trustworthy*, not *profitable* — and nothing is believed until it clears.

The verifier is also **hardened against being fooled or taken down**: a non-dict claim, a
non-serialisable field, `thresholds: None`, a NaN/inf "number", a stringified numeric, or a
negative tolerance in a truth pack are all handled deterministically (REFUSE or a clean flag), never
a crash — an input that can crash the gate is an input that bypasses it.

## Honest gaps

Per the Measurable Work Standard, the limits are stated, not hidden:

- **The eval is circular.** `eval/benchmark.jsonl` is self-authored against the gate's own rules, so
  a 100% catch-rate measures *internal consistency and wiring*, not real-world sufficiency,
  generalization, or profitability. There is **no external, independently-labelled benchmark** here;
  building one is future work, and the harness says so in its banner.
- **Fact-matching is substring, not semantic.** A determined author can *launder* a look-ahead tell
  by stuffing canonical terms ("walk-forward, out-of-sample, no look-ahead") next to a leak — the
  canonical language suppresses the contradiction. Surfacing that co-occurrence is **deliberately
  not** attempted because "no look-ahead" legitimately contains "look-ahead", and reliable negation
  detection is exactly the fuzzy-NLP this gate refuses to do. The gate catches the *naïve* tell, not
  an adversarial one.
- **Reconciliation only sees shared fields.** evidence/consistency compare keys present in **both**
  dicts; a claim that **omits** a disputed field is not caught by those dimensions (it is silent, by
  design — you can only reconcile what is stated). Omission-evasion is a known gap.
- **A poisoned truth pack is obeyed.** Thresholds come from the caller's truth file; a deliberately
  loosened pack (e.g. `hard_min_sample: 1`) will pass claims a strict pack rejects. Only impossible
  values (accuracy outside `[0,1]`, a malformed claim) are refused regardless of config. Trust the
  truth pack like you trust the test suite — review it.
- **A PASS is not a profit signal.** It means the claim cleared *these* hygiene checks — nothing
  about whether an edge is real or will make money.

## Tests

```sh
pip install -e ".[dev]"
pytest
```

## License

Apache-2.0. Built by **Alex Price** ([@StellarRequiem](https://github.com/StellarRequiem) ·
[𝕏](https://x.com/StellarRequiem)).
