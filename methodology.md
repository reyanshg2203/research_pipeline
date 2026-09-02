# Methodology

## Study Design and Overview

We investigate whether, and how, automated quality control (QC) improves the pedagogical usability of large language model (LLM)–generated mathematics practice problems. Our central design is a controlled comparison in which an identical stream of machine-generated problems is passed through three distinct QC strategies and the resulting items are evaluated by trained human raters under blinded conditions. Because the generator is held fixed and only the QC stage varies, observed differences in downstream quality are attributable to the QC method rather than to generation.

The task domain is a high-school geometry unit on dilation and similarity, comprising ten lessons whose learning objectives advance from scale factor and dilation, through triangle similarity (angle–angle, side–side–side, and side–angle–side criteria), triangle proportionality, and midsegments, to right-triangle relationships—the Pythagorean theorem, the geometric-mean relations, and the altitude-to-hypotenuse decomposition—and triangle classification. This unit is chosen because it is small enough to model formally yet rich enough to exhibit the multi-step, theorem-chaining reasoning where generation errors are both common and consequential.

Each generated candidate is realized in three parallel versions, one per QC condition: **(C1)** a no-QC baseline, **(C2)** an LLM-as-judge iterative refinement loop, and **(C3)** a symbolic validation-and-repair loop. All three versions are rendered into natural language by the same realization stage and rated on the same rubric, so that condition is the sole manipulated variable.

## Problem Representation

All components of the system communicate through a single structured representation of a problem. Each item is encoded as a typed **schema** with three parts: (i) a set of *entities*—geometric objects such as triangles, segments, polygons, points, lines, and circles, each carrying typed attributes (e.g., side lengths, angle measures, right-angle and isosceles flags, radii); (ii) a set of *relationships* drawn from a closed vocabulary of geometric relations (similarity and dilation, parallelism and transversal relations, angle relations, proportional-segment and midsegment relations, perpendicularity, congruence, and intersection), each with its own admissible attributes; and (iii) a *target*, the single unknown quantity the student is asked to determine. Unknown quantities are represented explicitly as null-valued attributes, which allows the same representation to express both the givens and the sought quantity of a well-posed problem.

This schema is the interchange format between generation, quality control, and natural-language realization. It is deliberately abstract: it captures the mathematical content of a problem independently of its surface wording, which makes it amenable to formal analysis while leaving linguistic realization to a separate stage.

## Item Generation

Candidate schemas are produced by an instruction-tuned generator LLM conditioned on the learning objectives of a target lesson and a small number of curriculum-authentic worked examples used as few-shot exemplars. The generator emits schemas as constrained structured output validated against the representation above, so that syntactically malformed candidates are rejected at the source. Generation is deliberately identical across all three conditions—the same candidate schema seeds C1, C2, and C3—so that any downstream difference isolates the effect of quality control. We generate a balanced pool of items across the ten lessons, with multiple candidates per lesson, to control for topic difficulty when comparing conditions.

## Quality-Control Conditions

### Baseline (C1)

In the baseline condition, the generated schema is passed directly to natural-language realization with no intervening quality control. C1 measures the intrinsic quality of unmoderated generation and serves as the reference against which the two QC strategies are compared.

### Model-Based Iterative Refinement (C2)

The second condition implements an *LLM-as-judge* critique-and-revise loop. A strong evaluator model scores the candidate against the study rubric—assigning graded scores on geometric accuracy, lesson alignment, and linguistic clarity—and returns structured, itemized feedback identifying specific deficiencies. A generator model then revises the natural-language rendering in response to this feedback. The judge–revise cycle repeats until the item attains a passing composite score or a fixed iteration budget is exhausted, with early termination when all rubric dimensions reach ceiling. This condition represents the prevailing paradigm in which model-based judgments substitute for formal verification.

### Symbolic Validation and Repair (C3)

The third condition replaces the model judge with a formal, logic-based validator coupled to an LLM repair step. The validator ingests a schema and evaluates it against a layered battery of constraints, organized from surface to semantic:

1. **Structural validity.** Well-formedness of entities and relationships: reference integrity (every relationship and the target refer to declared entities), naming and typing conventions, relation arity, and connectivity of the figure.
2. **Type compatibility.** Each relationship is applied only to entity types for which it is defined, and each attribute holds a value of its expected kind.
3. **Mathematical consistency.** Declared quantities must not contradict one another under the governing theorems—triangle angle sums, the triangle inequality, scale-factor coherence across corresponding parts, Pythagorean and geometric-mean relations, midsegment and proportionality relations, and analogous constraints. This layer fires only on genuine contradictions among *known* values, so that legitimately unspecified quantities are not penalized.
4. **Determinacy and solvability.** For a well-posed problem exactly one quantity—the target—is unknown and must be *derivable* from the givens. A reachability procedure attempts to derive the target by chaining domain theorems from a formal library, returning the derivation together with the sequence of theorems it used; an item whose target cannot be reached is flagged as under-determined.
5. **Redundancy.** Relationships that contribute nothing to reaching the target are identified as superfluous.

For items that are structurally and mathematically valid, a further **scope-and-difficulty calibration** examines the derivation itself. Each lesson is annotated with the set of theorems it is intended to exercise and a target band on the number of solution steps. Calibration checks that the shortest in-scope derivation (i) uses only theorems permitted at that point in the curriculum, (ii) invokes at least one of the lesson's own target skills—so that a problem cannot be "solved past" the intended concept by an earlier-lesson shortcut—and (iii) lands within the difficulty band. This distinguishes items that are merely *solvable* from items that are solvable *by the method the lesson is teaching, at the intended level*.

Validator and calibration outputs are returned to a repair model as structured feedback describing the constraint that failed and the corrective action required, without disclosing target values. The generator repairs the schema; the validate–repair cycle iterates to a fixed budget, retaining the best-scoring intermediate schema. Because the validator reasons over the formal schema rather than the surface text, its judgments are deterministic and, for the consistency and determinacy layers, constitute proofs of invalidity rather than probabilistic estimates.

## Natural-Language Realization

All three conditions share a two-stage realization pipeline that converts a schema into a student-facing problem. A deterministic renderer first produces a faithful but stylistically flat "functional" statement of the problem directly from the schema, guaranteeing that the natural-language item is a literal transcription of the underlying mathematics. A subsequent LLM prose layer then rewrites this statement into fluent, contextualized language—introducing a plausible real-world scenario and readable phrasing—under the constraint that every quantity, relationship, and the target are preserved. Holding realization constant across conditions ensures that measured quality differences reflect the schema entering realization, not the wording added afterward.

## Human Evaluation

### Rubric

Generated items are judged on three dimensions, each scored on a five-point scale (0–4) with anchored descriptors:

- **Geometric accuracy** (weight 0.50): the problem is mathematically correct, internally consistent, and solvable.
- **Lesson alignment** (weight 0.30): the problem targets the intended skill at an appropriate level of difficulty.
- **Linguistic clarity** (weight 0.20): the problem is unambiguous and well-posed in its wording.

A weighted composite summarizes overall usability, with geometric accuracy dominant because an inaccurate item is unusable regardless of its other properties. Dimension weights and scoring anchors were fixed prior to data collection.

### Rater Calibration and Inter-Rater Reliability

Prior to the main study, raters were calibrated on a small set of problems constructed to span the rubric—including well-formed items, items with deliberately introduced flaws of specific kinds (e.g., an over-specified target, an under-determined figure, a triangle-inequality violation, a mathematically valid but off-topic item), and borderline cases. Raters scored these items independently and without discussion. Inter-rater reliability was quantified per rubric dimension using Krippendorff's alpha for ordinal data. Proceeding to the main study was gated on a pre-specified agreement threshold; items of systematic disagreement were used to sharpen the rubric's anchors before the main study began. This calibration protocol both establishes the reliability of the measurement instrument and documents rater training, addressing a recurring methodological gap in prior item-generation evaluations.

### Procedure

In the main study, raters scored the full corpus of items—balanced across the ten lessons and the three QC conditions—one problem at a time. Presentation was **blind**: raters saw only the problem text, with no indication of the condition that produced it, and items were presented in randomized order to prevent condition- and position-based bias. Each rater independently scored every assigned item on all three dimensions, and responses were recorded at the granularity of one score per rater, item, and dimension.

### Analysis

The primary analysis compares the three QC conditions on each rubric dimension and on the composite score. Because scores are nested within raters, items, and lessons, we model dimension scores with mixed-effects models that include random effects for rater and for lesson/item, treating condition as the fixed effect of interest; this accounts for rater severity and for topic difficulty when estimating condition effects. We report per-dimension and composite differences between conditions with corresponding uncertainty, and we characterize the *distribution* of failure modes each condition leaves behind—separating genuine content defects from pedagogical misalignment—since the two implicate different remedies. Where a design-intent reference exists (the calibration set), we additionally report the agreement between automated QC decisions and both the reference key and aggregated human judgment, allowing the reliability of each QC strategy to be assessed directly rather than assumed.

## Implementation

Generation, natural-language repair, and the prose layer use a lightweight, lower-latency instruction-tuned LLM; the model-based judge in C2 uses a larger frontier model of the same family. Structured outputs are produced through constrained decoding against the schema. The symbolic validator, its theorem library, and the scope-and-difficulty calibration are implemented as a logic program over the formal representation and invoked through a thin bridge from the orchestration layer. LLM decoding for the QC and repair stages uses deterministic settings so that the pipeline is reproducible and the comparison between conditions is not confounded by sampling variance. Iteration budgets for both the model-based and symbolic loops are fixed and identical in spirit (a small bounded number of revision cycles), so that the two QC strategies are compared at matched refinement effort.
