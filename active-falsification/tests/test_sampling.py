"""Sampling, constraint handling and split-disjointness checks (spec S.12, S.15)."""

import random

import pytest

from families import all_families, get_family
from families.base import UnsatisfiableConstraints
from sampling import assert_disjoint, derive_seed, label_balance, stream


def test_derived_streams_are_deterministic_and_independent():
    a1 = [stream(7, "x").random() for _ in range(5)]
    a2 = [stream(7, "x").random() for _ in range(5)]
    b = [stream(7, "y").random() for _ in range(5)]
    assert a1 == a2
    assert a1 != b
    assert derive_seed(1, "a") != derive_seed(2, "a")
    assert derive_seed(1, "a") != derive_seed(1, "b")


def test_generation_is_reproducible_from_the_same_seed():
    for name, fam in all_families().items():
        first = fam.sample_random(random.Random(42), "medium", fam.base_templates[0])
        second = fam.sample_random(random.Random(42), "medium", fam.base_templates[0])
        assert first.text == second.text
        assert first.exact_answer == second.exact_answer
        assert first.strategy_applies == second.strategy_applies


def test_unknown_feature_names_and_values_are_rejected():
    for name, fam in all_families().items():
        rng = random.Random(0)
        with pytest.raises(UnsatisfiableConstraints) as exc:
            fam.sample_conditioned(rng, {"not_a_feature": "x"}, "medium",
                                   fam.base_templates[0])
        assert "unknown feature" in str(exc.value)
        feature = list(fam.query_schema())[0]
        with pytest.raises(UnsatisfiableConstraints) as exc:
            fam.sample_conditioned(rng, {feature: "not_a_value"}, "medium",
                                   fam.base_templates[0])
        assert "not allowed" in str(exc.value)


def test_oracle_feature_names_are_rejected_like_unknown_names():
    """Revision memo S.4: the model must not learn that oracle features exist."""
    for name, fam in all_families().items():
        for key in fam.oracle_feature_schema:
            value = fam.oracle_feature_schema[key][0]
            with pytest.raises(UnsatisfiableConstraints) as exc:
                fam.sample_conditioned(
                    random.Random(0), {key: value}, "medium", fam.base_templates[0]
                )
            assert "unknown feature" in str(exc.value), (name, key)


def test_task_form_constraint_switches_the_rendered_template():
    for name, fam in all_families().items():
        rng = random.Random(1)
        for template in fam.base_templates:
            p = fam.sample_conditioned(
                rng, {"task_form": template}, "medium", fam.base_templates[0]
            )
            assert p is not None
            assert p.template == template
            assert p.query_features["task_form"] == template


def test_challenge_templates_cannot_be_requested_by_active():
    for name, fam in all_families().items():
        for challenge in fam.challenge_templates:
            with pytest.raises(UnsatisfiableConstraints):
                fam.sample_conditioned(
                    random.Random(2), {"task_form": challenge}, "medium",
                    fam.base_templates[0],
                )


def test_more_than_three_constraints_is_rejected():
    fam = get_family("lte_valuation")
    constraints = {
        "prime_type": "odd",
        "n_parity": "even",
        "p_divides_difference": "yes",
        "exponent_size": "small",
    }
    with pytest.raises(UnsatisfiableConstraints) as exc:
        fam.sample_conditioned(random.Random(0), constraints, "medium", "valuation")
    assert "at most 3" in str(exc.value)


def test_empty_constraints_are_rejected():
    fam = get_family("order_minus_one")
    with pytest.raises(UnsatisfiableConstraints):
        fam.sample_conditioned(random.Random(0), {}, "medium", "least_n_congruence")


def test_contradictory_constraints_raise_with_an_explanation():
    fam = get_family("order_minus_one")
    with pytest.raises(UnsatisfiableConstraints) as exc:
        fam.sample_conditioned(
            random.Random(0),
            {"modulus_type": "prime", "number_of_factors": "2"},
            "medium",
            "least_n_congruence",
        )
    assert "contradicts" in str(exc.value)


def test_out_of_tier_constraints_raise():
    fam = get_family("order_minus_one")
    with pytest.raises(UnsatisfiableConstraints) as exc:
        fam.sample_conditioned(
            random.Random(0), {"number_of_factors": "3"}, "easy",
            "least_n_congruence",
        )
    assert "difficulty" in str(exc.value)


def test_satisfiable_constraints_are_honoured_exactly():
    checks = {
        "order_minus_one": ({"base_coprime": "yes"}, "least_n_congruence"),
        "lte_valuation": ({"prime_type": "odd", "n_parity": "even"}, "valuation"),
        "recurrence_substitution": (
            {"numerator_degree": "linear", "horizon_size": "small"}, "compute_term"
        ),
    }
    for name, (constraints, template) in checks.items():
        fam = get_family(name)
        rng = random.Random(1)
        for _ in range(6):
            p = fam.sample_conditioned(rng, constraints, "medium", template)
            assert p is not None, (name, constraints)
            fam.validate_problem(p)
            for key, value in constraints.items():
                assert str(p.query_features[key]) == value


def test_subset_constraints_are_supported():
    fam = get_family("lte_valuation")
    rng = random.Random(2)
    p = fam.sample_conditioned(
        rng, {"exponent_size": ["small", "medium"]}, "medium", "valuation"
    )
    assert p is not None
    assert p.query_features["exponent_size"] in ("small", "medium")


def test_splits_are_disjoint_and_balanced():
    for name, fam in all_families().items():
        seeds = fam.generate_seed_candidates(random.Random(3), 4, "medium")
        used = {p.content_key() for p in seeds}
        iid = fam.generate_iid_test(random.Random(4), 12, "medium", exclude=used)
        used |= {p.content_key() for p in iid}
        challenge = fam.generate_challenge_test(
            random.Random(5), 8, "medium", exclude=used
        )
        assert_disjoint({"seeds": seeds, "iid": iid, "challenge": challenge})
        assert label_balance(iid) == {"n": 12, "positive": 6, "negative": 6}
        assert label_balance(challenge) == {"n": 8, "positive": 4, "negative": 4}
        assert all(p.template in fam.challenge_templates for p in challenge)
        assert all(p.template in fam.base_templates for p in iid)


def test_assert_disjoint_detects_overlap():
    fam = get_family("order_minus_one")
    items = fam.generate_iid_test(random.Random(6), 6, "medium")
    with pytest.raises(ValueError) as exc:
        assert_disjoint({"a": items, "b": items[:2]})
    assert "leakage" in str(exc.value)


def test_query_and_oracle_namespaces_are_disjoint():
    """Revision memo S.4: two namespaces, never overlapping."""
    for name, fam in all_families().items():
        assert not (set(fam.queryable_features) & set(fam.oracle_feature_schema))
        rng = random.Random(3)
        p = fam.sample_random(rng, "medium", fam.base_templates[0])
        assert not (set(p.query_features) & set(p.oracle_features))
        assert set(p.oracle_features) == set(fam.oracle_feature_schema)


def test_every_problem_carries_an_applicability_reason():
    for name, fam in all_families().items():
        rng = random.Random(4)
        for want in (True, False):
            p = fam.sample_random(rng, "medium", fam.base_templates[0],
                                  want_applies=want)
            assert p.applicability_reason.strip()


def test_seed_candidates_are_all_positive_and_carry_solutions():
    for name, fam in all_families().items():
        seeds = fam.generate_seed_candidates(random.Random(7), 6, "medium")
        assert len(seeds) == 6
        assert all(p.strategy_applies for p in seeds)
        assert all(p.human_solution.strip() for p in seeds)
        assert len({p.content_key() for p in seeds}) == 6


def test_validate_problem_rejects_a_tampered_label():
    fam = get_family("order_minus_one")
    p = fam.sample_random(random.Random(8), "medium", "least_n_congruence",
                          want_applies=True)
    p.strategy_applies = False
    with pytest.raises(ValueError) as exc:
        fam.validate_problem(p)
    assert "oracle mismatch" in str(exc.value)


def test_validate_problem_rejects_a_tampered_answer():
    fam = get_family("lte_valuation")
    p = fam.sample_random(random.Random(9), "medium", "valuation")
    p.exact_answer = str(int(p.exact_answer) + 1)
    with pytest.raises(ValueError) as exc:
        fam.validate_problem(p)
    assert "answer mismatch" in str(exc.value)


def test_validate_problem_rejects_an_oracle_feature_in_the_query_namespace():
    fam = get_family("recurrence_substitution")
    p = fam.sample_random(random.Random(10), "medium", "compute_term")
    p.query_features["transformed_dynamics"] = "affine"
    with pytest.raises(ValueError) as exc:
        fam.validate_problem(p)
    assert "not in schema" in str(exc.value)
