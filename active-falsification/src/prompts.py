"""Every prompt used anywhere in the pipeline.

Two hard rules, enforced by tests/test_no_leakage.py:

  1. No prompt may contain `strategy_applies`, a family's canonical
     `strategy_description`, a hidden gold label, or latent generator
     parameters that are not already visible in the rendered problem.
  2. The canonical strategy name is never revealed; the model works only from
     the strategy description S_hat that it induced itself.

docs/PROMPTS.md is generated from this module by scripts/export_prompts.py so
the documentation cannot drift from the code.
"""

from __future__ import annotations

import json
from typing import Dict, List, Sequence

from schemas import Observation, Problem, stable_hash

PROMPT_VERSION = "1.0.0"

# --------------------------------------------------------------------------
# A. zero-shot solver (Stage 1 calibration; also used for seed screening)
# --------------------------------------------------------------------------
#
# Ordinary zero-shot prompting: no worked examples, no seed demonstrations, no
# canonical strategy description, no H0, no features, no applicability labels,
# no hint about the intended strategy, and nothing about difficulty selection.
#
# NOTE -- one deliberate addition to the wording in the calibration spec S.5:
# the final line about exact form. Family 3 answers are reduced fractions, and
# without it a model that solves the problem correctly can still be scored wrong
# for returning a decimal. That would measure formatting compliance rather than
# mathematics and would inflate the parse-failure rate the spec asks us to watch
# (S.12). It says nothing about any strategy.
# HUMAN_REVIEW_REQUIRED

SOLVE_SYSTEM = (
    "You are solving a mathematics competition problem.\n\n"
    "Solve the problem independently.\n\n"
    "At the very end, write:\n"
    "FINAL_ANSWER: <answer>\n\n"
    "If the problem explicitly permits no solution and no solution exists, use:\n"
    "FINAL_ANSWER: NONE\n\n"
    "Give the answer in exact form: an integer, or a reduced fraction such as "
    "-7/2. Never give a decimal approximation."
)

SOLVE_USER = "{problem_text}"


def solve_prompt(problem: Problem) -> Dict[str, str]:
    return {
        "system": SOLVE_SYSTEM,
        "user": SOLVE_USER.format(problem_text=problem.public_view()["text"]),
    }


# --------------------------------------------------------------------------
# B. strategy + H0 induction from seed demonstrations
# --------------------------------------------------------------------------

INDUCE_SYSTEM = (
    "You are a mathematician studying a collection of solved problems in order "
    "to extract a reusable solution method and to state precisely when that "
    "method works."
)

INDUCE_USER = """Below are {n} solved problems. They were all solved by the same underlying method.

{demonstrations}

Do two things.

1. STRATEGY: describe, in your own words, the general reusable method these solutions share. Describe the method itself, not the individual numbers.

2. HYPOTHESIS: state a falsifiable rule for WHEN this method will succeed on a new problem of this kind, and when it will fail. The rule must be checkable from the statement of a new problem. It must be a genuine applicability condition, not a restatement of the method. It must be specific enough that some problems of this kind would violate it.

Respond with a single JSON object and nothing else:

{{"strategy": "...", "hypothesis": "..."}}"""


def induction_prompt(seeds: Sequence[Problem]) -> Dict[str, str]:
    blocks = []
    for i, p in enumerate(seeds, 1):
        view = p.seed_view()
        blocks.append(
            f"--- Example {i} ---\n"
            f"Problem: {view['text']}\n"
            f"Solution: {view['solution']}\n"
            f"Answer: {view['answer']}"
        )
    return {
        "system": INDUCE_SYSTEM,
        "user": INDUCE_USER.format(n=len(seeds), demonstrations="\n\n".join(blocks)),
    }


# --------------------------------------------------------------------------
# C. boundary classification (the primary evaluation)
# --------------------------------------------------------------------------

CLASSIFY_SYSTEM = (
    "You decide whether a solution method applies to a problem. "
    "You do not solve the problem."
)

CLASSIFY_USER = """Method:
{strategy}

Rule for when the method works:
{hypothesis}

New problem:
{problem_text}

Using the rule above, decide whether applying the method to this problem would succeed.

Answer with exactly one of these two tokens and nothing else:
APPLIES
DOES_NOT_APPLY"""


def classify_prompt(strategy: str, hypothesis: str, problem: Problem) -> Dict[str, str]:
    return {
        "system": CLASSIFY_SYSTEM,
        "user": CLASSIFY_USER.format(
            strategy=strategy.strip(),
            hypothesis=hypothesis.strip(),
            problem_text=problem.public_view()["text"],
        ),
    }


# --------------------------------------------------------------------------
# D. Active experiment selection
# --------------------------------------------------------------------------

QUERY_SYSTEM = (
    "You are designing experiments to test and refine your own hypothesis. "
    "You cannot write code and you cannot choose specific numbers. You may only "
    "request problems by specifying values for the listed categorical features."
)

QUERY_USER = """Method:
{strategy}

Your current rule for when the method works:
{hypothesis}

{history}

You may now request a batch of {batch_size} fresh problems by constraining between 1 and 3 of the following features. Every problem you receive will satisfy your constraints, and you will be told, for each one, whether applying the method actually succeeded.

Available features and their allowed values:
{schema}

Choose constraints that are most likely to FALSIFY or sharpen your current rule: pick a region where your rule makes a confident prediction that you are least sure of.

Respond with a single JSON object and nothing else:

{{"constraints": {{"feature_name": "allowed_value"}}, "reason": "one or two sentences"}}"""


def query_prompt(
    strategy: str,
    hypothesis: str,
    schema: Dict[str, List[str]],
    batch_size: int,
    history: str,
) -> Dict[str, str]:
    schema_lines = "\n".join(
        f"- {name}: {', '.join(values)}" for name, values in schema.items()
    )
    return {
        "system": QUERY_SYSTEM,
        "user": QUERY_USER.format(
            strategy=strategy.strip(),
            hypothesis=hypothesis.strip(),
            schema=schema_lines,
            batch_size=batch_size,
            history=history.strip() or "This is your first experiment.",
        ),
    }


# --------------------------------------------------------------------------
# E. hypothesis revision (identical wording for Active and Passive)
# --------------------------------------------------------------------------

REVISE_SYSTEM = (
    "You update a hypothesis in the light of new evidence. Be precise and "
    "conservative: keep what the evidence supports and change what it refutes."
)

REVISE_USER = """Method:
{strategy}

Your current rule for when the method works:
{hypothesis}

New evidence. Each problem below was solved with the method, and the outcome says whether the method produced the correct result.

{observations}

Revise your rule so that it is consistent with all of the evidence you have seen. The revised rule must still be a falsifiable, checkable condition stated in terms of features of a problem statement, not a list of the specific problems above.

Respond with a single JSON object and nothing else:

{{"hypothesis": "..."}}"""


def revise_prompt(
    strategy: str, hypothesis: str, observations: Sequence[Observation]
) -> Dict[str, str]:
    blocks = [f"--- Observation {i} ---\n{o.render()}" for i, o in enumerate(observations, 1)]
    return {
        "system": REVISE_SYSTEM,
        "user": REVISE_USER.format(
            strategy=strategy.strip(),
            hypothesis=hypothesis.strip(),
            observations="\n\n".join(blocks),
        ),
    }


# --------------------------------------------------------------------------
# F. invalid Active request -> one reformulation attempt
# --------------------------------------------------------------------------

UNSAT_SYSTEM = QUERY_SYSTEM

UNSAT_USER = """UNSATISFIABLE_REQUEST

Your requested constraints could not be satisfied.

You requested:
{requested}

Reason: {reason}

Available features and their allowed values:
{schema}

Reformulate your request once, using only the feature names and values listed above, and using between 1 and 3 constraints.

Respond with a single JSON object and nothing else:

{{"constraints": {{"feature_name": "allowed_value"}}, "reason": "one or two sentences"}}"""


def unsat_prompt(
    requested: Dict[str, str], reason: str, schema: Dict[str, List[str]]
) -> Dict[str, str]:
    schema_lines = "\n".join(
        f"- {name}: {', '.join(values)}" for name, values in schema.items()
    )
    return {
        "system": UNSAT_SYSTEM,
        "user": UNSAT_USER.format(
            requested=json.dumps(requested, sort_keys=True),
            reason=reason,
            schema=schema_lines,
        ),
    }


# --------------------------------------------------------------------------
# history rendering for the Active loop
# --------------------------------------------------------------------------


def render_history(rounds: Sequence[dict], max_rounds: int = 3) -> str:
    """Compact summary of recent experiments shown to the Active selector."""
    if not rounds:
        return ""
    lines = ["Experiments you have already run:"]
    for r in rounds[-max_rounds:]:
        constraints = json.dumps(r.get("constraints") or {}, sort_keys=True)
        outcomes = r.get("outcome_counts", {})
        lines.append(
            f"- constraints {constraints} -> "
            f"{outcomes.get('SUCCESS', 0)} SUCCESS, {outcomes.get('FAILURE', 0)} FAILURE"
        )
    return "\n".join(lines)


# --------------------------------------------------------------------------
# versioning
# --------------------------------------------------------------------------

ALL_PROMPT_TEMPLATES = {
    "A_solve_system": SOLVE_SYSTEM,
    "A_solve_user": SOLVE_USER,
    "B_induce_system": INDUCE_SYSTEM,
    "B_induce_user": INDUCE_USER,
    "C_classify_system": CLASSIFY_SYSTEM,
    "C_classify_user": CLASSIFY_USER,
    "D_query_system": QUERY_SYSTEM,
    "D_query_user": QUERY_USER,
    "E_revise_system": REVISE_SYSTEM,
    "E_revise_user": REVISE_USER,
    "F_unsat_system": UNSAT_SYSTEM,
    "F_unsat_user": UNSAT_USER,
}


def prompts_hash() -> str:
    return stable_hash({"version": PROMPT_VERSION, **ALL_PROMPT_TEMPLATES})
