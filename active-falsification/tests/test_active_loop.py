"""Active/Passive loop behaviour (spec S.12, S.13, S.14).

Uses a scripted model so the exact sequence of model responses -- including
malformed and unsatisfiable requests -- is under test control.
"""

import json
import random

import pytest

from active import parse_constraints, run_active
from families import get_family
from models import ModelSpec
from models import BaseModel
from passive import run_passive
from schemas import Problem

MNT = {"solve": 64, "induce": 64, "query": 64, "revise": 64, "classify": 16}


class ScriptedModel(BaseModel):
    """Replays a fixed list of responses, one per generate() call."""

    is_mock = True

    def __init__(self, responses, tokens_per_call=10):
        super().__init__(ModelSpec("scripted", "scripted://test", "n/a"), {})
        self.responses = list(responses)
        self.tokens_per_call = tokens_per_call
        self.calls = []

    def _generate(self, system, user, max_new_tokens, seed):
        self.calls.append({"system": system, "user": user})
        text = self.responses.pop(0) if self.responses else '{"hypothesis": "fallback"}'
        return text, self.tokens_per_call, 5


def constraints_response(constraints, reason="probe"):
    return json.dumps({"constraints": constraints, "reason": reason})


def revision_response(text="revised H"):
    return json.dumps({"hypothesis": text})


# --------------------------------------------------------------------------
# constraint parsing
# --------------------------------------------------------------------------


def test_parse_constraints_handles_prose_and_reasoning_spans():
    resp = 'thinking...</think>\nHere you go:\n{"constraints": {"prime_type": "odd"}, "reason": "r"}'
    constraints, reason = parse_constraints(resp)
    assert constraints == {"prime_type": "odd"}
    assert reason == "r"


def test_parse_constraints_supports_value_lists():
    resp = constraints_response({"difference_valuation": ["1", "2plus"]})
    constraints, _ = parse_constraints(resp)
    assert constraints == {"difference_valuation": ["1", "2plus"]}


@pytest.mark.parametrize(
    "resp", ["not json at all", '{"constraints": {}}', '{"reason": "no constraints"}']
)
def test_parse_constraints_rejects_unusable_responses(resp):
    constraints, _ = parse_constraints(resp)
    assert constraints is None


# --------------------------------------------------------------------------
# the Active loop
# --------------------------------------------------------------------------


def test_valid_request_produces_a_conforming_batch_with_oracle_outcomes():
    fam = get_family("lte_valuation")
    model = ScriptedModel([
        constraints_response({"prime_type": "odd", "n_parity": "even"}),
        revision_response("H1"),
    ])
    result = run_active(model, fam, "S", "H0", "medium", rounds=1, batch_size=3,
                        max_new_tokens=MNT, master_seed=1, exclude_keys=set())
    assert result.n_unsatisfiable == 0
    assert result.n_query_generations == 1
    assert result.final_hypothesis == "H1"
    round0 = result.rounds[0]
    assert round0.constraints == {"prime_type": "odd", "n_parity": "even"}
    assert len(round0.observations) == 3
    for obs in round0.observations:
        assert obs.outcome in ("SUCCESS", "FAILURE")
        assert obs.shown_features == {}


def test_unsatisfiable_request_triggers_one_reformulation_and_then_succeeds():
    fam = get_family("order_minus_one")
    model = ScriptedModel([
        constraints_response({"not_a_feature": "whatever"}),   # invalid
        constraints_response({"base_coprime": "yes"}),          # reformulated
        revision_response("H1"),
    ])
    result = run_active(model, fam, "S", "H0", "medium", rounds=1, batch_size=2,
                        max_new_tokens=MNT, master_seed=2, exclude_keys=set())
    assert result.n_unsatisfiable == 1
    assert result.n_query_generations == 2
    assert result.rounds[0].constraints == {"base_coprime": "yes"}
    assert len(result.rounds[0].observations) == 2
    # the model must have been shown a literal UNSATISFIABLE_REQUEST message
    retry_prompt = model.calls[1]["user"]
    assert retry_prompt.startswith("UNSATISFIABLE_REQUEST")
    assert "unknown feature name" in retry_prompt
    for feature in fam.query_schema():
        assert feature in retry_prompt


def test_two_failed_requests_fall_back_to_the_passive_distribution_and_log_it():
    fam = get_family("order_minus_one")
    model = ScriptedModel([
        constraints_response({"number_of_factors": "3"}),  # outside 'easy'
        constraints_response({"still": "wrong"}),           # invalid again
        revision_response("H1"),
    ])
    result = run_active(model, fam, "S", "H0", "easy", rounds=1, batch_size=2,
                        max_new_tokens=MNT, master_seed=3, exclude_keys=set())
    assert result.n_unsatisfiable == 2
    assert result.rounds[0].constraints is None      # fallback is recorded as such
    assert len(result.rounds[0].observations) == 2   # the round still happened
    assert result.notes["fallback_policy"] == "random"
    assert result.notes["unsat_rate"] == 1.0


def test_out_of_tier_request_reports_the_tier_in_the_reason():
    fam = get_family("order_minus_one")
    model = ScriptedModel([
        constraints_response({"number_of_factors": "3"}),
        constraints_response({"base_coprime": "yes"}),
        revision_response("H1"),
    ])
    run_active(model, fam, "S", "H0", "easy", rounds=1, batch_size=2,
               max_new_tokens=MNT, master_seed=4, exclude_keys=set())
    assert "difficulty 'easy'" in model.calls[1]["user"]


def test_unparseable_revision_keeps_the_previous_hypothesis_and_flags_it():
    fam = get_family("lte_valuation")
    model = ScriptedModel([
        constraints_response({"prime_type": "odd"}),
        "I have no idea",  # unparseable revision
    ])
    result = run_active(model, fam, "S", "H0-original", "medium", rounds=1,
                        batch_size=2, max_new_tokens=MNT, master_seed=5,
                        exclude_keys=set())
    assert result.final_hypothesis == "H0-original"
    rev = result.rounds[0].generations[-1]
    assert rev.meta.get("revision_parse_failed") is True


def test_adaptation_never_draws_an_excluded_instance():
    fam = get_family("recurrence_substitution")
    frozen = fam.generate_iid_test(random.Random(9), 20, "medium")
    excluded = {p.content_key() for p in frozen}
    model = ScriptedModel([
        constraints_response({"horizon_size": "small"}),
        revision_response("H1"),
    ] * 3)
    result = run_active(model, fam, "S", "H0", "medium", rounds=3, batch_size=3,
                        max_new_tokens=MNT, master_seed=6, exclude_keys=excluded)
    seen = []
    for r in result.rounds:
        seen.extend(o.problem_id for o in r.observations)
    assert len(seen) == len(set(seen)), "adaptation repeated a problem"
    assert result.n_observations == 9


def test_active_output_token_accounting_is_the_sum_of_its_generations():
    fam = get_family("lte_valuation")
    model = ScriptedModel(
        [constraints_response({"prime_type": "odd"}), revision_response()] * 2,
        tokens_per_call=17,
    )
    result = run_active(model, fam, "S", "H0", "medium", rounds=2, batch_size=2,
                        max_new_tokens=MNT, master_seed=7, exclude_keys=set())
    # 2 rounds x (1 query + 1 revision) x 17 tokens
    assert result.adaptation_output_tokens == 4 * 17
    assert result.n_revisions == 2


# --------------------------------------------------------------------------
# Passive and compute matching
# --------------------------------------------------------------------------


def test_passive_meets_the_budget_with_minimal_overshoot():
    fam = get_family("lte_valuation")
    model = ScriptedModel([revision_response()] * 50, tokens_per_call=10)
    result = run_passive(model, fam, "S", "H0", "medium", batch_size=2,
                         target_output_tokens=45, max_new_tokens=MNT,
                         master_seed=8, exclude_keys=set())
    assert result.adaptation_output_tokens >= 45
    # one fewer round would have fallen short, so the overshoot is minimal
    assert result.adaptation_output_tokens - 10 < 45
    assert result.notes["budget_reached"] is True
    assert result.notes["budget_cap_binding"] is False
    assert result.n_query_generations == 0
    assert result.n_unsatisfiable == 0


def test_passive_reports_the_cap_binding_instead_of_pretending_to_match():
    fam = get_family("lte_valuation")
    model = ScriptedModel([revision_response()] * 10, tokens_per_call=1)
    result = run_passive(model, fam, "S", "H0", "medium", batch_size=2,
                         target_output_tokens=10_000, max_new_tokens=MNT,
                         master_seed=9, exclude_keys=set(), max_rounds=3)
    assert result.adaptation_output_tokens < 10_000
    assert result.notes["budget_cap_binding"] is True
    assert result.notes["relative_mismatch"] < 0


def test_passive_uses_the_same_revision_prompt_as_active():
    fam = get_family("lte_valuation")
    active_model = ScriptedModel(
        [constraints_response({"prime_type": "odd"}), revision_response()]
    )
    run_active(active_model, fam, "S", "H0", "medium", rounds=1, batch_size=2,
               max_new_tokens=MNT, master_seed=10, exclude_keys=set())
    passive_model = ScriptedModel([revision_response()])
    run_passive(passive_model, fam, "S", "H0", "medium", batch_size=2,
                target_output_tokens=1, max_new_tokens=MNT, master_seed=10,
                exclude_keys=set())
    active_revise = active_model.calls[-1]
    passive_revise = passive_model.calls[-1]
    assert active_revise["system"] == passive_revise["system"]
    # same scaffolding, different observed problems
    assert "Revise your rule" in passive_revise["user"]
    assert passive_revise["user"].startswith(active_revise["user"][:40])


def test_passive_excludes_frozen_instances():
    fam = get_family("order_minus_one")
    frozen = fam.generate_iid_test(random.Random(11), 20, "medium")
    excluded = {p.content_key() for p in frozen}
    model = ScriptedModel([revision_response()] * 20, tokens_per_call=10)
    result = run_passive(model, fam, "S", "H0", "medium", batch_size=3,
                         target_output_tokens=45, max_new_tokens=MNT,
                         master_seed=12, exclude_keys=excluded)
    ids = [o.problem_id for r in result.rounds for o in r.observations]
    assert len(ids) == len(set(ids))


def test_oracle_features_are_invisible_and_unrequestable_in_the_active_loop():
    """Revision memo S.4: asking for an oracle feature is an unknown-name error."""
    fam = get_family("recurrence_substitution")
    model = ScriptedModel([
        constraints_response({"transformed_dynamics": "non_affine"}),  # oracle-only
        constraints_response({"horizon_size": "small"}),
        revision_response("H1"),
    ])
    result = run_active(model, fam, "S", "H0", "medium", rounds=1, batch_size=2,
                        max_new_tokens=MNT, master_seed=13, exclude_keys=set())
    assert result.n_unsatisfiable == 1
    assert "unknown feature name" in model.calls[1]["user"]
    # the schema shown in the FIRST prompt never mentioned it
    for feature in fam.oracle_feature_schema:
        assert feature not in model.calls[0]["user"]
    assert result.rounds[0].constraints == {"horizon_size": "small"}


def test_active_can_steer_the_task_form():
    fam = get_family("lte_valuation")
    model = ScriptedModel([
        constraints_response({"task_form": "exponent_in_factorization"}),
        revision_response("H1"),
    ])
    result = run_active(model, fam, "S", "H0", "medium", rounds=1, batch_size=3,
                        max_new_tokens=MNT, master_seed=14, exclude_keys=set())
    assert result.rounds[0].constraints == {"task_form": "exponent_in_factorization"}
    assert result.rounds[0].observations
    for obs in result.rounds[0].observations:
        assert "prime factorization of" in obs.text
