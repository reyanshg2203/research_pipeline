"""Exact-grading checks (spec S.17, S.23)."""

import pytest

from grading import (
    canonical_gold,
    extract_answer_span,
    grade,
    normalise_answer,
    parse_boundary_label,
)


@pytest.mark.parametrize(
    "response,gold,expected",
    [
        ("reasoning\nFINAL_ANSWER: 12", "12", True),
        ("FINAL_ANSWER: 13", "12", False),
        ("FINAL_ANSWER: NONE", "NONE", True),
        ("FINAL_ANSWER: none", "NONE", True),
        ("FINAL_ANSWER: 12", "NONE", False),
        ("FINAL_ANSWER: YES", "YES", True),
        ("FINAL_ANSWER: no", "NO", True),
        ("blah \\boxed{7/5}", "7/5", True),
        ("blah \\boxed{14/10}", "7/5", True),
        ("FINAL_ANSWER: \\frac{-3}{6}", "-1/2", True),
        ("FINAL_ANSWER: $-\\dfrac{7}{2}$", "-7/2", True),
        ("FINAL_ANSWER: -7/2.", "-7/2", True),
        ("FINAL_ANSWER: 1,234", "1234", True),
        ("FINAL_ANSWER: 0", "0", True),
    ],
)
def test_grading_exactness(response, gold, expected):
    result = grade(response, gold)
    assert not result.parse_failed
    assert result.correct is expected


@pytest.mark.parametrize(
    "response",
    ["no answer here", "FINAL_ANSWER: the answer is five", "FINAL_ANSWER:", ""],
)
def test_parse_failures_are_reported_not_scored(response):
    result = grade(response, "12")
    assert result.parse_failed is True
    assert result.correct is False
    assert result.parsed is None


def test_final_answer_marker_wins_over_boxed():
    assert extract_answer_span("\\boxed{9}\nFINAL_ANSWER: 12") == "12"


def test_last_final_answer_wins():
    assert extract_answer_span("FINAL_ANSWER: 1\nmore\nFINAL_ANSWER: 2") == "2"


def test_rational_equivalence_is_exact_not_approximate():
    assert normalise_answer("6/4") == "3/2"
    assert normalise_answer("-6/4") == "-3/2"
    assert normalise_answer("4/2") == "2"
    assert normalise_answer("1/0") is None
    assert normalise_answer("0.5") is None  # decimals are never accepted


def test_canonical_gold_rejects_ungradable_gold():
    with pytest.raises(ValueError):
        canonical_gold("approximately 3")


@pytest.mark.parametrize(
    "response,expected",
    [
        ("APPLIES", True),
        ("DOES_NOT_APPLY", False),
        ("does not apply", False),
        ("I believe it APPLIES", True),
        ("First APPLIES, on reflection DOES_NOT_APPLY", False),
        ("nothing relevant", None),
        ("", None),
    ],
)
def test_boundary_label_parsing(response, expected):
    assert parse_boundary_label(response) is expected


def test_every_family_answer_is_gradable():
    import random

    from families import all_families

    for name, fam in all_families().items():
        rng = random.Random(0)
        for template in fam.base_templates + fam.challenge_templates:
            for want in (True, False):
                p = fam.sample_random(rng, "medium", template, want_applies=want)
                assert canonical_gold(p.exact_answer)
                assert grade(f"FINAL_ANSWER: {p.exact_answer}", p.exact_answer).correct
