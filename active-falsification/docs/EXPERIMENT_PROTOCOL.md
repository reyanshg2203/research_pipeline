# EXPERIMENT_PROTOCOL

The exact order of operations, what is frozen when, and how compute is matched.

---

## Research question

Does a mathematical LLM learn a more accurate rule for **when** to use a
reasoning strategy by actively selecting falsification-oriented practice
problems, compared with randomly sampled practice under an approximately matched
adaptation-output-token budget?

Three conditions share one induced strategy `S_hat` and one initial hypothesis
`H0`:

| condition | adaptation |
|---|---|
| **H0** | none |
| **Passive (HP)** | random practice from the adaptation distribution |
| **Active (HA)** | model selects categorical feature constraints intended to falsify its current hypothesis |

Primary metric: **boundary accuracy** — the fraction of held-out problems on
which the frozen hypothesis predicts the programmatic oracle label
`strategy_applies` correctly.

---

## Stage order

Run with `python scripts/run_experiment.py --config configs/<name>.yaml`.
The runner refuses to touch a model until `scripts/self_test.py` passes.

### 0. Manifest

`run_manifest.json` records the git commit, timestamp, platform, torch /
transformers / sympy versions, GPU name, model ids and notes, precision, the
full config, every derived RNG seed, each family's `version_hash`, the prompt
version and hash, and the active schema profile. A 4-bit run and a run
containing the mock model each get an explicit warning field.

### 1. Zero-shot difficulty calibration

`calibration_per_tier` label-balanced problems per family per difficulty per
model, solved once, exact-graded.

The selection rule is **predeclared** (`src/calibration.py`):

> Prefer a tier whose pooled zero-shot accuracy lies in **[0.20, 0.70]**; among
> those take the tier closest to **0.45**. If no tier is in band, take the tier
> closest to 0.45 and flag `in_band: false`.

It reads only zero-shot solving accuracy. It never sees Active-vs-Passive
outcomes. Outputs: `calibration_runs.jsonl`, `calibration_summary.csv`,
`selected_difficulties.json`.

### 2. Seed selection

`seed_candidates` positive demonstrations are generated at the selected
difficulty and screened zero-shot by every model. Candidates are ranked by
pooled solve count **ascending** — the seeds should be relatively difficult
across the pool — and the top `seed_count` (default 6) become the **common seed
set used by every model** (spec S.24.3), so cross-model robustness is not
confounded by different demonstrations.

Outputs: `seed_candidate_runs.jsonl`, `seeds_<family>.json`, and
`seeds_<family>_review.md`, which is a checkbox sheet the authors must complete
before a publication run.

### 3. Freeze the hidden tests — **before any adaptation**

Three disjoint sets per family, each from its own derived RNG stream, each
50/50 on applicability by default:

| set | size key | purpose |
|---|---|---|
| H0 pilot | `h0_pilot_size` | records H0 quality before adaptation |
| hidden IID | `iid_test_size` | unseen instances, base templates |
| hidden challenge | `challenge_test_size` | held-out templates, same boundary |

`assert_disjoint` raises if any mathematical instance appears in two sets, and
adaptation draws exclude every frozen key. Hidden tests are never regenerated
mid-run.

If `data/competition_ood.jsonl` contains author-curated entries, they are loaded
as a fourth split, evaluated separately, and **never pooled** with the generated
splits, because their labels come from human review rather than an oracle.

### 4. Induction

The model sees only the six seed statements and their verified solutions, and
returns `{"strategy": ..., "hypothesis": ...}`. Up to three attempts; a
persistent parse failure raises `InductionFailure` and is logged rather than
patched over with a default rule.

### 5. H0 pilot

The frozen `H0` is evaluated on the pilot set **before** any adaptation and
recorded with its diagnostic band (`likely_too_unclear` < 0.55, `attractive`
0.60–0.85, `little_headroom` > 0.90). These bands are diagnostics. **No family
is ever dropped on the basis of Active-vs-Passive results**; any exclusion must
cite the predeclared calibration criteria and be logged.

### 6. Active adaptation

Per round:

1. the model is shown `S_hat`, the current `H_t`, the allowed feature schema and
   a compact summary of its recent experiments;
2. it returns 1–3 feature constraints plus a reason;
3. every feature name and value is validated; subset constraints (a list of
   allowed values) are supported;
4. `family.sample_conditioned` produces a fresh batch of `active_batch_size`
   problems satisfying the constraints, excluding everything frozen and
   everything already seen;
5. the **programmatic oracle** labels each as SUCCESS or FAILURE;
6. the model is shown problem text and outcome — feature values are withheld
   unless `show_features_in_observations` is enabled — and revises `H_t → H_(t+1)`.

**Invalid or unsatisfiable requests.** The model receives a literal
`UNSATISFIABLE_REQUEST` message carrying the reason and the allowed schema, and
gets exactly **one** reformulation attempt. If that also fails, the round falls
back to the same unconstrained distribution Passive draws from, and the fallback
is logged. A request is never silently translated into a different experiment.
`n_unsatisfiable` and `unsat_rate` are reported.

### 7. Passive adaptation

Starts from the identical `S_hat` and `H0`. Each round draws
`active_batch_size` random problems from the same adaptation distribution and
asks for a revision, using the **same revision prompt** as Active. It performs
no experiment-design generations.

### 8. Compute matching

The budget proxy is **model output tokens spent during adaptation**, counted
exactly as generated token ids — never estimated.

- Active spends tokens on experiment-selection generations (including retries)
  and hypothesis revisions.
- Passive keeps adding random practice batches until
  `T_passive ≥ T_active`, stopping at the first batch that satisfies it, so the
  overshoot is the smallest achievable at this batch granularity.

Reported for every cell, in `main_table.csv` and `token_accounting.csv`:
`A_tokens`, `P_tokens`, `token_mismatch_pct`, `A_obs`, `P_obs`, revision counts,
query-generation count, `A_unsat`, `A_unsat_rate`, and whether the passive round
cap bound before the budget was reached. The phrase "compute matched" is never
reported without these numbers.

Because the applicability oracle is programmatic, applying `S` costs no model
tokens in either condition, so nothing further needs to be equalised.

### 9. Frozen evaluation

`H0`, `HP` and `HA` are frozen, and for each hidden problem the model is asked
only:

> Given the method and the rule, would applying the method to this problem
> succeed? Answer `APPLIES` or `DOES_NOT_APPLY`.

It is not asked to solve the problem. Unparseable responses are counted in
`unparsed` and scored as incorrect for accuracy, while being excluded from
precision / recall / F1; both figures are reported.

Metrics: accuracy with a percentile bootstrap 95% CI, precision / recall / F1
for the `APPLIES` class, the full confusion matrix, the predicted-positive rate
and the test base rate, per family and pooled, per model, with the challenge
split reported separately. `delta_active_passive` and `delta_active_h0` use a
**paired** bootstrap over the same test items.

### 10. Tables

`scripts/make_tables.py --run-dir outputs/<RUN_ID>` rebuilds every table from
`evaluation_raw.jsonl` — one row per classified problem, carrying the gold label
and the raw model response — so every reported number traces back to a saved raw
output.

---

## Repeats

`adaptation_repeats` controls how many stochastic adaptation runs are performed
per model × family against the **same** frozen seeds and tests. `configs/final.yaml`
sets 3. If you reduce it, the paper must state the number of runs and must not
overclaim.

---

## Scientific safeguards, and where each is implemented

| safeguard | implementation |
|---|---|
| no post-hoc family tuning | difficulty rule is predeclared in `src/calibration.py` and recorded in the manifest; no code path reads adaptation results |
| H0 calibration logged | `induction_*.json` stores `h0_pilot_accuracy` and its band, written before adaptation |
| common seed set | one seed set per family for all models; model-specific seeds would need a config flag and a visible warning |
| balanced tests | `_generate_split(balanced=True)` by default; the base rate is reported in every confusion row |
| Active unsat rate | `n_unsatisfiable`, `n_query_generations`, `unsat_rate` in every trace and table |
| exact token budget | generated token ids counted in `HFModel._generate` |
| execution vs applicability | `strategy_applies` (mathematical) is never named or computed like model success; the oracle is programmatic |
| raw trace retention | every prompt and response is stored in the traces and `evaluation_raw.jsonl` |
| no LLM as judge | `src/grading.py` is exact parsing plus rational comparison; no model grades anything |
| no model-written code | Active chooses categorical constraints only; nothing generated by a model is ever executed |
