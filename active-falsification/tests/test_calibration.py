"""Stage-1 calibration checks (calibration spec S.21).

Covers: the shared problem bank, mathematical validation before inference,
zero-shot prompt leakage, reproducibility, grading, the predeclared selection
rule (including NO_VIABLE_TIER and ties), diagnostics, and a mock pipeline run
that asserts no Stage-2 module is ever imported.
"""

import json
import os
import subprocess
import sys
import zlib

import pytest

import prompts as P
from calibration import (
    NO_VIABLE_TIER,
    PREFERRED_RANGE,
    TARGET_POINT,
    TIE_NEEDS_REVIEW,
    build_problem_bank,
    calibration_report,
    diagnostics,
    pooled_by_difficulty,
    run_zero_shot_calibration,
    select_difficulty,
    solve_once,
    summarise_by_cell,
)
from families import all_families, get_family
from models import MODEL_REGISTRY, load_model, resolve_substitutions

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))

STAGE_2_MODULES = [
    "active", "passive", "evaluation", "seed_induction", "seed_screening",
    "runner", "ood", "metrics",
]


# --------------------------------------------------------------------------
# the shared problem bank
# --------------------------------------------------------------------------


def test_bank_is_identical_for_every_model_and_reproducible_from_the_seed():
    """Calibration spec S.4: one bank, generated once, shared by all models."""
    families = all_families()
    first = build_problem_bank(families, 4, 20260901)["bank"]
    second = build_problem_bank(families, 4, 20260901)["bank"]
    for name in families:
        for difficulty in ("easy", "medium", "hard"):
            a = first[name][difficulty]
            b = second[name][difficulty]
            assert [p.id for p in a] == [p.id for p in b]
            assert [p.text for p in a] == [p.text for p in b]
            assert [p.exact_answer for p in a] == [p.exact_answer for p in b]


def test_a_different_master_seed_gives_a_different_bank():
    families = all_families()
    a = build_problem_bank(families, 4, 20260901)["bank"]
    b = build_problem_bank(families, 4, 12345)["bank"]
    ids_a = [p.id for f in a.values() for t in f.values() for p in t]
    ids_b = [p.id for f in b.values() for t in f.values() for p in t]
    assert ids_a != ids_b


def test_every_banked_problem_is_independently_validated():
    """Calibration spec S.3: validated by the family oracle BEFORE inference."""
    families = all_families()
    built = build_problem_bank(families, 6, 20260901)
    assert built["validation_failures"] == []
    for name, family in families.items():
        for difficulty, problems in built["bank"][name].items():
            assert len(problems) == 6
            for p in problems:
                assert family.validate_problem(p)
                assert family.recompute_answer(p) == p.exact_answer
                assert family.recompute_strategy_applies(p) is p.strategy_applies
                assert p.difficulty == difficulty


def test_bank_covers_all_three_tiers():
    families = all_families()
    bank = build_problem_bank(families, 10, 20260901)["bank"]
    for name in families:
        assert set(bank[name]) == {"easy", "medium", "hard"}
        for difficulty, problems in bank[name].items():
            assert len(problems) == 10
            assert all(p.difficulty == difficulty for p in problems)


def test_stage_1_never_reads_or_records_the_applicability_label():
    """Stage 1 uses only the public problem and the exact answer."""
    source = open(os.path.join(ROOT, "src", "calibration.py"), encoding="utf-8").read()
    code = "\n".join(
        line for line in source.splitlines()
        if not line.lstrip().startswith("#")
    )
    # the only mentions left are inside docstrings explaining the exclusion
    assert "p.strategy_applies" not in code
    assert "problem.strategy_applies" not in code
    assert "want_applies=None" in code
    assert "want_applies=wants" not in code

    runner_source = open(
        os.path.join(ROOT, "scripts", "run_calibration.py"), encoding="utf-8"
    ).read()
    assert "strategy_applies" not in runner_source

    fam = get_family("lte_valuation")
    bank = build_problem_bank({"lte_valuation": fam}, 2, 20260901)["bank"]
    model = load_model("mock", {"precision": "none"})
    rows = run_zero_shot_calibration(
        model, {"lte_valuation": fam}, bank, 128, 20260901, progress=False
    )
    for row in rows:
        assert "strategy_applies" not in row

    from calibration import bank_public_records

    for record in bank_public_records(bank):
        assert "strategy_applies" not in record


def test_bank_problems_are_unique_within_a_tier():
    families = all_families()
    bank = build_problem_bank(families, 8, 20260901)["bank"]
    for name in families:
        for difficulty, problems in bank[name].items():
            assert len({p.content_key() for p in problems}) == len(problems)


# --------------------------------------------------------------------------
# the zero-shot prompt
# --------------------------------------------------------------------------


def test_zero_shot_prompt_is_solver_instruction_plus_problem_text_only():
    """Calibration spec S.5: no examples, no strategy, no features, no labels."""
    for name, fam in all_families().items():
        bank = build_problem_bank({name: fam}, 2, 20260901)["bank"]
        for difficulty, problems in bank[name].items():
            for p in problems:
                prompt = P.solve_prompt(p)
                assert prompt["user"] == p.text
                blob = prompt["system"] + prompt["user"]
                for token in ("strategy_applies", "latent_parameters",
                              "oracle_features", "applicability_reason",
                              "APPLIES", "DOES_NOT_APPLY", "SUCCESS", "FAILURE",
                              "hypothesis", "difficulty", "easy", "medium", "hard"):
                    assert token not in blob, (name, token)
                assert fam.strategy_description not in blob
                assert p.applicability_reason not in blob
                assert p.human_solution == "" or p.human_solution not in blob
                for feature in fam.oracle_feature_schema:
                    assert feature not in blob
                for feature in fam.queryable_features:
                    assert feature not in blob


def test_zero_shot_prompt_carries_no_worked_example_or_seed_information():
    system = P.SOLVE_SYSTEM
    assert "Example" not in system
    assert "For example" not in system
    assert "seed" not in system.lower()
    assert "FINAL_ANSWER" in system
    assert "NONE" in system


# --------------------------------------------------------------------------
# grading
# --------------------------------------------------------------------------


@pytest.mark.parametrize(
    "response,gold,expect_correct,expect_unparsed",
    [
        ("work\nFINAL_ANSWER: 12", "12", True, False),
        ("work\nFINAL_ANSWER: 13", "12", False, False),
        ("FINAL_ANSWER: NONE", "NONE", True, False),
        ("FINAL_ANSWER: 5", "NONE", False, False),
        ("FINAL_ANSWER: -7/2", "-7/2", True, False),
        ("FINAL_ANSWER: 14/10", "7/5", True, False),
        ("FINAL_ANSWER: YES", "YES", True, False),
        ("FINAL_ANSWER: NO", "NO", True, False),
        ("no final answer line", "12", False, True),
        ("FINAL_ANSWER: about seven", "7", False, True),
        ("FINAL_ANSWER: 0.5", "1/2", False, True),
    ],
)
def test_calibration_grading_paths(response, gold, expect_correct, expect_unparsed):
    from grading import grade

    result = grade(response, gold)
    assert result.correct is expect_correct
    assert result.parse_failed is expect_unparsed


def test_every_banked_gold_answer_is_gradable():
    from grading import canonical_gold, grade

    families = all_families()
    bank = build_problem_bank(families, 4, 20260901)["bank"]
    for name in families:
        for problems in bank[name].values():
            for p in problems:
                assert canonical_gold(p.exact_answer)
                assert grade(f"FINAL_ANSWER: {p.exact_answer}", p.exact_answer).correct


# --------------------------------------------------------------------------
# one attempt per problem, and the recorded row
# --------------------------------------------------------------------------


def test_one_attempt_per_problem_and_full_row_is_recorded():
    """Calibration spec S.7 and S.16."""
    fam = get_family("lte_valuation")
    bank = build_problem_bank({"lte_valuation": fam}, 2, 20260901)["bank"]
    model = load_model("mock", {"precision": "none"})
    rows = run_zero_shot_calibration(
        model, {"lte_valuation": fam}, bank, 128, 20260901, progress=False
    )
    assert len(rows) == 6                      # 3 tiers x 2 problems
    assert len(model.generations) == 6         # exactly one call each
    required = {
        "model_alias", "model_id", "family", "difficulty", "problem_id",
        "problem_text", "gold_answer", "raw_response", "parsed_answer",
        "correct", "unparsed", "input_tokens", "output_tokens", "precision",
        "generation_seed",
    }
    for row in rows:
        assert required <= set(row)
        assert row["correct"] is row["model_answer_correct"]
        assert isinstance(row["raw_response"], str)


def test_unparsed_rows_are_scored_incorrect_but_reported_separately():
    rows = [
        {"model_alias": "m", "family": "f", "difficulty": "easy", "correct": True,
         "unparsed": False, "output_tokens": 10},
        {"model_alias": "m", "family": "f", "difficulty": "easy", "correct": False,
         "unparsed": True, "output_tokens": 10},
    ]
    cell = summarise_by_cell(rows)[0]
    assert cell["accuracy"] == 0.5              # unparsed counts as incorrect
    assert cell["accuracy_parsed_only"] == 1.0  # ... but is excluded here
    assert cell["unparsed"] == 1


# --------------------------------------------------------------------------
# the predeclared selection rule
# --------------------------------------------------------------------------


def _pooled(family, easy, medium, hard):
    out = []
    for difficulty, accuracy in (("easy", easy), ("medium", medium), ("hard", hard)):
        out.append({
            "family": family, "difficulty": difficulty, "n_total": 40,
            "accuracy_pooled": accuracy,
            "distance_from_target_0_45": abs(accuracy - TARGET_POINT),
            "within_preferred_range": PREFERRED_RANGE[0] <= accuracy <= PREFERRED_RANGE[1],
            "unparsed": 0, "parse_failure_rate": 0.0,
            "accuracy_parsed_only": accuracy, "mean_output_tokens": 100.0,
        })
    return out


def test_rule_picks_the_in_range_tier_closest_to_the_target():
    sel = select_difficulty(_pooled("f", 0.90, 0.47, 0.10), "f")
    assert sel["selected"] == "medium"
    assert sel["status"] == "OK"
    assert sel["pooled_accuracy"] == 0.47


def test_rule_prefers_in_range_over_merely_closest():
    """0.72 is closer to 0.45 than 0.25, but it is outside the preferred range."""
    sel = select_difficulty(_pooled("f", 0.95, 0.72, 0.25), "f")
    assert sel["selected"] == "hard"


def test_rule_reports_no_viable_tier_instead_of_silently_choosing():
    sel = select_difficulty(_pooled("f", 0.92, 0.88, 0.84), "f")
    assert sel["selected"] is None
    assert sel["status"] == NO_VIABLE_TIER
    assert sel["accuracies"] == {"easy": 0.92, "medium": 0.88, "hard": 0.84}

    sel = select_difficulty(_pooled("f", 0.05, 0.02, 0.00), "f")
    assert sel["selected"] is None
    assert sel["status"] == NO_VIABLE_TIER


def test_exact_tie_goes_to_human_review_by_default():
    sel = select_difficulty(_pooled("f", 0.95, 0.40, 0.50), "f")
    assert sel["selected"] is None
    assert sel["status"] == TIE_NEEDS_REVIEW
    assert sel["tied_tiers"] == ["medium", "hard"]


def test_boundary_values_are_inside_the_preferred_range():
    assert select_difficulty(_pooled("f", 0.20, 0.95, 0.99), "f")["selected"] == "easy"
    assert select_difficulty(_pooled("f", 0.95, 0.99, 0.70), "f")["selected"] == "hard"


def test_selection_rule_uses_only_zero_shot_accuracy():
    """The rule must be a pure function of the pooled zero-shot accuracies."""
    pooled = _pooled("f", 0.90, 0.47, 0.10)
    for row in pooled:
        row["h0_accuracy"] = 0.99
        row["active_accuracy"] = 0.10
        row["passive_accuracy"] = 0.99
    assert select_difficulty(pooled, "f")["selected"] == "medium"


# --------------------------------------------------------------------------
# diagnostics
# --------------------------------------------------------------------------


def test_diagnostics_flag_inversion_ceiling_floor_and_parse_failures():
    inverted = diagnostics(_pooled("f", 0.10, 0.60, 0.60), [], "f")
    assert any("inversion" in w for w in inverted)

    ceiling = diagnostics(_pooled("f", 0.95, 0.90, 0.88), [], "f")
    assert any("above" in w for w in ceiling)

    floor = diagnostics(_pooled("f", 0.05, 0.03, 0.01), [], "f")
    assert any("below" in w for w in floor)

    pooled = _pooled("f", 0.45, 0.45, 0.45)
    pooled[0]["parse_failure_rate"] = 0.4
    assert any("parse failures" in w for w in diagnostics(pooled, [], "f"))


def test_diagnostics_flag_a_model_at_ceiling_against_one_at_floor():
    per_cell = [
        {"model": "a", "family": "f", "difficulty": "easy", "accuracy": 0.95,
         "correct": 19, "n": 20},
        {"model": "b", "family": "f", "difficulty": "easy", "accuracy": 0.05,
         "correct": 1, "n": 20},
    ]
    warnings = diagnostics(_pooled("f", 0.50, 0.45, 0.40), per_cell, "f")
    assert any("ceiling" in w and "floor" in w for w in warnings)


def test_warnings_do_not_change_the_selection():
    pooled = _pooled("f", 0.10, 0.47, 0.60)   # inverted, but medium is still chosen
    assert diagnostics(pooled, [], "f")
    assert select_difficulty(pooled, "f")["selected"] == "medium"


# --------------------------------------------------------------------------
# models
# --------------------------------------------------------------------------


def test_every_required_model_alias_exists_with_an_explicit_thinking_mode():
    for alias in ("qwen3_8b", "deepseek_r1_llama_8b", "smollm3_3b", "llama32_3b",
                  "phi35_mini"):
        spec = MODEL_REGISTRY[alias]
        assert spec.thinking_mode in ("chat_template_flag", "native", "instruct")
        assert spec.model_id
    assert MODEL_REGISTRY["llama32_3b"].gated is True
    assert MODEL_REGISTRY["qwen3_8b"].thinking_mode == "chat_template_flag"
    assert MODEL_REGISTRY["smollm3_3b"].thinking_mode == "chat_template_flag"
    assert MODEL_REGISTRY["deepseek_r1_llama_8b"].thinking_mode == "native"
    assert MODEL_REGISTRY["llama32_3b"].thinking_mode == "instruct"


def test_deepseek_forces_its_reasoning_prefix_without_changing_the_instruction():
    """The model card's recommended start, with the same zero-shot contract."""
    spec = MODEL_REGISTRY["deepseek_r1_llama_8b"]
    assert spec.reasoning_prefix == "<think>\n"
    assert spec.merge_system_into_user is True
    assert spec.thinking_mode == "native"
    # the instruction and output convention are untouched
    assert "FINAL_ANSWER" in P.SOLVE_SYSTEM
    assert P.SOLVE_USER == "{problem_text}"
    # no other model forces a prefix
    for alias, other in MODEL_REGISTRY.items():
        if alias != "deepseek_r1_llama_8b":
            assert other.reasoning_prefix is None, alias


def test_reasoning_prefix_is_appended_to_the_prompt_not_the_output_budget():
    """The forced prefix belongs to the prompt, so it is not counted as output."""
    import models as models_module

    class _Tok:
        name_or_path = "stub"
        eos_token_id = 2
        pad_token_id = 2

        def apply_chat_template(self, messages, tokenize=False,
                                add_generation_prompt=True):
            assert len(messages) == 1 and messages[0]["role"] == "user"
            return messages[0]["content"] + "\n<assistant>\n"

    stub = models_module.HFModel.__new__(models_module.HFModel)
    stub.spec = MODEL_REGISTRY["deepseek_r1_llama_8b"]
    stub.tokenizer = _Tok()
    stub.reasoning_prefix = stub.spec.reasoning_prefix
    stub.chat_template_flag_accepted = None
    text = models_module.HFModel._apply_template(stub, "SYSTEM RULES", "PROBLEM TEXT")
    assert text.endswith("<think>\n")
    # system and user are merged into a single user turn, per the model card
    assert "SYSTEM RULES" in text and "PROBLEM TEXT" in text
    # applying it twice must not stack the prefix
    again = models_module.HFModel._apply_template(stub, "SYSTEM RULES", "PROBLEM TEXT")
    assert again.count("<think>") == 1


def test_truncation_is_recorded_on_every_generation():
    model = load_model("mock", {"precision": "none"})
    generous = model.generate("solve", "f", P.SOLVE_SYSTEM, "problem", 4096)
    assert generous.hit_max_new_tokens is False
    tiny = model.generate("solve", "f", P.SOLVE_SYSTEM, "problem", 2)
    assert tiny.hit_max_new_tokens is True
    assert tiny.output_tokens == 2


def test_calibration_rows_carry_the_truncation_field():
    fam = get_family("lte_valuation")
    bank = build_problem_bank({"lte_valuation": fam}, 2, 20260901)["bank"]
    model = load_model("mock", {"precision": "none"})
    rows = run_zero_shot_calibration(
        model, {"lte_valuation": fam}, bank, 128, 20260901, progress=False
    )
    for row in rows:
        assert "hit_max_new_tokens" in row
        assert isinstance(row["hit_max_new_tokens"], bool)
        assert row["max_new_tokens"] == 128


def test_summaries_report_truncation_counts():
    rows = [
        {"model_alias": "m", "family": "f", "difficulty": "easy", "correct": True,
         "unparsed": False, "output_tokens": 10, "hit_max_new_tokens": False},
        {"model_alias": "m", "family": "f", "difficulty": "easy", "correct": False,
         "unparsed": True, "output_tokens": 2048, "hit_max_new_tokens": True},
    ]
    cell = summarise_by_cell(rows)[0]
    assert cell["truncated"] == 1
    assert cell["truncation_rate"] == 0.5
    pooled = pooled_by_difficulty(rows)[0]
    assert pooled["truncated"] == 1
    assert pooled["truncation_rate"] == 0.5


def test_frequent_truncation_warns_without_changing_the_cap():
    from calibration import MAX_TRUNCATION_RATE

    pooled = _pooled("f", 0.90, 0.47, 0.10)
    pooled[1]["truncated"] = 20
    pooled[1]["truncation_rate"] = 0.5
    warnings = diagnostics(pooled, [], "f")
    assert any("hit the generation cap" in w for w in warnings)
    assert any("NOT been changed automatically" in w for w in warnings)
    # the warning must not move the selection
    assert select_difficulty(pooled, "f")["selected"] == "medium"

    quiet = _pooled("f", 0.90, 0.47, 0.10)
    for row in quiet:
        row["truncated"] = 0
        row["truncation_rate"] = 0.0
    assert not any("generation cap" in w for w in diagnostics(quiet, [], "f"))
    assert MAX_TRUNCATION_RATE == 0.10


def test_four_bit_compute_dtype_follows_gpu_bf16_support():
    """Change 3: BF16 compute dtype only where the GPU supports BF16."""
    source = open(os.path.join(ROOT, "src", "models.py"), encoding="utf-8").read()
    assert "compute_dtype = torch.bfloat16 if supports_bf16 else torch.float16" in source
    assert "bnb_4bit_compute_dtype=compute_dtype" in source
    assert "bnb_4bit_quant_type=\"nf4\"" in source


def test_resolved_inference_configuration_is_recorded():
    """Change 2: the manifest must describe what actually loaded."""
    source = open(os.path.join(ROOT, "src", "models.py"), encoding="utf-8").read()
    for field in ("parameter_dtypes", "dominant_parameter_dtype", "device_map",
                  "cpu_offload", "disk_offload", "gpu_name",
                  "gpu_total_vram_gib", "bf16_supported_by_gpu",
                  "requested_precision", "compute_dtype"):
        assert f'"{field}"' in source, field
    assert "resolved_inference" in source
    assert "_resolve_placement" in source


def test_four_bit_runs_are_marked_smoke_only():
    source = open(os.path.join(ROOT, "src", "models.py"), encoding="utf-8").read()
    assert "SMOKE / PILOT setting" in source
    smoke = open(os.path.join(ROOT, "configs", "calibration_smoke.yaml"),
                 encoding="utf-8").read()
    assert "precision: 4bit" in smoke
    assert "must NOT be used to select a difficulty tier" in smoke


def test_substitution_must_be_explicit():
    assert resolve_substitutions(["llama32_3b"], {}) == ["llama32_3b"]
    assert resolve_substitutions(["llama32_3b"], {"llama32_3b": "phi35_mini"}) == [
        "phi35_mini"
    ]
    with pytest.raises(KeyError):
        resolve_substitutions(["llama32_3b"], {"llama32_3b": "not_a_model"})


# --------------------------------------------------------------------------
# the runner is Stage-1 only
# --------------------------------------------------------------------------


def test_run_calibration_does_not_import_any_stage_2_module():
    """Calibration spec S.23: the runner must not import or call Active/Passive."""
    script = (
        "import sys, os; "
        f"sys.path.insert(0, {os.path.join(ROOT, 'scripts')!r}); "
        f"sys.path.insert(0, {os.path.join(ROOT, 'src')!r}); "
        "import run_calibration; "
        f"print(json.dumps([m for m in {STAGE_2_MODULES!r} if m in sys.modules]))"
    )
    out = subprocess.check_output(
        [sys.executable, "-c", "import json;" + script], cwd=ROOT
    ).decode().strip()
    assert json.loads(out) == [], f"Stage-2 modules imported: {out}"


def test_calibration_module_does_not_import_stage_2():
    source = open(os.path.join(ROOT, "src", "calibration.py"), encoding="utf-8").read()
    for module in ("active", "passive", "evaluation", "seed_induction",
                   "seed_screening", "runner", "ood"):
        assert f"import {module}" not in source
        assert f"from {module}" not in source


def test_mock_calibration_run_produces_only_stage_1_artifacts(tmp_path):
    """Calibration spec S.15 and S.21: full pipeline, no Stage-2 files."""
    out = subprocess.run(
        [sys.executable, os.path.join(ROOT, "scripts", "run_calibration.py"),
         "--config", os.path.join(ROOT, "configs", "calibration_mock.yaml"),
         "--skip-self-test", "--outputs", str(tmp_path), "--run-id", "t"],
        cwd=ROOT, capture_output=True, text=True,
    )
    # A completed calibration exits 0 even when a family has no viable tier:
    # that is a recorded result, not a software failure.
    assert out.returncode == 0, out.stderr
    run_dir = tmp_path / "t"
    produced = sorted(os.listdir(run_dir))
    expected = {
        "run_manifest.json", "config.yaml", "calibration_problem_bank.json",
        "calibration_problem_bank_researcher.json", "calibration_runs.jsonl",
        "calibration_summary.csv", "pooled_difficulty_summary.csv",
        "selected_difficulties.json", "calibration_report.md", "errors.log",
    }
    assert set(produced) == expected, produced
    for banned in ("seeds", "induction", "active_trace", "passive_trace",
                   "hidden_", "evaluation_raw", "main_table", "h0_"):
        assert not any(banned in f for f in produced), (banned, produced)

    manifest = json.loads((run_dir / "run_manifest.json").read_text())
    assert manifest["stage"] == "1_zero_shot_calibration_only"
    assert manifest["attempts_per_problem"] == 1
    assert manifest["zero_shot_prompt"]["system"] == P.SOLVE_SYSTEM
    assert "active_adaptation" in manifest["not_run"]

    bank = json.loads((run_dir / "calibration_problem_bank.json").read_text())
    assert len(bank["problems"]) == 3 * 3 * 4
    for record in bank["problems"]:
        assert set(record) == {
            "problem_id", "family", "difficulty", "template", "problem_text",
            "exact_answer", "generation_seed",
        }

    report = (run_dir / "calibration_report.md").read_text()
    for banned in ("Active", "Passive", "H0", "hypothesis", "boundary accuracy"):
        assert banned not in report, banned


def test_no_viable_tier_still_exits_zero(tmp_path):
    """A completed calibration is a success even when it selects nothing."""
    out = subprocess.run(
        [sys.executable, os.path.join(ROOT, "scripts", "run_calibration.py"),
         "--config", os.path.join(ROOT, "configs", "calibration_mock.yaml"),
         "--skip-self-test", "--outputs", str(tmp_path), "--run-id", "nv"],
        cwd=ROOT, capture_output=True, text=True,
    )
    assert out.returncode == 0, out.stderr
    selections = json.loads(
        (tmp_path / "nv" / "selected_difficulties.json").read_text()
    )
    statuses = {
        k: v.get("status") for k, v in selections.items() if not k.startswith("_")
    }
    # the mock model answers at random, so at least one family resolves to
    # NO_VIABLE_TIER -- and that must be recorded, not signalled by an exit code
    assert any(s in (NO_VIABLE_TIER, TIE_NEEDS_REVIEW) for s in statuses.values()), \
        statuses
    report = (tmp_path / "nv" / "calibration_report.md").read_text()
    assert NO_VIABLE_TIER in report or TIE_NEEDS_REVIEW in report


def test_calibration_config_rejects_stage_2_settings(tmp_path):
    from run_calibration import ConfigError, load_config

    path = tmp_path / "bad.yaml"
    path.write_text(
        "models: [mock]\nfamilies: [lte_valuation]\nactive_rounds: 3\n"
    )
    with pytest.raises(ConfigError) as exc:
        load_config(str(path))
    assert "Stage-2" in str(exc.value)
    assert "active_rounds" in str(exc.value)


def test_calibration_config_rejects_any_unknown_key(tmp_path):
    """Strict allowlist: an unrecognised key is an error, not a warning."""
    from run_calibration import ALLOWED_CONFIG_KEYS, ConfigError, load_config

    path = tmp_path / "typo.yaml"
    path.write_text(
        "models: [mock]\nfamilies: [lte_valuation]\ncalibraton_per_tier: 10\n"
    )
    with pytest.raises(ConfigError) as exc:
        load_config(str(path))
    assert "not recognised" in str(exc.value)
    assert "calibraton_per_tier" in str(exc.value)
    assert "override_difficulties" not in ALLOWED_CONFIG_KEYS


def test_calibration_config_requires_models_and_families(tmp_path):
    from run_calibration import ConfigError, load_config

    path = tmp_path / "empty.yaml"
    path.write_text("master_seed: 1\n")
    with pytest.raises(ConfigError) as exc:
        load_config(str(path))
    assert "missing required key" in str(exc.value)


def test_calibration_config_rejects_stage_2_token_budgets(tmp_path):
    from run_calibration import ConfigError, load_config

    path = tmp_path / "budgets.yaml"
    path.write_text(
        "models: [mock]\nfamilies: [lte_valuation]\n"
        "max_new_tokens:\n  solve: 512\n  classify: 64\n"
    )
    with pytest.raises(ConfigError) as exc:
        load_config(str(path))
    assert "classify" in str(exc.value)


def test_stage_2_configs_are_rejected_by_the_stage_1_loader():
    from run_calibration import ConfigError, load_config

    for name in ("pilot.yaml", "final.yaml", "mock.yaml"):
        with pytest.raises(ConfigError):
            load_config(os.path.join(ROOT, "configs", name))


def test_shipped_calibration_configs_are_stage_1_only():
    from run_calibration import load_config

    for name in ("calibration.yaml", "calibration_smoke.yaml", "calibration_mock.yaml"):
        config = load_config(os.path.join(ROOT, "configs", name))
        assert set(config["max_new_tokens"]) == {"solve"}
        assert config["calibration_per_tier"] >= 1
        assert config["families"] == [
            "order_minus_one", "lte_valuation", "recurrence_substitution"
        ]
    real = load_config(os.path.join(ROOT, "configs", "calibration.yaml"))
    assert real["calibration_per_tier"] == 10
    assert real["models"] == [
        "qwen3_8b", "deepseek_r1_llama_8b", "smollm3_3b", "llama32_3b"
    ]
    assert real["precision"] == "bf16_or_fp16"
