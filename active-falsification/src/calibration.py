"""Stage 1 -- zero-shot difficulty calibration.  NOTHING ELSE.

This module answers exactly one question:

    For each problem family, which predefined difficulty tier gives the models
    meaningful but nontrivial zero-shot solving accuracy?

It performs ordinary zero-shot solving and exact grading.  It does not touch
seeds, strategy induction, H0, Active, Passive, hidden tests, token matching or
the competition OOD set, and it must never import those modules.

The difficulty-selection rule is PREDECLARED and reads only zero-shot solving
accuracy.  It never sees Active-vs-Passive outcomes, which is the whole point:
it exists to make post-hoc difficulty selection impossible.
"""

from __future__ import annotations

import statistics
from typing import Any, Dict, List, Optional, Sequence

from families.base import ProblemFamily
from grading import grade
from models import BaseModel
from prompts import solve_prompt
from sampling import derive_seed, stream
from schemas import Problem

# --------------------------------------------------------------------------
# PREDECLARED difficulty-selection rule (calibration spec S.11)
# --------------------------------------------------------------------------
# HUMAN_REVIEW_REQUIRED -- these constants are the rule.  Changing them after
# seeing any adaptation result would be post-hoc tuning.  They are written into
# every run manifest and every report.

TARGET_POINT = 0.45
PREFERRED_RANGE = (0.20, 0.70)

#: Tie-breaking.  The spec permits choosing the harder tier ONLY if that is
#: explicitly encoded in advance; otherwise an exact tie goes to human review.
#: "human_review" is the default precisely so that no tie is resolved silently.
TIE_BREAKER = "human_review"          # or "harder", if the authors predeclare it
DIFFICULTY_ORDER = ["easy", "medium", "hard"]

NO_VIABLE_TIER = "NO_VIABLE_TIER"
TIE_NEEDS_REVIEW = "TIE_NEEDS_HUMAN_REVIEW"

#: Diagnostic thresholds (calibration spec S.12).  Warnings never change the
#: selected tier; they trigger human review of what the generator means by
#: easy / medium / hard.
INVERSION_MARGIN = 0.15
CEILING = 0.85
FLOOR = 0.10
MAX_PARSE_FAILURE_RATE = 0.10
SPREAD_CEILING = 0.85
SPREAD_FLOOR = 0.15


class ProblemBankError(RuntimeError):
    """Raised when a validated calibration bank could not be built."""


# --------------------------------------------------------------------------
# the fixed problem bank -- built ONCE, shared by every model
# --------------------------------------------------------------------------


def build_problem_bank(
    families: Dict[str, ProblemFamily],
    per_tier: int,
    master_seed: int,
    difficulties: Sequence[str] = tuple(DIFFICULTY_ORDER),
    max_validation_failures: int = 20,
) -> Dict[str, Any]:
    """Generate and independently validate the shared calibration bank.

    Calibration spec S.4: one bank, generated once from the master seed, used by
    every model.  Spec S.3: every problem is validated against the family's own
    oracle BEFORE any model sees it; a failure is logged, the problem is never
    sent to a model, and a replacement is drawn.  Repeated failures abort.

    Balanced on ``strategy_applies`` so solving accuracy is not dominated by
    whichever class happens to be easier.  The label itself is researcher-side
    metadata and never reaches a prompt.
    """
    bank: Dict[str, Dict[str, List[Problem]]] = {}
    validation_failures: List[Dict[str, str]] = []

    for name, family in families.items():
        bank[name] = {}
        for difficulty in difficulties:
            rng = stream(master_seed, "calibration_bank", name, difficulty)
            wants = [True, False] * ((per_tier + 1) // 2)
            items: List[Problem] = []
            seen: set = set()
            failures_here = 0
            for i in range(per_tier):
                template = family.base_templates[i % len(family.base_templates)]
                placed = False
                for _ in range(500):
                    problem = family.sample_random(
                        rng, difficulty, template, want_applies=wants[i]
                    )
                    if problem.content_key() in seen:
                        continue
                    try:
                        family.validate_problem(problem)
                    except Exception as exc:  # noqa: BLE001
                        failures_here += 1
                        validation_failures.append({
                            "family": name,
                            "difficulty": difficulty,
                            "problem_id": problem.id,
                            "error": f"{type(exc).__name__}: {exc}",
                        })
                        if failures_here > max_validation_failures:
                            raise ProblemBankError(
                                f"{name}/{difficulty}: {failures_here} validation "
                                f"failures while building the calibration bank; "
                                f"refusing to continue. See errors.log."
                            )
                        continue
                    seen.add(problem.content_key())
                    items.append(problem)
                    placed = True
                    break
                if not placed:
                    raise ProblemBankError(
                        f"{name}/{difficulty}: could not draw a valid problem "
                        f"{i + 1}/{per_tier}"
                    )
            bank[name][difficulty] = items

    return {"bank": bank, "validation_failures": validation_failures}


def bank_public_records(bank: Dict[str, Dict[str, List[Problem]]]) -> List[Dict[str, Any]]:
    """The saved bank file: identity, public text, exact answer, seed.

    Researcher-only metadata (features, oracle diagnostics, latent parameters)
    is stored separately and never enters a prompt.
    """
    rows = []
    for family, tiers in bank.items():
        for difficulty, problems in tiers.items():
            for p in problems:
                rows.append({
                    "problem_id": p.id,
                    "family": family,
                    "difficulty": difficulty,
                    "template": p.template,
                    "problem_text": p.text,
                    "exact_answer": p.exact_answer,
                    "generation_seed": p.generation_seed,
                })
    return rows


def bank_researcher_records(
    bank: Dict[str, Dict[str, List[Problem]]]
) -> List[Dict[str, Any]]:
    rows = []
    for family, tiers in bank.items():
        for difficulty, problems in tiers.items():
            rows.append({
                "family": family,
                "difficulty": difficulty,
                "problems": [p.to_json() for p in problems],
            })
    return rows


# --------------------------------------------------------------------------
# zero-shot solving -- ONE attempt per model per problem
# --------------------------------------------------------------------------


def solve_once(
    model: BaseModel,
    family_name: str,
    problem: Problem,
    max_new_tokens: int,
    master_seed: int,
    tag: str = "calibration",
) -> Dict[str, Any]:
    """One zero-shot attempt.  No majority vote, no retry, no second attempt.

    A parse failure is recorded as ``unparsed`` and scored incorrect for the
    primary accuracy; parsed-only accuracy is reported separately.
    """
    prompt = solve_prompt(problem)
    seed = derive_seed(master_seed, "solve", model.spec.alias, problem.id, tag)
    generation = model.generate(
        stage="solve",
        family=family_name,
        system=prompt["system"],
        user=prompt["user"],
        max_new_tokens=max_new_tokens,
        seed=seed % (2 ** 31),
        meta={"problem_id": problem.id, "tag": tag},
    )
    result = grade(generation.response, problem.exact_answer)
    return {
        "model_alias": model.spec.alias,
        "model_id": model.spec.model_id,
        "model": model.spec.alias,          # kept for downstream summarisers
        "family": family_name,
        "difficulty": problem.difficulty,
        "template": problem.template,
        "problem_id": problem.id,
        "problem_text": problem.text,
        "gold_answer": problem.exact_answer,
        "exact_answer": problem.exact_answer,
        "raw_response": generation.response,
        "parsed_answer": result.parsed,
        # `correct` here means "the model's ANSWER was right", never strategy
        # applicability; `model_answer_correct` is the unambiguous alias and the
        # two are always identical.
        "correct": result.correct,
        "model_answer_correct": result.correct,
        "unparsed": result.parse_failed,
        "parse_failed": result.parse_failed,
        "raw_span": result.raw_span,
        "input_tokens": generation.prompt_tokens,
        "output_tokens": generation.output_tokens,
        "precision": model.config.get("precision"),
        "generation_seed": problem.generation_seed,
        "strategy_applies": problem.strategy_applies,   # researcher-side only
        "tag": tag,
    }


def run_zero_shot_calibration(
    model: BaseModel,
    families: Dict[str, ProblemFamily],
    bank: Dict[str, Dict[str, List[Problem]]],
    max_new_tokens: int,
    master_seed: int,
    progress: bool = True,
) -> List[Dict[str, Any]]:
    """Solve the whole shared bank once with one model."""
    rows: List[Dict[str, Any]] = []
    for family_name in families:
        for difficulty, problems in bank[family_name].items():
            for problem in problems:
                rows.append(
                    solve_once(
                        model, family_name, problem, max_new_tokens, master_seed
                    )
                )
            if progress:
                done = [
                    r for r in rows
                    if r["family"] == family_name and r["difficulty"] == difficulty
                ]
                n_ok = sum(1 for r in done if r["correct"])
                print(f"    {model.spec.alias:22} {family_name:24} {difficulty:6} "
                      f"{n_ok}/{len(done)} correct")
    return rows


# --------------------------------------------------------------------------
# metrics
# --------------------------------------------------------------------------


def _cell_stats(rows: Sequence[Dict[str, Any]]) -> Dict[str, Any]:
    n = len(rows)
    correct = sum(1 for r in rows if r["correct"])
    unparsed = sum(1 for r in rows if r["unparsed"])
    parsed = n - unparsed
    parsed_correct = sum(1 for r in rows if r["correct"] and not r["unparsed"])
    tokens = [r["output_tokens"] for r in rows]
    return {
        "n": n,
        "correct": correct,
        "accuracy": correct / n if n else float("nan"),
        "unparsed": unparsed,
        "parse_failure_rate": unparsed / n if n else float("nan"),
        "accuracy_parsed_only": parsed_correct / parsed if parsed else float("nan"),
        "mean_output_tokens": statistics.mean(tokens) if tokens else float("nan"),
        "median_output_tokens": statistics.median(tokens) if tokens else float("nan"),
    }


def summarise_by_cell(rows: Sequence[Dict[str, Any]]) -> List[Dict[str, Any]]:
    """One row per model x family x difficulty (calibration spec S.17)."""
    out = []
    keys = sorted({(r["model_alias"], r["family"], r["difficulty"]) for r in rows})
    for model, family, difficulty in keys:
        sel = [r for r in rows if (r["model_alias"], r["family"], r["difficulty"])
               == (model, family, difficulty)]
        out.append({"model": model, "family": family, "difficulty": difficulty,
                    **_cell_stats(sel)})
    return sorted(out, key=lambda r: (r["family"], DIFFICULTY_ORDER.index(r["difficulty"]),
                                      r["model"]))


def pooled_by_difficulty(rows: Sequence[Dict[str, Any]]) -> List[Dict[str, Any]]:
    """One row per family x difficulty, pooled over models (spec S.18)."""
    out = []
    for family, difficulty in sorted({(r["family"], r["difficulty"]) for r in rows}):
        sel = [r for r in rows
               if r["family"] == family and r["difficulty"] == difficulty]
        stats = _cell_stats(sel)
        accuracy = stats["accuracy"]
        out.append({
            "family": family,
            "difficulty": difficulty,
            "n_total": stats["n"],
            "accuracy_pooled": accuracy,
            "distance_from_target_0_45": (
                abs(accuracy - TARGET_POINT) if accuracy == accuracy else float("nan")
            ),
            "within_preferred_range": bool(
                accuracy == accuracy
                and PREFERRED_RANGE[0] <= accuracy <= PREFERRED_RANGE[1]
            ),
            "unparsed": stats["unparsed"],
            "parse_failure_rate": stats["parse_failure_rate"],
            "accuracy_parsed_only": stats["accuracy_parsed_only"],
            "mean_output_tokens": stats["mean_output_tokens"],
        })
    return sorted(out, key=lambda r: (r["family"],
                                      DIFFICULTY_ORDER.index(r["difficulty"])))


# --------------------------------------------------------------------------
# the predeclared selection rule
# --------------------------------------------------------------------------

#: Report-safe wording. The calibration report must contain no Stage-2
#: vocabulary at all (calibration spec S.20), so the excluded inputs are named
#: only in the manifest, via RULE_EXCLUDED_INPUTS below.
RULE_TEXT = (
    f"predeclared: among tiers whose POOLED zero-shot accuracy lies in "
    f"[{PREFERRED_RANGE[0]}, {PREFERRED_RANGE[1]}], select the tier closest to "
    f"{TARGET_POINT}; if no tier qualifies, mark {NO_VIABLE_TIER} and select "
    f"nothing. The rule is a pure function of zero-shot solving accuracy and "
    f"reads no result from any later stage of the experiment."
)

#: Recorded in the run manifest so the exclusion is auditable by name.
RULE_EXCLUDED_INPUTS = [
    "h0_boundary_accuracy",
    "active_adaptation_result",
    "passive_adaptation_result",
    "any_strategy_boundary_metric",
    "any_hidden_test_result",
]


def select_difficulty(
    pooled: Sequence[Dict[str, Any]], family: str
) -> Dict[str, Any]:
    """Apply the predeclared rule.  Never silently selects an out-of-range tier."""
    accuracies = {
        r["difficulty"]: r["accuracy_pooled"]
        for r in pooled
        if r["family"] == family and r["accuracy_pooled"] == r["accuracy_pooled"]
    }
    if not accuracies:
        raise RuntimeError(f"no pooled calibration accuracy available for {family}")

    viable = {
        d: a for d, a in accuracies.items()
        if PREFERRED_RANGE[0] <= a <= PREFERRED_RANGE[1]
    }
    base = {
        "family": family,
        "accuracies": accuracies,
        "target": TARGET_POINT,
        "preferred_range": list(PREFERRED_RANGE),
        "rule": RULE_TEXT,
        "tie_breaker": TIE_BREAKER,
    }
    if not viable:
        return {**base, "selected": None, "status": NO_VIABLE_TIER,
                "reason": (
                    f"no tier has pooled accuracy in "
                    f"[{PREFERRED_RANGE[0]}, {PREFERRED_RANGE[1]}]; "
                    f"the family generator needs human review before Stage 2"
                )}

    best = min(abs(a - TARGET_POINT) for a in viable.values())
    tied = sorted(
        (d for d, a in viable.items() if abs(a - TARGET_POINT) == best),
        key=DIFFICULTY_ORDER.index,
    )
    if len(tied) > 1:
        if TIE_BREAKER == "harder":
            chosen = tied[-1]
            return {**base, "selected": chosen, "status": "OK",
                    "pooled_accuracy": viable[chosen],
                    "tied_tiers": tied,
                    "reason": "exact tie resolved by the predeclared 'harder' rule"}
        return {**base, "selected": None, "status": TIE_NEEDS_REVIEW,
                "tied_tiers": tied,
                "reason": (
                    f"tiers {tied} are equally close to {TARGET_POINT} and the "
                    f"predeclared tie-breaker is '{TIE_BREAKER}', so the choice "
                    f"is left to the authors"
                )}
    chosen = tied[0]
    return {**base, "selected": chosen, "status": "OK",
            "pooled_accuracy": viable[chosen],
            "reason": f"closest to {TARGET_POINT} within {list(PREFERRED_RANGE)}"}


# --------------------------------------------------------------------------
# diagnostics (calibration spec S.12) -- warnings never change the selection
# --------------------------------------------------------------------------


def diagnostics(
    pooled: Sequence[Dict[str, Any]], per_cell: Sequence[Dict[str, Any]], family: str
) -> List[str]:
    warnings: List[str] = []
    acc = {r["difficulty"]: r["accuracy_pooled"] for r in pooled
           if r["family"] == family}
    have = [d for d in DIFFICULTY_ORDER if d in acc and acc[d] == acc[d]]

    for lower, higher in (("easy", "medium"), ("medium", "hard")):
        if lower in acc and higher in acc:
            if acc[lower] + INVERSION_MARGIN < acc[higher]:
                warnings.append(
                    f"difficulty inversion: pooled accuracy on '{lower}' "
                    f"({acc[lower]:.2f}) is far below '{higher}' ({acc[higher]:.2f}); "
                    f"the generator's notion of difficulty needs review"
                )
    if have and all(acc[d] > CEILING for d in have):
        warnings.append(
            f"all tiers above {CEILING:.2f}: the family is too easy for this model "
            f"pool and leaves no headroom"
        )
    if have and all(acc[d] < FLOOR for d in have):
        warnings.append(
            f"all tiers below {FLOOR:.2f}: the family is too hard for this model "
            f"pool; zero-shot accuracy carries almost no signal"
        )
    for row in pooled:
        if row["family"] != family:
            continue
        if row["parse_failure_rate"] == row["parse_failure_rate"] and \
           row["parse_failure_rate"] > MAX_PARSE_FAILURE_RATE:
            warnings.append(
                f"parse failures on '{row['difficulty']}' are "
                f"{row['parse_failure_rate']:.0%} (> {MAX_PARSE_FAILURE_RATE:.0%}); "
                f"accuracy here may be measuring output format, not mathematics"
            )
    for difficulty in DIFFICULTY_ORDER:
        cells = [r for r in per_cell
                 if r["family"] == family and r["difficulty"] == difficulty]
        if len(cells) < 2:
            continue
        top = max(cells, key=lambda r: r["accuracy"])
        bottom = min(cells, key=lambda r: r["accuracy"])
        if top["accuracy"] > SPREAD_CEILING and bottom["accuracy"] < SPREAD_FLOOR:
            warnings.append(
                f"on '{difficulty}', {top['model']} is at ceiling "
                f"({top['accuracy']:.2f}) while {bottom['model']} is at floor "
                f"({bottom['accuracy']:.2f}); pooling across the model pool may "
                f"hide the disagreement"
            )
    return warnings


# --------------------------------------------------------------------------
# human-readable report (calibration spec S.20)
# --------------------------------------------------------------------------


def calibration_report(
    per_cell: Sequence[Dict[str, Any]],
    pooled: Sequence[Dict[str, Any]],
    selections: Dict[str, Dict[str, Any]],
    warnings: Dict[str, List[str]],
    manifest: Dict[str, Any],
) -> str:
    models = sorted({r["model"] for r in per_cell})
    lines = [
        "# Zero-shot calibration report",
        "",
        "Stage 1 only. This report contains zero-shot solving accuracy and the",
        "predeclared difficulty selection. It contains no strategy-boundary,",
        "adaptation or comparison result of any kind.",
        "",
        f"- run: `{manifest.get('run_id', '')}`",
        f"- timestamp: {manifest.get('timestamp_utc', '')}",
        f"- git commit: `{manifest.get('git_commit')}`",
        f"- precision: `{manifest.get('precision')}`",
        f"- models: {', '.join(models)}",
        f"- problems per family per tier: {manifest.get('calibration_per_tier')}",
        f"- master seed: {manifest.get('master_seed')}",
        "",
        "## Selection rule",
        "",
        f"> {RULE_TEXT}",
        "",
    ]
    if manifest.get("contains_mock_model"):
        lines += [
            "> **This run used the offline MOCK model. The numbers below are a",
            "> pipeline test and are NOT scientific results.**",
            "",
        ]

    for family in sorted({r["family"] for r in pooled}):
        lines += [f"## `{family}`", "", "### Accuracy by model and tier", ""]
        header = "| model | " + " | ".join(DIFFICULTY_ORDER) + " |"
        lines += [header, "|" + "---|" * (len(DIFFICULTY_ORDER) + 1)]
        for model in models:
            cells = []
            for difficulty in DIFFICULTY_ORDER:
                row = next((r for r in per_cell if r["model"] == model
                            and r["family"] == family
                            and r["difficulty"] == difficulty), None)
                cells.append(
                    f"{row['accuracy']:.2f} ({row['correct']}/{row['n']})"
                    if row else "—"
                )
            lines.append(f"| {model} | " + " | ".join(cells) + " |")

        lines += ["", "### Pooled over models", "",
                  "| tier | n | pooled accuracy | distance from 0.45 | in range | "
                  "parse failures | mean output tokens |",
                  "|---|---|---|---|---|---|---|"]
        for difficulty in DIFFICULTY_ORDER:
            row = next((r for r in pooled if r["family"] == family
                        and r["difficulty"] == difficulty), None)
            if not row:
                continue
            lines.append(
                f"| {difficulty} | {row['n_total']} | {row['accuracy_pooled']:.3f} | "
                f"{row['distance_from_target_0_45']:.3f} | "
                f"{'yes' if row['within_preferred_range'] else 'no'} | "
                f"{row['unparsed']} ({row['parse_failure_rate']:.0%}) | "
                f"{row['mean_output_tokens']:.0f} |"
            )

        selection = selections[family]
        lines += ["", "### Selected tier", ""]
        if selection.get("selected"):
            lines.append(
                f"**{selection['selected']}** — pooled accuracy "
                f"{selection['pooled_accuracy']:.3f}. {selection['reason']}."
            )
        else:
            lines.append(
                f"**{selection['status']}** — no tier selected. "
                f"{selection['reason']}."
            )
            lines.append("")
            lines.append("All three pooled accuracies: " + ", ".join(
                f"{d} = {a:.3f}" for d, a in sorted(
                    selection["accuracies"].items(),
                    key=lambda kv: DIFFICULTY_ORDER.index(kv[0]))
            ) + ".")

        family_warnings = warnings.get(family, [])
        lines += ["", "### Warnings", ""]
        if family_warnings:
            lines.append(
                "These do not change the selected tier. They ask the authors to "
                "review what this generator means by easy / medium / hard."
            )
            lines.append("")
            lines += [f"- {w}" for w in family_warnings]
        else:
            lines.append("None.")
        lines.append("")

    lines += [
        "---",
        "",
        "## Next step",
        "",
        "Stage 2 has not been run. It must not be started until the authors",
        "approve the tiers above.",
        "",
    ]
    return "\n".join(lines)
