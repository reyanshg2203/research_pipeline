# Active Falsification: Learning Strategy Boundaries in Mathematical LLMs

Experimental codebase for testing whether a mathematical LLM learns a more
accurate **strategy-applicability boundary** by actively selecting
falsification-oriented practice problems than by receiving random practice under
a matched adaptation-output-token budget.

This is a research implementation. It prioritises mathematical correctness,
reproducibility, minimal leakage between splits, transparent logs and easy
manual inspection over everything else.

> **No results are claimed here.** The repository has only been exercised
> end to end with the offline `mock` model, which has no mathematical ability
> and produces no scientific output. Every table from a mock run is stamped
> `is_mock`.

---

## What the experiment does

For each of three problem families a latent reasoning strategy `S` is fixed by
the researchers. The model sees six solved demonstrations and induces its own
strategy description `S_hat` and an initial applicability hypothesis `H0`. Three
conditions are then compared:

| condition | adaptation |
|---|---|
| **H0** | none |
| **Passive** | random practice from the adaptation distribution |
| **Active** | the model chooses categorical feature constraints designed to falsify its current hypothesis |

Whether `S` actually succeeds on any given problem is decided by an **exact
programmatic oracle**, never by a model. The primary metric is boundary
accuracy: how often a frozen hypothesis predicts that oracle correctly on
held-out problems.

The three families are documented in full, with proofs and test coverage, in
[`docs/FAMILY_SPEC.md`](docs/FAMILY_SPEC.md):

1. **`order_minus_one`** — exponential congruences `a^n ≡ -1 (mod m)`; the
   strategy is the narrow half-order shortcut (compute `d = ord_m(a)`; when `d`
   is even, try `n = d/2`).
2. **`lte_valuation`** — `v_p(a^n - b^n)`; the strategy is the
   Lifting-the-Exponent shortcut, and applicability is the **theorem's domain**
   (`p` odd, `p | a-b`, `p` divides neither base) — not numerical coincidence.
   About three quarters of the negatives are cases where the shortcut returns
   the right number anyway; those are logged as accidental matches.
3. **`recurrence_substitution`** — rational recurrences linearised by
   `y_n = 1/(x_n - c)`; applicability requires a rational fixed point, a
   symbolically verified affine reduction, and a substitution that is defined
   along the whole requested trajectory.

Two things the code separates deliberately:

- **three concepts, three names** — `exact_answer` (the right answer to the
  problem), `strategy_applies` (is S mathematically applicable), and
  `model_answer_correct` / `model_boundary_correct` (did a model get something
  right on a run). There is no bare `success` or `correct` anywhere.
- **two feature namespaces** — `query_features`, the observable experimental
  controls Active may request, and `oracle_features`, researcher-side
  diagnostics used for validation and audit. Several oracle features are exact
  synonyms for the hidden label, which is why asking for one returns
  `unknown feature name`.

---

## Install

```bash
pip install -r requirements.txt
```

Only `sympy`, `pyyaml` and `pytest` are needed for the mathematics, the tests
and the offline mock run. `torch` / `transformers` are needed only to run real
models.

## Run the mandatory checks first

```bash
python scripts/self_test.py
```

It checks imports and the registry, runs the full mathematical unit-test suite,
sweeps every family × difficulty × template × label and independently
revalidates each generated problem, checks split disjointness and label balance,
sweeps prompts for leakage, and reports which schema features determine the
hidden label. **Do not run a model until this passes.**

Inspect generated problems by hand:

```bash
python scripts/generate_preview.py --n 10                    # 10 positive + 10 negative
python scripts/generate_preview.py --n 10 --challenge        # held-out templates
python scripts/generate_preview.py --n 6 --seeds             # seed demonstrations
python scripts/generate_preview.py --n 5 --difficulty hard --verbose
```

Each problem prints its exact answer, `strategy_applies`, the reason the
strategy holds or fails, the query features, and the oracle features in a
clearly separate block — plus family detail such as the LTE shortcut prediction
beside the exact valuation, or the fixed point and the transformed recurrence.

Check that no query feature is a synonym for the hidden label, and see which
conjunctions determine it:

```bash
python scripts/audit_schema.py --n 500
```

It exits non-zero if any query feature determines the label on both sides. It
also reports one-sided implications (observable facts the model must learn, not
leaks) and the smallest determining conjunctions, which are scientifically
material and belong in the paper.

## Stage 1 — zero-shot difficulty calibration (run this first)

Calibration is a **standalone stage**. It answers one question — which
difficulty tier gives meaningful but nontrivial zero-shot solving accuracy —
and it runs none of the strategy-boundary experiment. `scripts/run_calibration.py`
does not import Active, Passive, seed induction or evaluation, and a test
asserts that.

### Exact command for the co-author with the lab GPU

```bash
git checkout <FROZEN_CALIBRATION_COMMIT>
pip install -r requirements.txt
python scripts/self_test.py
python scripts/run_calibration.py --config configs/calibration.yaml
```

Then return the entire `outputs/<RUN_ID>/` directory.

That is 3 families × 3 tiers × 10 problems = 90 generations per model, 360 in
total across the four models, **one attempt per problem** — no majority vote, no
self-consistency, no retries.

If `meta-llama/Llama-3.2-3B-Instruct` cannot be loaded, the run **stops** with
instructions. Nothing is substituted automatically. To substitute, say so
explicitly:

```bash
python scripts/run_calibration.py --config configs/calibration.yaml --substitute llama32_3b=phi35_mini
```

`phi35_mini` is ~3.8B, not an exact 3B model, and that must be stated wherever
the numbers appear.

### Smaller runs

```bash
python scripts/run_calibration.py --config configs/calibration_mock.yaml --skip-self-test  # offline, no GPU
python scripts/run_calibration.py --config configs/calibration_smoke.yaml                  # 4-bit GPU smoke test
```

Smoke-test accuracies must **not** be used to select a tier.

### The predeclared selection rule

Fixed in `src/calibration.py` before any model ran:

> Among tiers whose **pooled** zero-shot accuracy lies in **[0.20, 0.70]**,
> select the tier closest to **0.45**. If no tier qualifies, select nothing and
> mark the family `NO_VIABLE_TIER`. An exact tie goes to human review unless a
> tie-breaker was predeclared.

It is a pure function of zero-shot solving accuracy and reads no later-stage
result, which is what makes post-hoc difficulty selection impossible.
Diagnostics (difficulty inversion, ceiling, floor, parse-failure rate,
ceiling-vs-floor disagreement between models) are reported as warnings and never
change the selection.

Stage 1 uses only the public problem statement and the exact mathematical
answer. It never reads, conditions on, or records `strategy_applies` — the bank
is drawn unconditionally from each tier's own distribution.

`NO_VIABLE_TIER` is a **result**, not an error: a completed calibration exits 0
and records the outcome in `selected_difficulties.json` and
`calibration_report.md`. Non-zero exit codes mean the run did not complete —
a bad config, a model that would not load, or a generator whose problems failed
mathematical validation.

The config loader enforces a strict allowlist. Any unknown key is an error, so
a setting copied from `pilot.yaml` or `final.yaml` cannot silently enter
calibration and do nothing.

Every generation records `hit_max_new_tokens`. If responses frequently run into
the cap, the report warns — and the cap is **not** adjusted automatically, since
changing it makes tiers measured before and after incomparable.

The manifest records the **resolved** inference configuration, not just the
precision label that was requested: the dtype the weights actually loaded as,
the device map, GPU name and total VRAM, and whether anything spilled to CPU or
disk. 4-bit runs use a BF16 compute dtype only where the GPU supports BF16, and
are stamped smoke/pilot-only.

Preview the exact bank calibration will send:

```bash
python scripts/generate_preview.py --calibration-bank --n 5 --seed 20260901
```

### Calibration outputs

```
outputs/<RUN_ID>/
  run_manifest.json                          model ids, revisions, tokenizers,
                                             per-model reasoning config, GPU,
                                             versions, seeds, the exact prompt
  config.yaml
  calibration_problem_bank.json              the ONE shared bank, frozen before inference
  calibration_problem_bank_researcher.json   researcher-side metadata (never prompted)
  calibration_runs.jsonl                     one row per attempt, with raw response
  calibration_summary.csv                    model x family x difficulty
  pooled_difficulty_summary.csv              family x difficulty, pooled
  selected_difficulties.json                 the rule's output, or NO_VIABLE_TIER
  calibration_report.md                      human-readable
  errors.log
```

### Colab

[`COLAB_CALIBRATION.ipynb`](COLAB_CALIBRATION.ipynb) runs calibration only:
install, GPU check, self-tests, the exact prompt, a bank preview, the offline
plumbing check, the 4-bit smoke test, the summary — then stops.

---

## Offline end-to-end pipeline test (no GPU)

```bash
python scripts/run_mock.py
```

Runs calibration → seed selection → frozen tests → induction → Active →
compute-matched Passive → evaluation → `main_table.csv` with a deterministic
stand-in model. Useful for verifying the plumbing; **produces no results**.

## Pilot run (small models; Colab-friendly)

```bash
python scripts/run_pilot.py --config configs/pilot.yaml
```

`configs/pilot.yaml` uses 4-bit NF4 quantisation. **4-bit numbers are pilot-only
and must never be pooled with full-precision numbers without a visible
warning**; the run manifest carries that warning automatically.

## Final run (lab GPU)

```bash
python scripts/run_final.py --config configs/final.yaml
```

Override the model list without editing the config:

```bash
python scripts/run_experiment.py --config configs/final.yaml --models qwen3_8b
```

Gated models (`meta-llama/Llama-3.2-3B-Instruct`) need an accepted licence and a
token:

```bash
export HF_TOKEN=hf_xxx
```

If access is blocked, use the `phi35_mini` alias instead — but it is ~3.8B, not
an exact 3B model, and the paper must say so.

## Rebuild tables from raw outputs

```bash
python scripts/make_tables.py --run-dir outputs/<RUN_ID>
```

Every table is recomputed from `evaluation_raw.jsonl`, which holds one row per
classified problem with the gold oracle label and the raw model response, so
every reported number traces back to a saved raw output.

## Regenerate the prompt documentation

```bash
python scripts/export_prompts.py
```

`docs/PROMPTS.md` is generated from `src/prompts.py` so it cannot drift.

---

## Colab

Open [`COLAB_PILOT.ipynb`](COLAB_PILOT.ipynb). It installs requirements, checks
the GPU, runs the self-tests, runs one small model first, displays the
calibration summary, and then optionally runs the second small model.

---

## Repository layout

```
configs/     calibration (stage 1) and pilot / final / mock (stage 2) settings
data/        optional author-curated competition OOD problems (ships empty)
docs/        FAMILY_SPEC, PROMPTS (generated), EXPERIMENT_PROTOCOL, AUTHOR_REVIEW_CHECKLIST
src/         families/, models, prompts, grading, sampling, metrics,
             calibration (stage 1 only), seed_screening, seed_induction,
             active, passive, evaluation, runner
scripts/     self_test, generate_preview, audit_schema, export_prompts,
             run_calibration (stage 1), run_mock / run_pilot / run_final,
             make_tables
tests/       mathematical unit tests, leakage tests, sampling tests
outputs/     one directory per run
```

## What a run writes

```
outputs/<RUN_ID>/
  run_manifest.json          git commit, versions, GPU, seeds, hashes, warnings
  config.yaml
  calibration_runs.jsonl     every zero-shot solve, raw
  calibration_summary.csv
  selected_difficulties.json predeclared selection rule and its inputs
  seed_candidate_runs.jsonl
  seeds_<family>.json        the COMMON seed set
  seeds_<family>_review.md   author checkbox sheet
  h0_pilot_<family>.json
  hidden_iid_<family>.json         frozen before adaptation
  hidden_challenge_<family>.json   frozen before adaptation
  induction_<model>_<family>_r<k>.json   S_hat, H0, H0-pilot accuracy
  active_trace_<model>_<family>_r<k>.json
  passive_trace_<model>_<family>_r<k>.json
  evaluation_raw.jsonl       one row per classified problem, with raw responses
  summary_long.csv
  main_table.csv             immediately usable in the paper
  pooled_table.csv
  confusion_matrices.csv
  token_accounting.csv       exact adaptation output tokens, both conditions
  errors.log
```

---

## Before you publish

Work through [`docs/AUTHOR_REVIEW_CHECKLIST.md`](docs/AUTHOR_REVIEW_CHECKLIST.md).
It covers the mathematics, seed approval, prompt leakage, protocol integrity,
token accounting, and the NeurIPS 2026 disclosure of LLM use as part of the
methodology.

Find every scientifically meaningful implementation choice with:

```bash
grep -rn "HUMAN_REVIEW_REQUIRED" src scripts docs
```

## Things this code deliberately does not do

- It never uses an LLM to grade a mathematical answer or to decide whether a
  generated problem is correct.
- It never executes code proposed by a tested model; the Active condition may
  only choose values from a fixed categorical schema.
- It never silently translates an unsatisfiable experiment request into a
  different experiment.
- It never continues past a mathematical validation failure.
- It never populates `data/competition_ood.jsonl` automatically.
