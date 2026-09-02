"""Stage 1 -- zero-shot difficulty calibration and seed screening (spec S.10).

Difficulty selection is PREDECLARED and depends only on zero-shot solving
accuracy.  It must never look at Active-vs-Passive outcomes.
"""

from __future__ import annotations

import json
from typing import Any, Dict, List, Optional, Sequence

from families.base import ProblemFamily
from grading import grade
from models import BaseModel
from prompts import solve_prompt
from sampling import derive_seed, stream
from schemas import Problem

#: Spec S.10.1 -- predeclared target band and target point for pooled zero-shot
#: accuracy.  Changing these after seeing adaptation results would be post-hoc
#: tuning; they are recorded in the run manifest.
# HUMAN_REVIEW_REQUIRED
TARGET_BAND = (0.20, 0.70)
TARGET_POINT = 0.45


def solve_once(
    model: BaseModel,
    family_name: str,
    problem: Problem,
    max_new_tokens: int,
    master_seed: int,
    tag: str,
) -> Dict[str, Any]:
    prompt = solve_prompt(problem)
    seed = derive_seed(master_seed, "solve", model.spec.alias, problem.id, tag)
    gen = model.generate(
        stage="solve",
        family=family_name,
        system=prompt["system"],
        user=prompt["user"],
        max_new_tokens=max_new_tokens,
        seed=seed % (2 ** 31),
        meta={"problem_id": problem.id, "tag": tag},
    )
    result = grade(gen.response, problem.exact_answer)
    return {
        "model": model.spec.alias,
        "family": family_name,
        "tag": tag,
        "problem_id": problem.id,
        "template": problem.template,
        "difficulty": problem.difficulty,
        "gold_answer": problem.exact_answer,
        "strategy_applies": problem.strategy_applies,  # researcher-side only
        "output_tokens": gen.output_tokens,
        "raw_response": gen.response,
        **result.to_json(),
    }


def run_difficulty_calibration(
    models: Sequence[BaseModel],
    family: ProblemFamily,
    per_tier: int,
    max_new_tokens: int,
    master_seed: int,
    difficulties: Sequence[str] = ("easy", "medium", "hard"),
) -> Dict[str, Any]:
    """Zero-shot solve `per_tier` problems per difficulty per model."""
    rng = stream(master_seed, "calibration_problems", family.name)
    problems: Dict[str, List[Problem]] = {}
    for difficulty in difficulties:
        items: List[Problem] = []
        seen = set()
        # calibration sets are label-balanced so that solving accuracy is not
        # dominated by whichever class happens to be easier
        wants = [True, False] * ((per_tier + 1) // 2)
        for i in range(per_tier):
            template = family.base_templates[i % len(family.base_templates)]
            for _ in range(400):
                p = family.sample_random(rng, difficulty, template, want_applies=wants[i])
                if p.content_key() in seen:
                    continue
                family.validate_problem(p)
                seen.add(p.content_key())
                items.append(p)
                break
            else:
                raise RuntimeError(
                    f"{family.name}: calibration sampling failed at {difficulty}"
                )
        problems[difficulty] = items

    runs: List[Dict[str, Any]] = []
    for model in models:
        for difficulty, items in problems.items():
            for p in items:
                runs.append(
                    solve_once(
                        model, family.name, p, max_new_tokens, master_seed, "calibration"
                    )
                )

    summary = summarise_calibration(runs)
    return {"family": family.name, "runs": runs, "summary": summary,
            "problems": {d: [p.to_json() for p in ps] for d, ps in problems.items()}}


def summarise_calibration(runs: Sequence[Dict[str, Any]]) -> List[Dict[str, Any]]:
    """Per (family, difficulty, model) and pooled-over-models accuracy."""
    out: List[Dict[str, Any]] = []
    keys = sorted({(r["family"], r["difficulty"], r["model"]) for r in runs})
    for family, difficulty, model in keys:
        sel = [r for r in runs if r["family"] == family
               and r["difficulty"] == difficulty and r["model"] == model]
        out.append(_acc_row(family, difficulty, model, sel))
    pooled_keys = sorted({(r["family"], r["difficulty"]) for r in runs})
    for family, difficulty in pooled_keys:
        sel = [r for r in runs if r["family"] == family and r["difficulty"] == difficulty]
        out.append(_acc_row(family, difficulty, "POOLED", sel))
    return out


def _acc_row(family: str, difficulty: str, model: str, sel: Sequence[Dict[str, Any]]) -> Dict[str, Any]:
    n = len(sel)
    correct = sum(1 for r in sel if r["correct"])
    parse_fail = sum(1 for r in sel if r["parse_failed"])
    tokens = sum(r["output_tokens"] for r in sel)
    return {
        "family": family,
        "difficulty": difficulty,
        "model": model,
        "n": n,
        "n_correct": correct,
        "accuracy": correct / n if n else float("nan"),
        "parse_failures": parse_fail,
        "parse_failure_rate": parse_fail / n if n else float("nan"),
        "mean_output_tokens": tokens / n if n else float("nan"),
    }


def select_difficulty(
    summary: Sequence[Dict[str, Any]],
    family: str,
    difficulties: Sequence[str] = ("easy", "medium", "hard"),
) -> Dict[str, Any]:
    """Predeclared rule: prefer pooled accuracy in TARGET_BAND, closest to TARGET_POINT.

    If no tier lands in the band, the tier closest to TARGET_POINT is selected and
    the result is flagged ``in_band=False`` so the authors can see it.
    """
    pooled = {
        r["difficulty"]: r["accuracy"]
        for r in summary
        if r["family"] == family and r["model"] == "POOLED"
    }
    available = {d: a for d, a in pooled.items() if d in difficulties and a == a}
    if not available:
        raise RuntimeError(f"no pooled calibration accuracy available for {family}")
    in_band = {d: a for d, a in available.items() if TARGET_BAND[0] <= a <= TARGET_BAND[1]}
    pool = in_band or available
    chosen = min(pool, key=lambda d: abs(pool[d] - TARGET_POINT))
    return {
        "family": family,
        "selected_difficulty": chosen,
        "pooled_accuracy": available[chosen],
        "in_band": bool(in_band),
        "target_band": list(TARGET_BAND),
        "target_point": TARGET_POINT,
        "all_pooled_accuracy": available,
        "rule": (
            "predeclared: prefer pooled zero-shot accuracy inside the target band, "
            "then take the tier closest to the target point; never uses "
            "Active-vs-Passive outcomes"
        ),
    }


# --------------------------------------------------------------------------
# seed-candidate screening (spec S.10.2)
# --------------------------------------------------------------------------


def screen_seed_candidates(
    models: Sequence[BaseModel],
    family: ProblemFamily,
    n_candidates: int,
    difficulty: str,
    max_new_tokens: int,
    master_seed: int,
) -> Dict[str, Any]:
    """Generate positive demonstrations and screen them zero-shot.

    The candidate list is a deterministic function of (master_seed, family), so
    every model screens the SAME candidates.  Selection happens in the runner,
    pooled over all models, which is what makes the seed set common to every
    model (spec S.24.3).
    """
    rng = stream(master_seed, "seed_candidates", family.name)
    candidates = family.generate_seed_candidates(rng, n_candidates, difficulty)

    runs: List[Dict[str, Any]] = []
    for model in models:
        for p in candidates:
            runs.append(
                solve_once(model, family.name, p, max_new_tokens, master_seed, "seed_screen")
            )

    solve_counts: Dict[str, int] = {p.id: 0 for p in candidates}
    for r in runs:
        if r["correct"]:
            solve_counts[r["problem_id"]] += 1

    return {
        "family": family.name,
        "difficulty": difficulty,
        "runs": runs,
        "candidates": [p.to_json() for p in candidates],
        "solve_counts": solve_counts,
    }


def select_seed_set(
    candidates: Sequence[Problem], solve_counts: Dict[str, int], n_seeds: int,
    templates: Sequence[str],
) -> List[Problem]:
    """Pick the common seed set, pooled over every model (spec S.10.2).

    Rank by pooled solve count ASCENDING -- seeds should be relatively difficult
    across the model pool -- then spread across surface templates so the model
    must abstract the method rather than memorise one presentation.
    """
    ordered = sorted(candidates, key=lambda p: (solve_counts.get(p.id, 0), p.id))
    per_template = max(1, n_seeds // max(1, len(templates)))
    chosen: List[Problem] = []
    used: Dict[str, int] = {}
    for p in ordered:
        if len(chosen) >= n_seeds:
            break
        if used.get(p.template, 0) >= per_template:
            continue
        used[p.template] = used.get(p.template, 0) + 1
        chosen.append(p)
    for p in ordered:  # top up if the diversity cap starved the selection
        if len(chosen) >= n_seeds:
            break
        if p not in chosen:
            chosen.append(p)
    return chosen


def seed_review_markdown(family: ProblemFamily, seeds: Sequence[Problem],
                         solve_counts: Dict[str, int]) -> str:
    """Human-review sheet for the chosen seed set (spec S.10.2)."""
    lines = [
        f"# Seed review -- family `{family.name}`",
        "",
        "The authors must read every seed below, check the mathematics, and tick",
        "the box before this seed set is used in a publication run.",
        "",
        f"Canonical strategy (RESEARCHER-ONLY, never shown to a model):",
        "",
        f"> {family.strategy_description}",
        "",
        "---",
        "",
    ]
    for i, p in enumerate(seeds, 1):
        lines += [
            f"## Seed {i} -- `{p.id}`",
            "",
            f"- template: `{p.template}`  |  difficulty: `{p.difficulty}`",
            f"- pooled zero-shot solve count: **{solve_counts.get(p.id, 0)}**",
            f"- oracle `strategy_applies`: **{p.strategy_applies}**",
            "",
            "**Problem**",
            "",
            f"> {p.text}",
            "",
            "**Verified solution shown to the model**",
            "",
            f"> {p.human_solution}",
            "",
            f"**Exact answer:** `{p.exact_answer}`",
            "",
            "**Researcher-side metadata (NOT shown to the model)**",
            "",
            "```json",
            json.dumps(p.latent_parameters, indent=2, default=str),
            "```",
            "",
            "- [ ] I have verified this problem, this solution and this answer by hand.",
            "",
            "---",
            "",
        ]
    return "\n".join(lines)
