"""End-to-end experiment orchestration (spec S.19, S.22).

Pipeline order, with everything frozen to disk before it is used:

  0. run manifest (git commit, versions, seeds, config, family/prompt hashes)
  1. zero-shot difficulty calibration            -> selected_difficulties.json
  2. seed-candidate screening + COMMON seed set  -> seeds_<family>.json
  3. FREEZE hidden IID + challenge tests         -> hidden_*_<family>.json
  4. per model: induce S_hat and H0
  5.            H0 pilot on a held-out balanced set
  6.            Active adaptation
  7.            Passive adaptation, matched on adaptation output tokens
  8.            evaluate frozen H0 / HP / HA on both hidden splits
  9. tables

Models are loaded and unloaded one at a time.
"""

from __future__ import annotations

import csv
import json
import os
import platform
import subprocess
import sys
import time
import traceback
from dataclasses import asdict
from typing import Any, Dict, List, Optional, Sequence

import yaml

import prompts as prompt_module
from active import run_active
from calibration import (
    TARGET_BAND,
    TARGET_POINT,
    run_difficulty_calibration,
    screen_seed_candidates,
    seed_review_markdown,
    select_seed_set,
    select_difficulty,
)
from evaluation import evaluate_hypothesis
from families import get_family
from families.base import ProblemFamily
from metrics import paired_bootstrap_delta
from models import MODEL_REGISTRY, BaseModel, environment_report, load_model
from ood import load_competition_ood
from passive import run_passive
from sampling import assert_disjoint, derive_seed, label_balance, stream
from schemas import Problem
from seed_induction import InductionFailure, classify_h0_band, induce_strategy_and_h0

DEFAULTS: Dict[str, Any] = {
    "master_seed": 20260101,
    "precision": "bf16_or_fp16",
    "temperature": 0.6,
    "top_p": 0.95,
    "top_k": 20,
    "use_thinking": True,
    "calibration_per_tier": 6,
    "seed_candidates": 12,
    "seed_count": 6,
    "h0_pilot_size": 20,
    "active_rounds": 3,
    "active_batch_size": 3,
    "iid_test_size": 40,
    "challenge_test_size": 20,
    "adaptation_repeats": 1,
    "passive_max_rounds": 40,
    "balanced_tests": True,
    "show_features_in_observations": False,
    "difficulties": ["easy", "medium", "hard"],
    "max_new_tokens": {
        "solve": 2048,
        "induce": 1800,
        "query": 800,
        "revise": 1200,
        "classify": 500,
    },
}


def load_config(path: str) -> Dict[str, Any]:
    with open(path, "r", encoding="utf-8") as fh:
        raw = yaml.safe_load(fh) or {}
    config = dict(DEFAULTS)
    config.update({k: v for k, v in raw.items() if k != "max_new_tokens"})
    mnt = dict(DEFAULTS["max_new_tokens"])
    mnt.update(raw.get("max_new_tokens") or {})
    config["max_new_tokens"] = mnt
    config["_config_path"] = path
    return config


def git_commit() -> Optional[str]:
    try:
        return (
            subprocess.check_output(
                ["git", "rev-parse", "HEAD"], stderr=subprocess.DEVNULL
            )
            .decode()
            .strip()
        )
    except Exception:
        return None


class Runner:
    def __init__(self, config: Dict[str, Any], run_dir: str):
        self.config = config
        self.run_dir = run_dir
        os.makedirs(run_dir, exist_ok=True)
        self.errors_path = os.path.join(run_dir, "errors.log")
        # always exists, so its absence never looks like "no errors were logged"
        if not os.path.exists(self.errors_path):
            with open(self.errors_path, "w", encoding="utf-8") as fh:
                fh.write(f"# errors for run {os.path.basename(run_dir)}\n")
        self.master_seed = int(config["master_seed"])
        self.families: Dict[str, ProblemFamily] = {
            name: get_family(name) for name in config["families"]
        }
        self.model_aliases: List[str] = list(config["models"])
        self.is_mock_run = all(a == "mock" for a in self.model_aliases)
        self.has_mock = any(a == "mock" for a in self.model_aliases)
        self.ood: Dict[str, List[Problem]] = {}
        self.failures: List[Dict[str, Any]] = []
        self.eval_rows: List[Dict[str, Any]] = []
        self.summary_rows: List[Dict[str, Any]] = []
        self.selected: Dict[str, Any] = {}
        self.seeds: Dict[str, List[Problem]] = {}
        self.frozen: Dict[str, Dict[str, List[Problem]]] = {}

    # ---------------------------------------------------------------- utils
    def log_error(self, where: str, exc: BaseException) -> None:
        entry = (
            f"\n=== {time.strftime('%Y-%m-%d %H:%M:%S')} :: {where} ===\n"
            f"{type(exc).__name__}: {exc}\n{traceback.format_exc()}\n"
        )
        with open(self.errors_path, "a", encoding="utf-8") as fh:
            fh.write(entry)
        print(f"[ERROR] {where}: {type(exc).__name__}: {exc}", file=sys.stderr)
        self.failures.append({"where": where, "error": f"{type(exc).__name__}: {exc}"})

    def path(self, *parts: str) -> str:
        return os.path.join(self.run_dir, *parts)

    def write_json(self, name: str, obj: Any) -> None:
        with open(self.path(name), "w", encoding="utf-8") as fh:
            json.dump(obj, fh, indent=2, default=str)

    def append_jsonl(self, name: str, rows: Sequence[Dict[str, Any]]) -> None:
        with open(self.path(name), "a", encoding="utf-8") as fh:
            for row in rows:
                fh.write(json.dumps(row, default=str) + "\n")

    def write_csv(self, name: str, rows: Sequence[Dict[str, Any]]) -> None:
        if not rows:
            open(self.path(name), "w", encoding="utf-8").close()
            return
        keys: List[str] = []
        for row in rows:
            for k in row:
                if k not in keys:
                    keys.append(k)
        with open(self.path(name), "w", newline="", encoding="utf-8") as fh:
            writer = csv.DictWriter(fh, fieldnames=keys)
            writer.writeheader()
            for row in rows:
                writer.writerow(row)

    # ------------------------------------------------------------- manifest
    def write_manifest(self) -> None:
        manifest = {
            "run_dir": self.run_dir,
            "timestamp_utc": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
            "git_commit": git_commit(),
            "python": sys.version.split()[0],
            "platform": platform.platform(),
            "environment": environment_report(),
            "config": {k: v for k, v in self.config.items() if not k.startswith("_")},
            "config_path": self.config.get("_config_path"),
            "master_seed": self.master_seed,
            "models": [
                {
                    "alias": a,
                    **{
                        k: v
                        for k, v in asdict(MODEL_REGISTRY[a]).items()
                        if k != "alias"
                    },
                }
                for a in self.model_aliases
            ],
            "precision": self.config["precision"],
            "family_versions": {
                name: fam.version_hash() for name, fam in self.families.items()
            },
            # exactly what Active may see and constrain, and the researcher-only
            # diagnostics it may not (revision memo S.4)
            "active_query_schemas": {
                name: fam.query_schema() for name, fam in self.families.items()
            },
            "oracle_only_feature_schemas": {
                name: fam.oracle_feature_schema for name, fam in self.families.items()
            },
            "prompt_version": prompt_module.PROMPT_VERSION,
            "prompt_hash": prompt_module.prompts_hash(),
            "calibration_rule": {
                "target_band": list(TARGET_BAND),
                "target_point": TARGET_POINT,
            },
            "seed_streams": {
                stage: derive_seed(self.master_seed, stage)
                for stage in (
                    "calibration_problems",
                    "seed_candidates",
                    "hidden_iid",
                    "hidden_challenge",
                    "h0_pilot",
                    "active_sampler",
                    "passive_sampler",
                )
            },
            "is_mock_run": self.is_mock_run,
            "contains_mock_model": self.has_mock,
        }
        if self.config["precision"] == "4bit":
            manifest["WARNING_precision"] = (
                "4-bit NF4 quantisation is a PILOT/COLAB setting. These numbers "
                "must not be mixed with full-precision results without a visible "
                "warning in the paper (spec S.3)."
            )
        if self.has_mock:
            manifest["WARNING_mock"] = (
                "This run used the offline MOCK model. It exercises the pipeline "
                "and produces NO scientific results."
            )
        self.write_manifest_file(manifest)

    def write_manifest_file(self, manifest: Dict[str, Any]) -> None:
        self.write_json("run_manifest.json", manifest)
        with open(self.path("config.yaml"), "w", encoding="utf-8") as fh:
            yaml.safe_dump(
                {k: v for k, v in self.config.items() if not k.startswith("_")},
                fh,
                sort_keys=True,
            )

    # ------------------------------------------------------ model iteration
    def _model_config(self) -> Dict[str, Any]:
        return {
            "precision": self.config["precision"],
            "temperature": self.config["temperature"],
            "top_p": self.config["top_p"],
            "top_k": self.config["top_k"],
            "use_thinking": self.config["use_thinking"],
        }

    # --------------------------------------------------------- stage 1 + 2
    def stage_calibration(self) -> None:
        print("\n=== stage 1: zero-shot difficulty calibration ===")
        per_tier = int(self.config["calibration_per_tier"])
        all_runs: List[Dict[str, Any]] = []
        summaries: List[Dict[str, Any]] = []
        for alias in self.model_aliases:
            model = load_model(alias, self._model_config())
            try:
                for name, fam in self.families.items():
                    res = run_difficulty_calibration(
                        [model], fam, per_tier,
                        self.config["max_new_tokens"]["solve"],
                        self.master_seed, self.config["difficulties"],
                    )
                    all_runs.extend(res["runs"])
                    print(f"  {alias}/{name}: {len(res['runs'])} zero-shot solves")
            finally:
                model.unload()
        from calibration import summarise_calibration

        summaries = summarise_calibration(all_runs)
        self.append_jsonl("calibration_runs.jsonl", all_runs)
        self.write_csv("calibration_summary.csv", summaries)

        selected = {}
        for name in self.families:
            sel = select_difficulty(summaries, name, self.config["difficulties"])
            selected[name] = sel
            flag = "" if sel["in_band"] else "   <-- OUTSIDE PREDECLARED BAND"
            print(
                f"  selected difficulty for {name}: {sel['selected_difficulty']} "
                f"(pooled zero-shot acc {sel['pooled_accuracy']:.3f}){flag}"
            )
        self.selected = selected
        self.write_json("selected_difficulties.json", selected)

    def stage_seeds(self) -> None:
        print("\n=== stage 2: seed-candidate screening (COMMON seed set) ===")
        all_runs: List[Dict[str, Any]] = []
        per_family_counts: Dict[str, Dict[str, int]] = {n: {} for n in self.families}
        candidates: Dict[str, List[Problem]] = {}
        for alias in self.model_aliases:
            model = load_model(alias, self._model_config())
            try:
                for name, fam in self.families.items():
                    difficulty = self.selected[name]["selected_difficulty"]
                    res = screen_seed_candidates(
                        [model], fam,
                        int(self.config["seed_candidates"]),
                        difficulty,
                        self.config["max_new_tokens"]["solve"],
                        self.master_seed,
                    )
                    all_runs.extend(res["runs"])
                    drawn = [Problem.from_json(d) for d in res["candidates"]]
                    if name in candidates:
                        # the candidate list must be identical for every model,
                        # otherwise the seed set is not genuinely common
                        assert [p.id for p in drawn] == [
                            p.id for p in candidates[name]
                        ], f"{name}: seed candidates differ between models"
                    candidates[name] = drawn
                    for pid, c in res["solve_counts"].items():
                        per_family_counts[name][pid] = (
                            per_family_counts[name].get(pid, 0) + c
                        )
            finally:
                model.unload()
        self.append_jsonl("seed_candidate_runs.jsonl", all_runs)

        for name, fam in self.families.items():
            counts = per_family_counts[name]
            pool = candidates[name]
            chosen = select_seed_set(
                pool, counts, int(self.config["seed_count"]), fam.base_templates
            )
            self.seeds[name] = chosen
            self.write_json(
                f"seeds_{name}.json",
                {
                    "family": name,
                    "difficulty": self.selected[name]["selected_difficulty"],
                    "common_seed_set_across_models": True,
                    "pooled_solve_counts": counts,
                    "seeds": [p.to_json() for p in chosen],
                },
            )
            with open(self.path(f"seeds_{name}_review.md"), "w", encoding="utf-8") as fh:
                fh.write(seed_review_markdown(fam, chosen, counts))
            print(f"  {name}: selected {len(chosen)} seeds (pooled solve counts "
                  f"{[counts.get(p.id, 0) for p in chosen]})")

    # ------------------------------------------------------------- stage 3
    def stage_freeze_tests(self) -> None:
        print("\n=== stage 3: freezing hidden tests BEFORE any adaptation ===")
        self.ood = load_competition_ood()
        if self.ood:
            print(f"  loaded author-curated competition OOD sets for "
                  f"{sorted(self.ood)}")
        for name, fam in self.families.items():
            difficulty = self.selected[name]["selected_difficulty"]
            seed_keys = {p.content_key() for p in self.seeds[name]}

            pilot = fam.generate_iid_test(
                stream(self.master_seed, "h0_pilot", name),
                int(self.config["h0_pilot_size"]), difficulty,
                exclude=seed_keys, balanced=bool(self.config["balanced_tests"]),
            )
            used = seed_keys | {p.content_key() for p in pilot}
            iid = fam.generate_iid_test(
                stream(self.master_seed, "hidden_iid", name),
                int(self.config["iid_test_size"]), difficulty,
                exclude=used, balanced=bool(self.config["balanced_tests"]),
            )
            used |= {p.content_key() for p in iid}
            challenge = fam.generate_challenge_test(
                stream(self.master_seed, "hidden_challenge", name),
                int(self.config["challenge_test_size"]), difficulty,
                exclude=used, balanced=bool(self.config["balanced_tests"]),
            )
            assert_disjoint(
                {
                    "seeds": self.seeds[name],
                    "h0_pilot": pilot,
                    "hidden_iid": iid,
                    "hidden_challenge": challenge,
                }
            )
            self.frozen[name] = {"h0_pilot": pilot, "iid": iid, "challenge": challenge}
            ood = self.ood.get(name) or []
            if ood:
                # author-curated, human-labelled; kept strictly separate
                self.frozen[name]["competition_ood"] = ood
                self.write_json(
                    f"competition_ood_{name}.json",
                    {"family": name,
                     "label_provenance": "human author review, not a programmatic oracle",
                     "balance": label_balance(ood),
                     "problems": [p.to_json() for p in ood]},
                )
                print(f"  {name}: competition_ood={label_balance(ood)} "
                      f"(human-labelled, reported separately)")
            self.write_json(
                f"hidden_iid_{name}.json",
                {"family": name, "difficulty": difficulty,
                 "balance": label_balance(iid),
                 "problems": [p.to_json() for p in iid]},
            )
            self.write_json(
                f"hidden_challenge_{name}.json",
                {"family": name, "difficulty": difficulty,
                 "balance": label_balance(challenge),
                 "templates": fam.challenge_templates,
                 "problems": [p.to_json() for p in challenge]},
            )
            self.write_json(
                f"h0_pilot_{name}.json",
                {"family": name, "difficulty": difficulty,
                 "balance": label_balance(pilot),
                 "problems": [p.to_json() for p in pilot]},
            )
            print(
                f"  {name}: iid={label_balance(iid)} challenge={label_balance(challenge)} "
                f"h0_pilot={label_balance(pilot)}"
            )

    # ------------------------------------------------------------- stage 4+
    def stage_main(self) -> None:
        print("\n=== stage 4-8: induction, adaptation, evaluation ===")
        repeats = int(self.config["adaptation_repeats"])
        for alias in self.model_aliases:
            model = load_model(alias, self._model_config())
            try:
                for name, fam in self.families.items():
                    for repeat in range(repeats):
                        try:
                            self._run_model_family(model, fam, repeat)
                        except Exception as exc:  # noqa: BLE001
                            self.log_error(f"{alias}/{name}/repeat{repeat}", exc)
            finally:
                model.unload()

    def _run_model_family(self, model: BaseModel, fam: ProblemFamily, repeat: int) -> None:
        name = fam.name
        alias = model.spec.alias
        difficulty = self.selected[name]["selected_difficulty"]
        mnt = self.config["max_new_tokens"]
        seed = derive_seed(self.master_seed, "repeat", repeat) % (2 ** 31)
        print(f"\n  --- {alias} / {name} / repeat {repeat} (difficulty={difficulty}) ---")

        # 4. induction
        induction = induce_strategy_and_h0(
            model, fam, self.seeds[name], mnt["induce"], seed
        )
        strategy, h0 = induction["strategy"], induction["hypothesis"]
        print(f"    H0: {h0[:140]}")

        # 5. H0 pilot -- recorded BEFORE any adaptation (spec S.24.2)
        pilot_eval = evaluate_hypothesis(
            model, name, "h0", "h0_pilot", strategy, h0,
            self.frozen[name]["h0_pilot"], mnt["classify"], seed,
        )
        h0_pilot_acc = pilot_eval["metrics"]["accuracy"]
        induction["h0_pilot_accuracy"] = h0_pilot_acc
        induction["h0_pilot_band"] = classify_h0_band(h0_pilot_acc)
        induction["repeat"] = repeat
        self.write_json(f"induction_{alias}_{name}_r{repeat}.json", induction)
        self.eval_rows.extend(pilot_eval["rows"])
        print(f"    H0 pilot accuracy: {h0_pilot_acc:.3f} ({induction['h0_pilot_band']})")

        # adaptation must not reuse anything frozen
        exclude = (
            {p.content_key() for p in self.seeds[name]}
            | {p.content_key() for p in self.frozen[name]["h0_pilot"]}
            | {p.content_key() for p in self.frozen[name]["iid"]}
            | {p.content_key() for p in self.frozen[name]["challenge"]}
        )

        # 6. Active
        active = run_active(
            model, fam, strategy, h0, difficulty,
            int(self.config["active_rounds"]), int(self.config["active_batch_size"]),
            mnt, seed, exclude,
            show_features=bool(self.config["show_features_in_observations"]),
        )
        print(
            f"    Active: {active.adaptation_output_tokens} output tokens, "
            f"{active.n_observations} obs, {active.n_unsatisfiable} unsat"
        )

        # 7. Passive, matched on adaptation output tokens
        passive = run_passive(
            model, fam, strategy, h0, difficulty,
            int(self.config["active_batch_size"]),
            active.adaptation_output_tokens, mnt, seed, exclude,
            max_rounds=int(self.config["passive_max_rounds"]),
            show_features=bool(self.config["show_features_in_observations"]),
        )
        print(
            f"    Passive: {passive.adaptation_output_tokens} output tokens "
            f"({passive.notes['relative_mismatch']:+.1%} vs Active), "
            f"{passive.n_observations} obs"
        )
        if passive.notes["budget_cap_binding"]:
            print("    [WARN] passive round cap bound before reaching the token budget")

        self.write_json(f"active_trace_{alias}_{name}_r{repeat}.json", active.to_json())
        self.write_json(f"passive_trace_{alias}_{name}_r{repeat}.json", passive.to_json())

        # 8. frozen evaluation of H0 / HP / HA
        hypotheses = {
            "H0": h0,
            "Passive": passive.final_hypothesis,
            "Active": active.final_hypothesis,
        }
        splits = ["iid", "challenge"]
        if self.frozen[name].get("competition_ood"):
            splits.append("competition_ood")
        for split in splits:
            problems = self.frozen[name][split]
            preds: Dict[str, List[Optional[bool]]] = {}
            y_true = [p.strategy_applies for p in problems]
            for condition, hypothesis in hypotheses.items():
                res = evaluate_hypothesis(
                    model, name, condition, split, strategy, hypothesis,
                    problems, mnt["classify"], seed,
                )
                self.eval_rows.extend(res["rows"])
                preds[condition] = res["y_pred"]
                row = {
                    "model": alias, "family": name, "repeat": repeat, "split": split,
                    "condition": condition, "difficulty": difficulty,
                    "h0_pilot_accuracy": h0_pilot_acc,
                    "is_mock": model.is_mock, "precision": self.config["precision"],
                    **res["metrics"],
                }
                if condition == "Active":
                    row.update({
                        "adaptation_output_tokens": active.adaptation_output_tokens,
                        "n_observations": active.n_observations,
                        "n_revisions": active.n_revisions,
                        "n_unsatisfiable": active.n_unsatisfiable,
                        "n_query_generations": active.n_query_generations,
                        "unsat_rate": active.notes["unsat_rate"],
                    })
                elif condition == "Passive":
                    row.update({
                        "adaptation_output_tokens": passive.adaptation_output_tokens,
                        "n_observations": passive.n_observations,
                        "n_revisions": passive.n_revisions,
                        "relative_mismatch": passive.notes["relative_mismatch"],
                        "budget_cap_binding": passive.notes["budget_cap_binding"],
                    })
                else:
                    row.update({"adaptation_output_tokens": 0, "n_observations": 0,
                                "n_revisions": 0})
                self.summary_rows.append(row)
                print(f"      {split:9} {condition:8} accuracy={res['metrics']['accuracy']:.3f} "
                      f"(unparsed {res['metrics']['unparsed']})")

            for a, b in (("Active", "Passive"), ("Active", "H0"), ("Passive", "H0")):
                d = paired_bootstrap_delta(y_true, preds[a], preds[b], seed=seed)
                self.summary_rows.append({
                    "model": alias, "family": name, "repeat": repeat, "split": split,
                    "condition": f"delta_{a.lower()}_{b.lower()}", "difficulty": difficulty,
                    "accuracy": d["delta"], "ci95_lo": d["lo"], "ci95_hi": d["hi"],
                    "n": len(problems), "is_mock": model.is_mock,
                })

    # ------------------------------------------------------------- tables
    def stage_tables(self) -> None:
        print("\n=== stage 9: tables ===")
        self.append_jsonl("evaluation_raw.jsonl", self.eval_rows)
        self.write_csv("summary_long.csv", self.summary_rows)
        self.write_csv("main_table.csv", build_main_table(self.summary_rows))
        self.write_csv("confusion_matrices.csv", build_confusion_table(self.summary_rows))
        if self.failures:
            self.write_json("failures.json", self.failures)
        print(f"  wrote main_table.csv ({self.run_dir})")

    # ---------------------------------------------------------------- entry
    def run(self) -> Dict[str, Any]:
        self.write_manifest()
        self.stage_calibration()
        self.stage_seeds()
        self.stage_freeze_tests()
        self.stage_main()
        self.stage_tables()
        if self.has_mock:
            print("\n[!] MOCK MODEL RUN -- these outputs are a pipeline test and "
                  "contain NO scientific results.")
        if self.failures:
            print(f"\n[!] {len(self.failures)} failure(s) recorded; see errors.log")
            for f in self.failures:
                print(f"    - {f['where']}: {f['error']}")
        return {"run_dir": self.run_dir, "failures": self.failures}


# --------------------------------------------------------------------------
# table builders
# --------------------------------------------------------------------------


def build_main_table(rows: Sequence[Dict[str, Any]]) -> List[Dict[str, Any]]:
    """Model | Family | Split | H0 | Passive | Active | tokens | observations."""
    keys = sorted(
        {
            (r["model"], r["family"], r["split"], r.get("repeat", 0))
            for r in rows
            if r["condition"] in ("H0", "Passive", "Active")
        }
    )
    out: List[Dict[str, Any]] = []
    for model, family, split, repeat in keys:
        sel = {
            r["condition"]: r
            for r in rows
            if (r["model"], r["family"], r["split"], r.get("repeat", 0))
            == (model, family, split, repeat)
            and r["condition"] in ("H0", "Passive", "Active")
        }
        if not sel:
            continue
        deltas = {
            r["condition"]: r
            for r in rows
            if (r["model"], r["family"], r["split"], r.get("repeat", 0))
            == (model, family, split, repeat)
            and str(r["condition"]).startswith("delta_")
        }
        row = {
            "model": model,
            "family": family,
            "split": split,
            "repeat": repeat,
            "n_test": sel.get("Active", {}).get("n"),
            "H0": _fmt(sel.get("H0", {}).get("accuracy")),
            "Passive": _fmt(sel.get("Passive", {}).get("accuracy")),
            "Active": _fmt(sel.get("Active", {}).get("accuracy")),
            "delta_active_passive": _fmt(
                deltas.get("delta_active_passive", {}).get("accuracy")
            ),
            "delta_active_h0": _fmt(deltas.get("delta_active_h0", {}).get("accuracy")),
            "P_tokens": sel.get("Passive", {}).get("adaptation_output_tokens"),
            "A_tokens": sel.get("Active", {}).get("adaptation_output_tokens"),
            "token_mismatch_pct": _fmt(
                sel.get("Passive", {}).get("relative_mismatch"), pct=True
            ),
            "P_obs": sel.get("Passive", {}).get("n_observations"),
            "A_obs": sel.get("Active", {}).get("n_observations"),
            "A_unsat": sel.get("Active", {}).get("n_unsatisfiable"),
            "A_unsat_rate": _fmt(sel.get("Active", {}).get("unsat_rate")),
            "H0_pilot_acc": _fmt(sel.get("Active", {}).get("h0_pilot_accuracy")),
            "unparsed_H0": sel.get("H0", {}).get("unparsed"),
            "unparsed_P": sel.get("Passive", {}).get("unparsed"),
            "unparsed_A": sel.get("Active", {}).get("unparsed"),
            "is_mock": sel.get("Active", {}).get("is_mock"),
            "precision": sel.get("Active", {}).get("precision"),
        }
        out.append(row)
    return out


def build_confusion_table(rows: Sequence[Dict[str, Any]]) -> List[Dict[str, Any]]:
    out = []
    for r in rows:
        if r["condition"] not in ("H0", "Passive", "Active"):
            continue
        out.append(
            {
                "model": r["model"], "family": r["family"], "split": r["split"],
                "repeat": r.get("repeat", 0), "condition": r["condition"],
                "tp": r.get("tp"), "fp": r.get("fp"), "tn": r.get("tn"),
                "fn": r.get("fn"), "unparsed": r.get("unparsed"),
                "precision_applies": _fmt(r.get("precision_applies")),
                "recall_applies": _fmt(r.get("recall_applies")),
                "f1_applies": _fmt(r.get("f1_applies")),
                "accuracy": _fmt(r.get("accuracy")),
                "ci95_lo": _fmt(r.get("ci95_lo")), "ci95_hi": _fmt(r.get("ci95_hi")),
                "base_rate_positive": _fmt(r.get("base_rate_positive")),
            }
        )
    return out


def _fmt(value: Any, pct: bool = False) -> Any:
    if value is None:
        return ""
    if isinstance(value, float):
        if value != value:
            return ""
        return round(value * 100, 2) if pct else round(value, 4)
    return value
