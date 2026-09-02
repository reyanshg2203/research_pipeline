"""Stage 3b -- the Passive control, matched on adaptation output tokens.

Spec S.13/S.14.  Passive starts from the EXACT same induced S_hat and H0 as
Active, sees randomly drawn problems from the same adaptation distribution, and
receives the same kind of verified SUCCESS/FAILURE feedback.  It performs no
experiment-design generations.

Budget rule: keep adding random practice batches until

    T_passive >= T_active

and stop at the first batch that satisfies it, so the overshoot is the smallest
achievable at this batch granularity.  The realised numbers -- not the word
"matched" -- are what gets reported.
"""

from __future__ import annotations

import random
from typing import Dict, List, Set

from active import observations_from, revise_hypothesis
from families.base import ProblemFamily
from models import BaseModel
from sampling import derive_seed
from schemas import AdaptationResult, AdaptationRound, Generation, Problem


def run_passive(
    model: BaseModel,
    family: ProblemFamily,
    strategy: str,
    h0: str,
    difficulty: str,
    batch_size: int,
    target_output_tokens: int,
    max_new_tokens: Dict[str, int],
    master_seed: int,
    exclude_keys: Set[str],
    min_rounds: int = 1,
    max_rounds: int = 40,
    show_features: bool = False,
) -> AdaptationResult:
    rng = random.Random(
        derive_seed(master_seed, "passive_sampler", model.spec.alias, family.name)
    )
    hypothesis = h0
    trace: List[AdaptationRound] = []
    seen = set(exclude_keys)
    tokens_before = model.total_output_tokens
    budget_reached = False

    for round_index in range(max_rounds):
        spent = model.total_output_tokens - tokens_before
        if round_index >= min_rounds and spent >= target_output_tokens:
            budget_reached = True
            break

        problems: List[Problem] = []
        for i in range(batch_size):
            template = family.base_templates[i % len(family.base_templates)]
            for _ in range(400):
                p = family.sample_random(rng, difficulty, template, want_applies=None)
                if p.content_key() in seen:
                    continue
                family.validate_problem(p)
                seen.add(p.content_key())
                problems.append(p)
                break
            else:
                raise RuntimeError(
                    f"{family.name}: passive sampling exhausted at round {round_index}"
                )

        observations = observations_from(
            problems, show_features, list(family.active_query_schema)
        )
        hypothesis_before = hypothesis
        hypothesis, gen = revise_hypothesis(
            model, family, strategy, hypothesis, observations,
            max_new_tokens["revise"], master_seed, f"passive-r{round_index}",
        )
        trace.append(
            AdaptationRound(
                round_index=round_index,
                hypothesis_before=hypothesis_before,
                hypothesis_after=hypothesis,
                constraints=None,
                constraint_reason="",
                unsatisfiable_attempts=0,
                observations=observations,
                generations=[gen],
            )
        )
    else:
        budget_reached = (model.total_output_tokens - tokens_before) >= target_output_tokens

    spent = model.total_output_tokens - tokens_before
    mismatch = (
        (spent - target_output_tokens) / target_output_tokens
        if target_output_tokens
        else float("nan")
    )
    return AdaptationResult(
        condition="passive",
        model=model.spec.alias,
        family=family.name,
        h0=h0,
        strategy=strategy,
        final_hypothesis=hypothesis,
        rounds=trace,
        adaptation_output_tokens=spent,
        n_observations=sum(len(r.observations) for r in trace),
        n_revisions=len(trace),
        n_unsatisfiable=0,
        n_query_generations=0,
        notes={
            "difficulty": difficulty,
            "batch_size": batch_size,
            "target_output_tokens": target_output_tokens,
            "relative_mismatch": mismatch,
            "budget_reached": budget_reached,
            "max_rounds": max_rounds,
            "show_features_in_observations": show_features,
            "budget_cap_binding": (not budget_reached),
        },
    )
