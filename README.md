# verity-core

**The verification primitive — as a library and an MCP tool. Make any AI agent check itself.**

verity-core is the small, hard core of trustworthy AI: a **Reality Anchor** that refuses to believe a result-claim until it clears basic empirical hygiene, plus a **tamper-evident audit chain**. Use it as a library — or run it as an **MCP server** so any agent (including Claude) can call the gate on its own outputs *before* believing a number.

> **Validated, not just asserted.** On **1,772 real scientific replications**, verity flags the claims that *failed* to replicate significantly more than the ones that held — odds **2.14×**, p ≈ 10⁻¹². A principled, held-out-validated check got it there; a corpus-fitted shortcut that scored as well was *declined*. → [the proof](docs/replication-benchmark.md)

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
→ runnable pattern: [`examples/agent_self_check.py`](examples/agent_self_check.py) (the agent refuses a flashy 95%-on-15-trades "edge", acts on a modest 56%-on-1200-OOS one).

## Agent-native verification — the `verify` surface

`verify` is the unified entrypoint an agent calls **before acting** on a number. It is a thin
orchestrator over four independent, deterministic dimensions — each emitting the same issue shape,
all judged by one verdict ladder (worst severity wins: `REFUSE` ≥ CRITICAL · `WARN` any · `PASS`
clean). A dimension only runs when you give it the input, so the result distinguishes *"checked and
clean"* from *"not applicable"*.

| Dimension | Runs when | What it catches |
|---|---|---|
| **empirical** | always | sample floors, suspicious / impossible accuracy, out-of-sample + leakage affirmation, statistical rigor (significance, effect-size floor, power/MDE, CI coherence, multiplicity, base-rate) |
| **evidence** | `evidence=` given | the claim's fields vs **recomputed** ground truth — a number that disagrees beyond tolerance is a fabrication-class **CRITICAL** (deterministic field reconciliation, *never* fuzzy NLP) |
| **consistency** | `prior=` given | the claim vs a **previously-asserted** claim — a silently-revised number is a story-change (HIGH); a sign-flip on a signed effect is a direct contradiction (**CRITICAL**) |
| **grounding** | `sources=` non-empty | the claim's disclosed facts vs what its **cited sources** actually assert — a structured source asserting a differing value is a **CRITICAL** contradiction (it beats support: disagreeing sources don't safely ground); a fact no source backs is MEDIUM "unsupported". Sources are caller-supplied resolved facts/text — **never** crawled. A *text* source can support (substring) but never contradict; a *poisoned* source (NaN/garbage for a numeric key) is silent, so junk can't force a REFUSE |

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

**Grounding** runs when `--sources` is a *non-empty* list of resolved facts/text (never crawled). A
structured source that asserts a differing value is a CRITICAL contradiction:

```sh
verity verify --claim   '{"name":"alpha","accuracy":0.91,"out_of_sample":true,"leakage_checked":true}' \
              --sources '[{"id":"recompute.csv","facts":{"accuracy":0.58}}]'
# VERIFIED → REFUSE: grounding:accuracy claim 0.91 contradicts source recompute.csv accuracy=0.58
# …whereas --sources '[{"id":"recompute.csv","facts":{"accuracy":0.91}}]' grounds it → that field clears.
```

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

### External validity — real replication outcomes (`verity eval-external`)

The eval above proves *wiring*. **This** proves the checks track *reality*: **1,772 published
result-claims** with their real statistics **and an independent replication label** (FORRT corpus,
CC-BY 4.0 — see [`eval/external/`](eval/external/SOURCES.md)).

| | flag-rate (WARN/REFUSE) |
|---|---|
| claims that **failed** to replicate | **78%** |
| claims that **replicated** | **63%** |

verity flags a failed-to-replicate claim **significantly more often** than a survivor — odds
**2.14×**, **z = 7.06, p ≈ 10⁻¹²** (n = 1,772). And *how* it got there is the point: the base checks
gave a modest 1.41×; mining the corpus showed the binary `p>0.05` cut backfires, so we added one
**marginal-significance** check (a "just-significant" 0.01<p≤0.05 result is fragile — 42% vs 59%
replication, held-out validated, the standard literature cut, **not** tuned to the data), which
nearly doubled the gap to 2.14×. We **declined** a fitted logistic that scored as well — a
corpus-tuned number is the exact thing a verifier exists to catch. The honest arc seals it: the
132-case subset only *hinted* (z=1.30, p=0.19) and `verity verify` flagged **our own claim** as
under-powered; we got the power, confirmed it, then improved it the principled way. *A verifier that
holds itself to its own bar, then earns its gains honestly — that's the holotype.* →
**[the full writeup](docs/replication-benchmark.md)**.

## As a CLI / CI gate

```sh
pip install "git+https://github.com/StellarRequiem/verity-core"
verity check       --claim '{"accuracy":0.92,"sample_size":40}'   # one claim → REFUSE/WARN/PASS
verity check-batch claims.jsonl                                   # a backlog → rolled-up verdict
verity check-batch claims.jsonl --truth truths/trading.yaml       # tuned to your domain (see truths/)
verity prove-batch proofs.jsonl                                   # RUN each proof; number must reproduce
```

Ready-made **domain packs** live in [`truths/`](truths/) — `ml-classification`, `trading`,
`ab-test`, `research`, plus high-stakes science: `clinical-trials` (pre-specified endpoint + CI),
`genomics` (genome-wide significance `p < 5e-8`, not `0.05`), `epidemiology` (adjust for confounders
+ multiplicity), `economics`, `ml-security`, `neuroscience`, `psychology` (the replication-crisis pack, locked tight),
`business` (C-suite + supply-chain metrics), `ai-eval` (AI benchmark/eval claims — data
contamination, cherry-picked baselines, test-set tuning; a high score is *not* auto-suspect),
`finance` (earnings — non-GAAP reconciliation, revenue recognition, cherry-picked period),
`polling` (survey — sample/MOE/leading questions), `esg` (greenwashing — offsets, scope-3, baseline
gaming), and `journalism` (sourcing, context, stat literacy) — **seventeen packs** in all. So the same
`0.72` is auto-suspect for a trading signal but fine for a classifier, a GWAS hit at `p=1e-5` is
correctly refused, and an "obfuscated-gradients" robustness claim is flagged. Point `--truth` at one,
or tune your own.
The **exit code is the worst verdict** (`0` PASS · `1` WARN · `2` REFUSE), so it gates CI like a
linter. Drop the bundled **GitHub Action** into any workflow:
```yaml
- uses: StellarRequiem/verity-core@main
  with:
    claims: results/claims.jsonl      # JSONL, one result-claim per line
    truth:  results/truth.yaml         # optional ground-truth (thresholds + facts)
```
A pull request that claims "95% accuracy" now fails CI unless the claim clears the hygiene bar.
Or gate it **before the commit even lands** — verity ships a [pre-commit](https://pre-commit.com) hook:
```yaml
# .pre-commit-config.yaml
- repo: https://github.com/StellarRequiem/verity-core
  rev: v0.2.0
  hooks:
    - id: verity-check
      files: results/claims\.jsonl$
```

Or assert it **inside your test suite** — a REFUSE fails the test:
```python
from verity import assert_verified
def test_model_card_is_honest():
    assert_verified({"accuracy": 0.87, "sample_size": 5000, "out_of_sample": True,
                     "leakage_checked": True, "base_rate": 0.51})
```

…or drop `@verified` on a function so it can't *return* an untrustworthy number:
```python
from verity import verified
@verified
def evaluate(): return {"accuracy": 0.99, "sample_size": 5}   # raises: verity REFUSE
```

Point it at a **README or model card** to gate the numbers it brags about, or run it as a **service**:
```sh
verity verify-markdown README.md     # check every ```json claim block in a doc (exit = worst verdict)
verity serve                         # POST /verify over HTTP — verify-as-a-service, stdlib only
```

It reaches into a **notebook** and **Slack** too:
```python
%load_ext verity.jupyter                 # then  %%verity  gates a claim cell inline
from verity import notify_slack           # post a REFUSE / WARN / PASS to a Slack webhook
```

## Proof-carrying claims — `verity prove`

`check`/`verify` ask *is this number statistically trustworthy?* and `ground` asks *does it match
the live source?* — but none of them **re-derive** the number. `prove` does: a claim carries a
re-runnable `proof` command, and the gate **runs it and asserts the number actually reproduces.**

```sh
# proofs.jsonl — each claim ships the command that produces its number
{"name": "demo-classifier accuracy", "metric": "accuracy", "value": 0.9,
 "proof": "python examples/eval_demo.py", "tolerance": 0.001}

verity prove-batch examples/proofs.jsonl     # CI runs each proof; exit 0 PASS · 2 REFUSE
#   [PASS  ] demo-classifier accuracy  —  reproduced 0.9 ≈ claimed 0.9 (±0.001)
```

Bump that `0.9` to `0.97` without re-running the eval and CI **fails the build**:

```
[REFUSE] inflated  —  reproduced 0.9 ≠ claimed 0.97 (Δ=0.07 > ±0.001)
```

The proof command prints the value as JSON (`{"accuracy": 0.9}`), a labelled line (`accuracy: 0.9`),
or just the headline number; `prove` extracts and compares it. **Security:** `prove` *executes* each
claim's `proof` — they're your own recipes, run in your own CI like your test suite. It is not a
sandbox; never point it at an untrusted claims file. (For that reason `prove` is CLI/CI-only — it is
deliberately **not** an MCP tool.) This repo gates its own `examples/proofs.jsonl` in CI.

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
- **Reconciliation only sees stated fields — omission-evasion persists.** evidence/consistency
  compare keys present in **both** dicts; grounding only iterates the claim's **own disclosed** keys.
  So a claim that simply **omits** a disputed fact is silent across all three (you can only reconcile
  what is stated). It **degrades gracefully** — the omitted fact is never grounded, never invented,
  and never crashes the verifier (tested adversarially) — but it is **not caught**. Omission-evasion
  is a known, by-design gap; closing it needs an *expected-fields* contract the caller has not given.
- **Grounding's text-source matching is shallow (substring, not semantic).** A *structured* source
  (`{facts: {...}}`) is reconciled value-by-value and CAN contradict; a *text/prose* source is only
  normalized-substring-searched, so it can **support** (the value's string appears) or be **silent**,
  but **never contradict** — absence of a value's string means "phrased differently", not "disputed".
  A prose source therefore can't *catch* a wrong number, only fail to back it (MEDIUM unsupported);
  and "0.6" won't match prose that says "60%". Sources are caller-supplied resolved facts/text and
  are **never crawled or fetched** (the no-I/O rule). Hardened so a *poisoned* source — NaN/inf/garbage
  for a numeric key, a non-dict / non-serialisable source, a list of junk — is treated as silent and
  cannot force a REFUSE or crash the gate; what it can't do is upgrade prose to semantic understanding.
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
