# I built a linter for ML result-claims — then tested it against 1,772 real replications

Your README says **95% accuracy**. Your model card says **0.98 AUC**. Your paper says **SOTA**.

Did anyone *check*?

ML and research repos report their headline numbers in prose — a badge, a model card, a results table. Almost nobody gates those numbers against basic statistical hygiene before they ship. So the claims that slip through are the dangerous ones: no lift over the base rate, samples too small to mean anything, evaluated on training data, the best of 50 configs reported as if it were the only one.

A human reviewer sees a big confident number and nods. The number is the thing that should have been gated — and wasn't.

## verity gates result-claims like a linter gates code

Put your metrics in a file, add it to CI, and every pull request that touches your numbers gets checked. The exit code gates the build: **PASS / WARN / REFUSE.**

In a demo repo, a PR adds a fraud detector claiming **98.5% accuracy**. But fraud is 2% of the data — so "always predict *not* fraud" already scores 98%. A reviewer waves it through. CI does not.

## But do the checks actually work?

A linter is only worth running if its rules track reality. So I tested verity against **1,772 published findings that were independently replicated** — the FORRT database: real effect sizes, sample sizes, and p-values, each with a "did a high-powered replication succeed?" label.

The question: does verity flag the claims that *failed* to replicate more than the ones that held up?

**It does — significantly.** 78% of failures flagged vs 63% of survivors: odds **2.14×**, **z = 7.06, p ≈ 10⁻¹²** (n = 1,772).

And *how* it got there is the part I'm proudest of. The base checks gave a modest 1.41×. Mining the corpus showed that a **marginal p-value** — one just under 0.05 — predicts replication failure: claims at 0.01–0.05 replicated 42% of the time vs 59% for strongly significant ones, confirmed out-of-sample. So I added one principled check for it, using the standard literature cut — **not** a knob tuned to the benchmark. That single check nearly doubled the discrimination.

I also built a fitted model that scored just as well on held-out data — and **threw it away.** A number tuned to one dataset is the exact thing a verifier exists to catch. Improving the tool by fitting it to my own benchmark would have been the sin it's designed to flag.

It even flagged its *own* first result as under-powered, before I had enough data to claim it. A verifier that holds itself to its own bar — and earns its improvements honestly — is the whole idea.

## What it checks

Sample floors · out-of-sample required · leakage affirmatively checked · suspicious accuracy · **marginal significance** · multiple-comparisons correction · effect-size floors and statistical power · base-rate lift. Thresholds live in a config you tune per domain.

A **PASS** means *trustworthy*, not *true* — it clears the hygiene bar, nothing more. That honesty is the point.

## Try it

Open source (Apache-2.0). It's a CI Action, a Python library, **and** an MCP tool — so an AI agent can verify its own claims before believing a number.

→ **github.com/StellarRequiem/verity-core** (the full 1,772-replication writeup is in the repo)

— Alex Price ([@StellarRequiem](https://x.com/StellarRequiem))
