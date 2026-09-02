"""Leakage checks (spec S.18, S.23).

No prompt that a model sees during solving, classification, experiment
selection or hypothesis revision may contain the oracle label, the canonical
strategy description, or latent generator parameters that are not visible in
the rendered problem.
"""

import json
import random
import zlib

import pytest

import prompts as P
from active import observations_from
from families import all_families, get_family
from schemas import HIDDEN_KEYS, Problem

FORBIDDEN_TOKENS = [
    "strategy_applies",
    "latent_parameters",
    "researcher_view",
    "instance_key",
    "want_applies",
    "oracle",
]



def _seed(*parts) -> int:
    """Process-stable seed: built-in hash() is salted per process."""
    return zlib.crc32("|".join(str(p) for p in parts).encode("utf-8"))

def sample_problems(n=6):
    out = []
    for name, fam in all_families().items():
        rng = random.Random(_seed(name))
        for template in fam.base_templates + fam.challenge_templates:
            for want in (True, False):
                out.append(fam.sample_random(rng, "medium", template, want_applies=want))
    return out


def all_prompt_text(prompt: dict) -> str:
    return f"{prompt['system']}\n{prompt['user']}"


def test_public_view_hides_researcher_metadata():
    for p in sample_problems():
        view = p.public_view()
        assert set(view) == {"id", "template", "text"}
        for key in HIDDEN_KEYS:
            assert key not in view


def test_solve_prompt_contains_only_the_problem_text():
    for p in sample_problems():
        text = all_prompt_text(P.solve_prompt(p))
        assert p.text in text
        for token in FORBIDDEN_TOKENS:
            assert token not in text
        assert p.human_solution == "" or p.human_solution not in text
        assert "APPLIES" not in text


def test_classify_prompt_never_leaks_the_label_or_the_canonical_strategy():
    for name, fam in all_families().items():
        rng = random.Random(1)
        for want in (True, False):
            p = fam.sample_random(rng, "medium", fam.base_templates[0], want_applies=want)
            text = all_prompt_text(
                P.classify_prompt("INDUCED S_HAT", "INDUCED H", p)
            )
            for token in FORBIDDEN_TOKENS:
                assert token not in text
            # the canonical strategy description is researcher-only
            assert fam.strategy_description not in text
            assert p.human_solution == "" or p.human_solution not in text
            assert str(p.exact_answer) not in text.replace(p.text, "")


def test_classify_prompt_does_not_contain_latent_parameters_that_are_hidden():
    """Latent values are allowed only when they are visible in the problem text."""
    for name, fam in all_families().items():
        rng = random.Random(2)
        for want in (True, False):
            p = fam.sample_random(rng, "medium", fam.base_templates[0], want_applies=want)
            prompt_text = all_prompt_text(P.classify_prompt("S", "H", p))
            outside = prompt_text.replace(p.text, "")
            for key, value in p.latent_parameters.items():
                if key in ("instance_key", "terms", "linearising_shifts"):
                    continue
                if isinstance(value, (int, float)) and abs(value) > 3:
                    assert str(value) not in outside, (name, key, value)


def test_induction_prompt_shows_only_seed_statements_and_solutions():
    for name, fam in all_families().items():
        rng = random.Random(3)
        seeds = fam.generate_seed_candidates(rng, 3, "medium")
        text = all_prompt_text(P.induction_prompt(seeds))
        for token in FORBIDDEN_TOKENS:
            assert token not in text
        assert fam.strategy_description not in text
        for p in seeds:
            assert p.text in text
            assert p.human_solution in text
            assert "SUCCESS" not in text and "FAILURE" not in text


def test_query_prompt_exposes_the_schema_but_no_labels():
    for name, fam in all_families().items():
        text = all_prompt_text(
            P.query_prompt("S", "H", fam.active_query_schema, 3, "")
        )
        for token in FORBIDDEN_TOKENS:
            assert token not in text
        assert fam.strategy_description not in text
        for feature, values in fam.active_query_schema.items():
            assert feature in text
            for v in values:
                assert v in text


def test_observations_hide_feature_values_by_default():
    for name, fam in all_families().items():
        rng = random.Random(4)
        problems = [
            fam.sample_random(rng, "medium", fam.base_templates[0], want_applies=w)
            for w in (True, False)
        ]
        obs = observations_from(problems, False, list(fam.active_query_schema))
        for o in obs:
            assert o.shown_features == {}
            rendered = o.render()
            assert "Features:" not in rendered
            assert o.outcome in ("SUCCESS", "FAILURE")
        text = all_prompt_text(P.revise_prompt("S", "H", obs))
        for token in FORBIDDEN_TOKENS:
            assert token not in text
        assert fam.strategy_description not in text


def test_observations_can_show_features_only_when_explicitly_enabled():
    fam = get_family("lte_valuation")
    rng = random.Random(5)
    p = fam.sample_random(rng, "medium", "valuation", want_applies=True)
    obs = observations_from([p], True, list(fam.active_query_schema))
    assert obs[0].shown_features
    assert "Features:" in obs[0].render()


def test_no_prompt_template_mentions_a_canonical_strategy_name():
    banned = [
        "lifting the exponent",
        "LTE",
        "multiplicative order",
        "half-order",
        "Mobius",
        "fixed point",
        "reciprocal substitution",
    ]
    for key, template in P.ALL_PROMPT_TEMPLATES.items():
        low = template.lower()
        for token in banned:
            assert token.lower() not in low, (key, token)


def test_seed_view_is_the_only_view_carrying_a_solution():
    for p in sample_problems():
        assert "solution" not in p.public_view()
        if p.human_solution:
            assert p.seed_view()["solution"] == p.human_solution
