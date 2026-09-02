"""Stage 1 -- zero-shot difficulty calibration.  Standalone.

    python scripts/run_calibration.py --config configs/calibration.yaml

This script deliberately imports NOTHING from the strategy-boundary experiment.
It does not touch seeds, strategy induction, H0, Active, Passive, hidden tests,
token matching or the competition OOD set, and `tests/test_calibration.py`
asserts that none of those modules is even imported when it runs.

It produces only:

    outputs/<RUN_ID>/
      run_manifest.json
      config.yaml
      calibration_problem_bank.json
      calibration_problem_bank_researcher.json
      calibration_runs.jsonl
      calibration_summary.csv
      pooled_difficulty_summary.csv
      selected_difficulties.json
      calibration_report.md
      errors.log
"""

import argparse
import csv
import json
import os
import platform
import subprocess
import sys
import time
import traceback
from dataclasses import asdict
from typing import Any, Dict, List, Sequence

import _bootstrap  # noqa: F401
import yaml

import prompts as prompt_module
from calibration import (
    PREFERRED_RANGE,
    RULE_EXCLUDED_INPUTS,
    RULE_TEXT,
    TARGET_POINT,
    TIE_BREAKER,
    bank_public_records,
    bank_researcher_records,
    build_problem_bank,
    calibration_report,
    diagnostics,
    pooled_by_difficulty,
    run_zero_shot_calibration,
    select_difficulty,
    summarise_by_cell,
)
from families import get_family
from models import (
    MODEL_REGISTRY,
    GatedModelError,
    environment_report,
    load_model,
    resolve_substitutions,
)
from sampling import derive_seed

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))

DEFAULTS: Dict[str, Any] = {
    "master_seed": 20260901,
    "precision": "bf16_or_fp16",
    "temperature": 0.6,
    "top_p": 0.95,
    "top_k": 20,
    "calibration_per_tier": 10,
    "difficulties": ["easy", "medium", "hard"],
    "max_new_tokens": {"solve": 2048},
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

    stage2 = [
        k for k in raw
        if k in ("seed_candidates", "seed_count", "h0_pilot_size", "active_rounds",
                 "active_batch_size", "iid_test_size", "challenge_test_size",
                 "adaptation_repeats", "passive_max_rounds")
    ]
    if stage2:
        raise ValueError(
            f"{path} contains Stage-2 settings {stage2}. A calibration config "
            f"must contain only Stage-1 settings (calibration spec S.23)."
        )
    return config


def git_commit():
    try:
        return subprocess.check_output(
            ["git", "rev-parse", "HEAD"], stderr=subprocess.DEVNULL, cwd=ROOT
        ).decode().strip()
    except Exception:
        return None


def write_csv(path: str, rows: Sequence[Dict[str, Any]]) -> None:
    if not rows:
        open(path, "w", encoding="utf-8").close()
        return
    keys: List[str] = []
    for row in rows:
        for k in row:
            if k not in keys:
                keys.append(k)
    with open(path, "w", newline="", encoding="utf-8") as fh:
        writer = csv.DictWriter(fh, fieldnames=keys)
        writer.writeheader()
        for row in rows:
            writer.writerow(row)


def parse_substitutions(items: Sequence[str]) -> Dict[str, str]:
    out: Dict[str, str] = {}
    for item in items or ():
        if "=" not in item:
            raise ValueError(f"--substitute expects alias=alias, got {item!r}")
        src, dst = item.split("=", 1)
        out[src.strip()] = dst.strip()
    return out


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--config", required=True)
    ap.add_argument("--run-id", default=None)
    ap.add_argument("--tag", default="")
    ap.add_argument("--outputs", default=os.path.join(ROOT, "outputs"))
    ap.add_argument(
        "--substitute", nargs="*", default=[],
        help="EXPLICIT model substitution, e.g. --substitute llama32_3b=phi35_mini. "
             "Nothing is ever substituted automatically.",
    )
    ap.add_argument("--skip-self-test", action="store_true",
                    help="NOT for a real calibration run")
    args = ap.parse_args(argv)

    if not args.skip_self_test:
        print("running scripts/self_test.py --quick before touching a model ...")
        proc = subprocess.run(
            [sys.executable, os.path.join(ROOT, "scripts", "self_test.py"), "--quick"],
            cwd=ROOT,
        )
        if proc.returncode != 0:
            print("\nself-test FAILED; refusing to run models.", file=sys.stderr)
            return proc.returncode
    else:
        print("[WARN] self-test skipped -- this run must not be used scientifically")

    config = load_config(args.config)
    substitutions = parse_substitutions(args.substitute)
    aliases = resolve_substitutions(list(config["models"]), substitutions)
    if substitutions:
        print(f"[!] EXPLICIT model substitution applied: {substitutions}")
        for _src, dst in substitutions.items():
            note = MODEL_REGISTRY[dst].note
            if note:
                print(f"    {dst}: {note}")

    run_id = args.run_id or (
        time.strftime("%Y%m%d-%H%M%S")
        + "_"
        + os.path.splitext(os.path.basename(args.config))[0]
        + (f"_{args.tag}" if args.tag else "")
    )
    run_dir = os.path.join(args.outputs, run_id)
    os.makedirs(run_dir, exist_ok=True)
    errors_path = os.path.join(run_dir, "errors.log")
    with open(errors_path, "w", encoding="utf-8") as fh:
        fh.write(f"# calibration errors for run {run_id}\n")

    def log_error(where: str, exc: BaseException) -> None:
        with open(errors_path, "a", encoding="utf-8") as fh:
            fh.write(f"\n=== {time.strftime('%Y-%m-%d %H:%M:%S')} :: {where} ===\n"
                     f"{type(exc).__name__}: {exc}\n{traceback.format_exc()}\n")
        print(f"[ERROR] {where}: {type(exc).__name__}: {exc}", file=sys.stderr)

    print(f"\nrun directory: {run_dir}")

    families = {name: get_family(name) for name in config["families"]}
    per_tier = int(config["calibration_per_tier"])
    master_seed = int(config["master_seed"])
    difficulties = list(config["difficulties"])

    # ---- 1. the shared, validated problem bank, BEFORE any inference -----
    print(f"\n=== building the shared calibration problem bank "
          f"({per_tier} per family per tier) ===")
    built = build_problem_bank(families, per_tier, master_seed, difficulties)
    bank = built["bank"]
    for failure in built["validation_failures"]:
        with open(errors_path, "a", encoding="utf-8") as fh:
            fh.write(f"validation failure (problem discarded, replacement drawn): "
                     f"{json.dumps(failure)}\n")
    if built["validation_failures"]:
        print(f"  [!] {len(built['validation_failures'])} problem(s) failed "
              f"validation, were discarded and replaced; see errors.log")

    public = bank_public_records(bank)
    with open(os.path.join(run_dir, "calibration_problem_bank.json"), "w",
              encoding="utf-8") as fh:
        json.dump({
            "run_id": run_id,
            "master_seed": master_seed,
            "calibration_per_tier": per_tier,
            "note": "one shared bank; every model receives exactly these problems",
            "problems": public,
        }, fh, indent=2)
    with open(os.path.join(run_dir, "calibration_problem_bank_researcher.json"), "w",
              encoding="utf-8") as fh:
        json.dump({
            "note": "researcher-side metadata; NEVER enters a prompt",
            "families": bank_researcher_records(bank),
        }, fh, indent=2, default=str)
    for name in families:
        counts = {d: len(bank[name][d]) for d in difficulties}
        balance = {
            d: sum(1 for p in bank[name][d] if p.strategy_applies)
            for d in difficulties
        }
        print(f"  {name:26} {counts}  (positive applicability: {balance})")
    print(f"  bank frozen: {len(public)} problems, identical for every model")

    # ---- 2. manifest -----------------------------------------------------
    manifest: Dict[str, Any] = {
        "stage": "1_zero_shot_calibration_only",
        "run_id": run_id,
        "run_dir": run_dir,
        "timestamp_utc": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
        "git_commit": git_commit(),
        "python": sys.version.split()[0],
        "platform": platform.platform(),
        "environment": environment_report(),
        "config": {k: v for k, v in config.items() if not k.startswith("_")},
        "config_path": config.get("_config_path"),
        "master_seed": master_seed,
        "calibration_per_tier": per_tier,
        "precision": config["precision"],
        "requested_models": list(config["models"]),
        "resolved_models": aliases,
        "explicit_substitutions": substitutions,
        "models": [{"alias": a, **{k: v for k, v in asdict(MODEL_REGISTRY[a]).items()
                                   if k != "alias"}} for a in aliases],
        "family_versions": {n: f.version_hash() for n, f in families.items()},
        "prompt_version": prompt_module.PROMPT_VERSION,
        "prompt_hash": prompt_module.prompts_hash(),
        "zero_shot_prompt": {
            "system": prompt_module.SOLVE_SYSTEM,
            "user_template": prompt_module.SOLVE_USER,
        },
        "selection_rule": {
            "target": TARGET_POINT,
            "preferred_range": list(PREFERRED_RANGE),
            "tie_breaker": TIE_BREAKER,
            "text": RULE_TEXT,
            "excluded_inputs": RULE_EXCLUDED_INPUTS,
        },
        "attempts_per_problem": 1,
        "bank_seed_stream": derive_seed(master_seed, "calibration_bank"),
        "contains_mock_model": "mock" in aliases,
        "not_run": [
            "seed_selection", "strategy_induction", "h0_induction",
            "h0_boundary_evaluation", "active_adaptation", "passive_adaptation",
            "hidden_iid_evaluation", "challenge_evaluation",
            "token_budget_matching", "competition_ood",
        ],
    }
    if config["precision"] == "4bit":
        manifest["WARNING_precision"] = (
            "4-bit NF4 is a smoke/Colab setting. Smoke-test accuracies must NOT be "
            "used to select a difficulty tier (calibration spec S.9)."
        )
    if "mock" in aliases:
        manifest["WARNING_mock"] = (
            "Offline MOCK model: this exercises the pipeline and produces NO "
            "scientific results."
        )
    with open(os.path.join(run_dir, "config.yaml"), "w", encoding="utf-8") as fh:
        yaml.safe_dump({k: v for k, v in config.items() if not k.startswith("_")},
                       fh, sort_keys=True)

    # ---- 3. zero-shot solving, one model at a time -----------------------
    all_rows: List[Dict[str, Any]] = []
    model_details: List[Dict[str, Any]] = []
    print(f"\n=== zero-shot solving: {len(aliases)} model(s) x "
          f"{len(public)} problems, ONE attempt each ===")
    for alias in aliases:
        print(f"\n  loading {alias} ({MODEL_REGISTRY[alias].model_id}) ...")
        try:
            model = load_model(alias, {
                "precision": config["precision"],
                "temperature": config["temperature"],
                "top_p": config["top_p"],
                "top_k": config["top_k"],
            })
        except GatedModelError as exc:
            log_error(f"load:{alias}", exc)
            print(f"\n{exc}\n", file=sys.stderr)
            return 2
        except Exception as exc:  # noqa: BLE001
            log_error(f"load:{alias}", exc)
            return 2
        try:
            rows = run_zero_shot_calibration(
                model, families, bank, config["max_new_tokens"]["solve"], master_seed
            )
            all_rows.extend(rows)
            model_details.append(model.describe())
        finally:
            model.unload()

    manifest["model_details"] = model_details
    with open(os.path.join(run_dir, "run_manifest.json"), "w", encoding="utf-8") as fh:
        json.dump(manifest, fh, indent=2, default=str)

    # ---- 4. metrics, selection, report -----------------------------------
    with open(os.path.join(run_dir, "calibration_runs.jsonl"), "w",
              encoding="utf-8") as fh:
        for row in all_rows:
            fh.write(json.dumps(row, default=str) + "\n")

    per_cell = summarise_by_cell(all_rows)
    pooled = pooled_by_difficulty(all_rows)
    write_csv(os.path.join(run_dir, "calibration_summary.csv"), per_cell)
    write_csv(os.path.join(run_dir, "pooled_difficulty_summary.csv"), pooled)

    selections: Dict[str, Dict[str, Any]] = {}
    warnings: Dict[str, List[str]] = {}
    print("\n=== predeclared difficulty selection ===")
    print(f"  rule: {RULE_TEXT}")
    for name in families:
        selections[name] = select_difficulty(pooled, name)
        warnings[name] = diagnostics(pooled, per_cell, name)
        sel = selections[name]
        if sel.get("selected"):
            print(f"  {name:26} -> {sel['selected']:6} "
                  f"(pooled {sel['pooled_accuracy']:.3f})")
        else:
            print(f"  {name:26} -> {sel['status']}: " + ", ".join(
                f"{d}={a:.3f}" for d, a in sorted(sel["accuracies"].items())))
        for w in warnings[name]:
            print(f"      [warn] {w}")

    with open(os.path.join(run_dir, "selected_difficulties.json"), "w",
              encoding="utf-8") as fh:
        json.dump({**selections, "_warnings": warnings}, fh, indent=2, default=str)

    report = calibration_report(per_cell, pooled, selections, warnings, manifest)
    with open(os.path.join(run_dir, "calibration_report.md"), "w",
              encoding="utf-8") as fh:
        fh.write(report)

    print(f"\n=== done ===\n  {run_dir}")
    for name in ("run_manifest.json", "calibration_problem_bank.json",
                 "calibration_runs.jsonl", "calibration_summary.csv",
                 "pooled_difficulty_summary.csv", "selected_difficulties.json",
                 "calibration_report.md", "errors.log"):
        print(f"    {name}")
    if "mock" in aliases:
        print("\n[!] MOCK model run: these numbers are a pipeline test, NOT results.")
    if config["precision"] == "4bit":
        print("\n[!] 4-bit smoke run: do NOT use these accuracies to select a tier.")
    print("\nStage 2 (seeds / H0 / Active / Passive) has NOT been run and must not")
    print("be started until the authors approve the tiers above.")
    unviable = [n for n, s in selections.items() if not s.get("selected")]
    return 1 if unviable else 0


if __name__ == "__main__":
    sys.exit(main())
