# AUTHOR_REVIEW_CHECKLIST

Complete this before any publication run, and again before submission.
Every box is a claim **you** are making, not one the code can make for you.

---

## A. Mathematics

- [ ] I understand the exact mathematical strategy **S1**, and that it is the NARROW half-order shortcut (compute `d = ord_m(a)`; when `d` is even try `n = d/2`) — not a full compatibility analysis.
- [ ] I understand the **S1 applicability oracle** and I have manually checked worked examples, including a composite modulus where the global order is even but the half-order power is not `-1`.
- [ ] I have confirmed that "the S1 shortcut does not apply" is never treated as "the problem has no solution": the exact answer always comes from independent enumeration.
- [ ] I understand that **S2 applicability is the theorem's domain** (`p` odd, `p | a-b`, `p ∤ a`, `p ∤ b`), NOT numerical agreement, and I have checked an accidental-match negative where the shortcut returns the right number outside the domain.
- [ ] I understand **S3** (shift-and-reciprocal linearisation), the proof that a linearising shift must be a fixed point, and the discriminant criterion for Möbius maps, and I have manually verified a positive and a negative instance.
- [ ] I have confirmed that S3 negatives are verified symbolically rather than trusted from a generator flag, and that condition 3 (the substitution is defined along the trajectory) is actually checked.
- [ ] I have read the **deviation notes** in `docs/FAMILY_SPEC.md` and I accept them:
  - [ ] Family 1 template D is realised as a count (`count_up_to`) rather than a free-text classification.
  - [ ] Family 1 seeds mix prime, prime-power and composite moduli, so the seeds alone do not suggest "the shortcut works iff the modulus is prime".
  - [ ] Family 2 positive seeds span exact valuations 1, 2 and 3+, and none has valuation 0.
  - [ ] Family 3's `transformed_value` challenge template is removed, since it revealed `1/(x - c)`.
  - [ ] Family 1's `existence` challenge template makes the boundary question identical to the problem question.
  - [ ] Family 3's oracle uses the **existential** reading of "there exists a shift `c`", not a hidden designated constant.
  - [ ] Family 3 renders all instances from normalised coefficients so the surface form does not leak the label.
- [ ] I have inspected at least **20 randomly generated problems per family** (`python scripts/generate_preview.py --n 10 --verbose`, at each difficulty).
- [ ] I have inspected at least 10 problems from the **challenge** templates (`--challenge`).

## B. Seeds

- [ ] I have completed every checkbox in each `outputs/<RUN_ID>/seeds_<family>_review.md`.
- [ ] I have verified each of the 6 seed problems, its worked solution, and its exact answer **by hand**.
- [ ] I confirm the seed solutions demonstrate the intended strategy without stating the full applicability boundary.
- [ ] I confirm one **common** seed set was used for every model (`common_seed_set_across_models: true` in `seeds_<family>.json`).

## C. Prompts and leakage

- [ ] I have read every prompt in `docs/PROMPTS.md` verbatim.
- [ ] I confirm no prompt contains `strategy_applies`, a canonical strategy description, hidden test membership, or latent parameters not visible in the problem.
- [ ] I have inspected the **Active query schema** actually shown to the model (`active_query_schemas` in `run_manifest.json`) and confirmed every value is observable from a problem statement.
- [ ] I have inspected `oracle_only_feature_schemas` in the manifest and confirmed none of those names is requestable.
- [ ] I have read the **measured determinacy summary** in `docs/FAMILY_SPEC.md` and the output of `python scripts/audit_schema.py`, and it reports PASS.
- [ ] I accept that for `lte_valuation` the conjunction `prime_type=odd ∧ p_divides_difference=yes ∧ p_divides_a_or_b=no` determines the label exactly, that Active can request all three at once, and that **the paper states this**.
- [ ] I accept that a quadratic numerator (Family 3) and a non-coprime base (Family 1) are visible one-sided predictors of non-applicability, and the paper does not present Active gains concentrated there as evidence of falsification-driven learning without saying so.
- [ ] I understand how invalid Active requests are handled (one `UNSATISFIABLE_REQUEST` reformulation, then a logged neutral fallback).

## D. Protocol integrity

- [ ] I have verified the hidden IID and challenge tests were **frozen before adaptation** (compare file timestamps and `run_manifest.json` against the trace files).
- [ ] I have verified the hidden tests are disjoint from the seeds, the H0 pilot, and the adaptation draws.
- [ ] I have verified the hidden tests are label-balanced, so a constant "always APPLIES" rule scores 0.5.
- [ ] I confirm the difficulty selection used the predeclared rule and did **not** consult Active-vs-Passive results.
- [ ] I confirm no family was excluded on the basis of Active-vs-Passive results.
- [ ] I have verified **token accounting**: `A_tokens`, `P_tokens` and `token_mismatch_pct` in `token_accounting.csv` are exact counts, and the paper reports the numbers rather than the phrase "compute matched".
- [ ] I have checked whether `passive_budget_cap_binding` is true anywhere; if it is, the budget was not actually matched in that cell and the paper says so.

## E. Results

- [ ] I have read several raw model outputs behind **each** main result (`evaluation_raw.jsonl`).
- [ ] I have checked the `unparsed` counts; if they are material, the paper reports both `accuracy` and `accuracy_parsed_only`.
- [ ] I have verified every number reported in the paper against the saved CSVs.
- [ ] I confirm no 4-bit pilot number is pooled with a full-precision number without a visible warning.
- [ ] I confirm no `mock` run output appears anywhere in the paper.
- [ ] I confirm the number of stochastic repeats is stated, and that the claims are proportionate to it.
- [ ] If `phi35_mini` was substituted for `llama32_3b`, the paper says it is ~3.8B and not an exact 3B model.
- [ ] Any competition-OOD split is reported separately, with its label provenance (human review) stated.

## F. Attribution and citations

- [ ] I have verified every citation independently. The code does not generate references and none should be taken from it.
- [ ] I can explain the full pipeline end to end without relying on an LLM explanation.
- [ ] I accept responsibility for the correctness and originality of the entire submission.

---

## NeurIPS 2026 LLM-use disclosure

The NeurIPS 2026 Main Track Handbook does not require basic coding assistance to
be documented. However, **the use of an LLM as the Active experiment-selection
mechanism is not coding assistance — it is part of the methodology**, and it
belongs in the Experimental Setup / Methods section.

At minimum, describe:

1. that the Active condition's experiment design is produced by the tested model
   itself, choosing constraints from a fixed categorical schema;
2. that the model neither writes nor executes code, and that SUCCESS/FAILURE
   labels come from a programmatic oracle rather than from any model;
3. that hypotheses are induced and revised by the tested model, and that the
   identical revision prompt is used in both conditions;
4. the adaptation-output-token budget matching, with the realised numbers;
5. which `active_schema_profile` was used, and what the schema exposes.

Separately, if you want to note routine implementation assistance, say so
plainly. Either way the authors remain responsible for all content and results.

---

## Where each `# HUMAN_REVIEW_REQUIRED` marker lives

```
src/families/order_minus_one.py          module docstring; strategy_succeeds
src/families/lte_valuation.py            module docstring; construction modes
src/families/recurrence_substitution.py  module docstring (oracle reading);
                                         quadratic perturbation weighting
src/families/base.py                     preview_extras; query vs oracle namespaces
src/calibration.py                       predeclared difficulty band and target
docs/FAMILY_SPEC.md                      every family oracle; deviation notes;
                                         schema/label determinacy
scripts/audit_schema.py                  determinacy report
```

Find them all with:

```bash
grep -rn "HUMAN_REVIEW_REQUIRED" src scripts docs
```
