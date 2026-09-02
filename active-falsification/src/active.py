"""Stage 3 -- the Active condition: model-designed falsification experiments.

Spec S.12.  The tested LLM never writes or executes code.  It selects between
one and three constraints from a fixed categorical schema; the generator
produces fresh problems satisfying them; the programmatic oracle -- not the
model -- decides SUCCESS or FAILURE.

Invalid or unsatisfiable requests are surfaced to the model verbatim as
``UNSATISFIABLE_REQUEST`` with the allowed schema, and it is given exactly one
reformulation attempt.  A request is NEVER silently translated into a different
experiment.
"""

from __future__ import annotations

import random
from typing import Any, Dict, List, Optional, Tuple

from families.base import ProblemFamily, UnsatisfiableConstraints
from models import BaseModel
from prompts import query_prompt, render_history, revise_prompt, unsat_prompt
from sampling import derive_seed
from schemas import AdaptationResult, AdaptationRound, Generation, Observation, Problem
from seed_induction import extract_json_object


class ActiveQueryError(RuntimeError):
    pass


def parse_constraints(response: str) -> Tuple[Optional[Dict[str, str]], str]:
    """Extract {'constraints', 'reason'} from a raw response."""
    parsed = extract_json_object(response)
    if not parsed:
        return None, ""
    constraints = parsed.get("constraints")
    reason = str(parsed.get("reason", "")).strip()
    if not isinstance(constraints, dict) or not constraints:
        return None, reason
    clean: Dict[str, str] = {}
    for key, value in constraints.items():
        if isinstance(value, (list, tuple)):
            clean[str(key)] = [str(v) for v in value]
        else:
            clean[str(key)] = str(value)
    return clean, reason


def sample_batch(
    family: ProblemFamily,
    rng: random.Random,
    constraints: Dict[str, str],
    difficulty: str,
    batch_size: int,
    exclude: set,
) -> List[Problem]:
    """Fresh problems satisfying ``constraints``.

    Raises :class:`UnsatisfiableConstraints` for a provably impossible request;
    returns fewer than ``batch_size`` problems when the attempt budget runs out.
    """
    out: List[Problem] = []
    seen = set(exclude)
    template_pool = family.base_templates
    for i in range(batch_size):
        template = template_pool[i % len(template_pool)]
        for _ in range(6):
            p = family.sample_conditioned(rng, constraints, difficulty, template)
            if p is None:
                break
            if p.content_key() in seen:
                continue
            family.validate_problem(p)
            seen.add(p.content_key())
            out.append(p)
            break
    return out


def observations_from(
    problems: List[Problem], show_features: bool, schema_keys: List[str]
) -> List[Observation]:
    """Turn oracle labels into the SUCCESS / FAILURE feedback shown to the model.

    Default (spec S.12.5): problem text and outcome only.  Even when
    ``show_features`` is enabled, ONLY query features can be shown -- oracle
    features are never rendered anywhere a model can see them.
    """
    out = []
    for p in problems:
        shown = (
            {k: p.query_features[k] for k in schema_keys if k in p.query_features}
            if show_features
            else {}
        )
        out.append(
            Observation(
                problem_id=p.id,
                text=p.text,
                outcome="SUCCESS" if p.strategy_applies else "FAILURE",
                shown_features=shown,
            )
        )
    return out


def revise_hypothesis(
    model: BaseModel,
    family: ProblemFamily,
    strategy: str,
    hypothesis: str,
    observations: List[Observation],
    max_new_tokens: int,
    master_seed: int,
    tag: str,
) -> Tuple[str, Generation]:
    prompt = revise_prompt(strategy, hypothesis, observations)
    seed = derive_seed(master_seed, "revise", model.spec.alias, family.name, tag)
    gen = model.generate(
        stage="revise",
        family=family.name,
        system=prompt["system"],
        user=prompt["user"],
        max_new_tokens=max_new_tokens,
        seed=seed % (2 ** 31),
        meta={"tag": tag, "n_observations": len(observations)},
    )
    parsed = extract_json_object(gen.response)
    new_h = None
    if parsed and parsed.get("hypothesis"):
        new_h = str(parsed["hypothesis"]).strip()
    if not new_h:
        # Keep the previous hypothesis and record the failure explicitly rather
        # than inventing a replacement.
        gen.meta["revision_parse_failed"] = True
        return hypothesis, gen
    return new_h, gen


def run_active(
    model: BaseModel,
    family: ProblemFamily,
    strategy: str,
    h0: str,
    difficulty: str,
    rounds: int,
    batch_size: int,
    max_new_tokens: Dict[str, int],
    master_seed: int,
    exclude_keys: set,
    show_features: bool = False,
    fallback_policy: str = "random",
) -> AdaptationResult:
    """Run the Active adaptation loop and return a fully logged result."""
    rng = random.Random(derive_seed(master_seed, "active_sampler", model.spec.alias, family.name))
    hypothesis = h0
    history: List[Dict[str, Any]] = []
    trace: List[AdaptationRound] = []
    seen = set(exclude_keys)
    total_unsat = 0
    query_generations = 0
    tokens_before = model.total_output_tokens

    for round_index in range(rounds):
        generations: List[Generation] = []
        unsat_this_round = 0
        constraints: Optional[Dict[str, str]] = None
        reason = ""
        problems: List[Problem] = []

        prompt = query_prompt(
            strategy,
            hypothesis,
            family.query_schema(),
            batch_size,
            render_history(history),
        )
        seed = derive_seed(master_seed, "query", model.spec.alias, family.name, round_index)
        gen = model.generate(
            stage="query",
            family=family.name,
            system=prompt["system"],
            user=prompt["user"],
            max_new_tokens=max_new_tokens["query"],
            seed=seed % (2 ** 31),
            meta={"round": round_index},
        )
        generations.append(gen)
        query_generations += 1
        requested, reason = parse_constraints(gen.response)

        # -- attempt 1, then exactly one reformulation --------------------
        for attempt in range(2):
            if requested is None:
                failure_reason = "no valid JSON object with a non-empty 'constraints' map"
                requested_display: Dict[str, Any] = {}
            else:
                failure_reason = ""
                requested_display = requested
                try:
                    family.check_constraints_wellformed(requested)
                    problems = sample_batch(
                        family, rng, requested, difficulty, batch_size, seen
                    )
                    if problems:
                        constraints = requested
                        break
                    failure_reason = (
                        "the constraints are individually valid but no fresh problem "
                        "satisfying all of them could be generated at this difficulty"
                    )
                except UnsatisfiableConstraints as exc:
                    failure_reason = exc.reason

            unsat_this_round += 1
            total_unsat += 1
            if attempt == 1:
                break
            uprompt = unsat_prompt(
                requested_display, failure_reason, family.query_schema()
            )
            seed2 = derive_seed(
                master_seed, "unsat", model.spec.alias, family.name, round_index
            )
            gen2 = model.generate(
                stage="query_retry",
                family=family.name,
                system=uprompt["system"],
                user=uprompt["user"],
                max_new_tokens=max_new_tokens["query"],
                seed=seed2 % (2 ** 31),
                meta={"round": round_index, "reason": failure_reason},
            )
            generations.append(gen2)
            query_generations += 1
            requested, reason = parse_constraints(gen2.response)

        # -- predefined neutral fallback ----------------------------------
        if not problems:
            # Spec S.12: after one failed reformulation, fall back to the SAME
            # unconstrained distribution Passive draws from, and log it.
            constraints = None
            for i in range(batch_size):
                template = family.base_templates[i % len(family.base_templates)]
                for _ in range(200):
                    p = family.sample_random(rng, difficulty, template, want_applies=None)
                    if p.content_key() in seen:
                        continue
                    family.validate_problem(p)
                    seen.add(p.content_key())
                    problems.append(p)
                    break
        else:
            for p in problems:
                seen.add(p.content_key())

        observations = observations_from(
            problems, show_features, list(family.query_schema())
        )
        hypothesis_before = hypothesis
        hypothesis, rev_gen = revise_hypothesis(
            model, family, strategy, hypothesis, observations,
            max_new_tokens["revise"], master_seed, f"active-r{round_index}",
        )
        generations.append(rev_gen)

        history.append(
            {
                "constraints": constraints,
                "delivered": len(problems),
                "requested": batch_size,
                "outcome_counts": {
                    "SUCCESS": sum(1 for o in observations if o.outcome == "SUCCESS"),
                    "FAILURE": sum(1 for o in observations if o.outcome == "FAILURE"),
                },
            }
        )
        trace.append(
            AdaptationRound(
                round_index=round_index,
                hypothesis_before=hypothesis_before,
                hypothesis_after=hypothesis,
                constraints=constraints,
                constraint_reason=reason,
                unsatisfiable_attempts=unsat_this_round,
                observations=observations,
                generations=generations,
            )
        )

    spent = model.total_output_tokens - tokens_before
    return AdaptationResult(
        condition="active",
        model=model.spec.alias,
        family=family.name,
        h0=h0,
        strategy=strategy,
        final_hypothesis=hypothesis,
        rounds=trace,
        adaptation_output_tokens=spent,
        n_observations=sum(len(r.observations) for r in trace),
        n_revisions=len(trace),
        n_unsatisfiable=total_unsat,
        n_query_generations=query_generations,
        notes={
            "difficulty": difficulty,
            "batch_size": batch_size,
            "show_features_in_observations": show_features,
            "fallback_policy": fallback_policy,
            "unsat_rate": total_unsat / max(1, query_generations),
        },
    )
