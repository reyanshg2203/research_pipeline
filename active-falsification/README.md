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
   strategy is half-order reasoning over coprime prime-power components.
2. **`lte_valuation`** — `v_p(a^n - b^n)`; the strategy is the
   Lifting-the-Exponent shortcut, with applicability defined *operationally* as
   "the shortcut returns the true valuation".
3. **`recurrence_substitution`** — rational recurrences linearised by
   `y_n = 1/(x_n - c)`; applicability is exactly the existence of a rational
   fixed point.

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
python scripts/generate_preview.py --n 5
python scripts/generate_preview.py --n 5 --difficulty hard --verbose
python scripts/generate_preview.py --n 5 --challenge
```

See how much of the label each queryable feature explains:

```bash
python scripts/audit_schema.py --n 500
```

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
configs/     pilot / final / mock experiment settings
data/        optional author-curated competition OOD problems (ships empty)
docs/        FAMILY_SPEC, PROMPTS (generated), EXPERIMENT_PROTOCOL, AUTHOR_REVIEW_CHECKLIST
src/         families/, models, prompts, grading, sampling, metrics,
             calibration, seed_induction, active, passive, evaluation, runner
scripts/     self_test, generate_preview, audit_schema, export_prompts,
             run_mock / run_pilot / run_final, make_tables
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
