"""Stage 2 -- seed-candidate screening and the common seed set.

Split out of ``src/calibration.py`` so that the Stage-1 zero-shot calibration
module contains nothing but difficulty calibration (calibration spec S.13).
Nothing in the Stage-1 pipeline imports this module.
"""

from __future__ import annotations

import json
from typing import Any, Dict, List, Sequence

from calibration import solve_once
from families.base import ProblemFamily
from models import BaseModel
from sampling import stream
from schemas import Problem


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
        if r["model_answer_correct"]:
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
