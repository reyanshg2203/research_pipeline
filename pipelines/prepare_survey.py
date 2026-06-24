#!/usr/bin/env python3
"""
Generate all survey materials: 10 lessons × 3 pipeline variants (30 NL texts per pipeline).

Survey mapping (3 problems per lesson, _001/_002/_003 slots):
  Part 1  outputs/schema_lesson_XX_00N.txt          — Haiku baseline + schema_to_text
  Part 2  refined/schema_lesson_XX_001_refined.txt  — Opus judge + refine_nl (3 iterations)
  Part 3a validated/schema_<id>_functional.txt      — refine_schema + schema_to_text
  Part 3b validated/schema_<id>_refined.txt         — refine_schema + prose_nl
  Part 4  (in app) — same prose as Part 3b, rated if marked faithful in Part 3

Usage:
  python3 pipelines/prepare_survey.py              # regenerate all steps
  python3 pipelines/prepare_survey.py --fresh      # wipe survey artifacts, then full regen
  python3 pipelines/prepare_survey.py --step 1     # only Part 1 (baseline generation)
  python3 pipelines/prepare_survey.py --step 3     # only Part 3 (functional + prose)
  python3 pipelines/prepare_survey.py --freeze     # snapshot Pipeline 1 outputs to frozen dir
  python3 pipelines/prepare_survey.py --freeze v2  # snapshot with custom tag
"""

from __future__ import annotations

import argparse
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
LESSONS = ["01", "03", "05", "06", "08", "09", "10", "14", "15", "16"]
OUTPUTS_DIR = ROOT / "outputs"
REFINED_DIR = ROOT / "refined"
VALIDATED_DIR = ROOT / "validated"


def _stem(lesson: str) -> str:
    return f"schema_lesson_{lesson}_001"


def clean_survey_artifacts(*, validated: bool = True) -> None:
    """Remove prior survey outputs so the next run is a clean slate."""
    removed = 0
    for lesson in LESSONS:
        for path in sorted(OUTPUTS_DIR.glob(f"schema_lesson_{lesson}_*")):
            if path.is_file():
                path.unlink()
                removed += 1
                print(f"  removed {path.relative_to(ROOT)}")
        for path in (
            REFINED_DIR.glob(f"schema_lesson_{lesson}_001_refined.txt"),
            REFINED_DIR.glob(f"schema_lesson_{lesson}_001_refined_trace.json"),
        ):
            for p in path:
                p.unlink()
                removed += 1
                print(f"  removed {p.relative_to(ROOT)}")

    if validated and VALIDATED_DIR.is_dir():
        for path in sorted(VALIDATED_DIR.glob("schema_*")):
            if path.is_file():
                path.unlink()
                removed += 1
                print(f"  removed {path.relative_to(ROOT)}")

    print(f"Cleaned {removed} file(s).")


def freeze_pipeline1(tag: str = "v1") -> None:
    """Copy current Pipeline 1 outputs into a frozen, immutable snapshot directory."""
    frozen_dir = ROOT / f"outputs_pipeline1_{tag}_frozen"
    frozen_dir.mkdir(exist_ok=True)
    copied = 0
    for lesson in LESSONS:
        for slot in ["001", "002", "003"]:
            stem = f"schema_lesson_{lesson}_{slot}"
            for ext in (".txt", ".json"):
                src = OUTPUTS_DIR / f"{stem}{ext}"
                if src.exists():
                    dst = frozen_dir / src.name
                    dst.write_bytes(src.read_bytes())
                    copied += 1
                    print(f"  frozen {src.relative_to(ROOT)} → {dst.relative_to(ROOT)}")
    print(f"Frozen {copied} file(s) into {frozen_dir.relative_to(ROOT)}/")


def run(cmd: list[str], label: str, *, allow_fail: bool = False) -> int:
    print(f"\n{'=' * 60}\n{label}\n{'=' * 60}")
    result = subprocess.run(cmd, cwd=ROOT)
    if result.returncode != 0 and not allow_fail:
        raise SystemExit(f"Failed: {' '.join(cmd)}")
    return result.returncode


def step1_generate(py: str) -> None:
    run(
        [py, "pipelines/generate_schema.py"],
        "Step 1/3 — Part 1: Haiku baseline schemas + function-translated NL (all lessons)",
    )


def step2_refine_nl(py: str) -> None:
    for lesson in LESSONS:
        run(
            [py, "pipelines/refine_nl.py", "--problem", f"outputs/{_stem(lesson)}.txt"],
            f"Step 2/3 — Part 2: Opus-judge + Haiku NL refine (lesson {lesson})",
        )


def step3_refine_schema(py: str) -> None:
    for lesson in LESSONS:
        rc = run(
            [py, "pipelines/refine_schema.py", "--schema", f"outputs/{_stem(lesson)}.json"],
            f"Step 3/3 — Part 3: Prolog validate/repair + functional NL + Haiku prose (lesson {lesson})",
            allow_fail=True,
        )
        if rc != 0:
            print(f"  Warning: refine_schema exited {rc} for lesson {lesson} (outputs may still exist)")


def readiness_check(py: str) -> None:
    run(
        [
            py,
            "-c",
            "from pipelines.app import load_survey_problems, _readiness; "
            "r=_readiness(load_survey_problems()); print('Readiness:', r); "
            "assert r['part1']==10 and r['part2']==10 and r['part3']==10, r",
        ],
        "Final readiness check",
        allow_fail=True,
    )


def main() -> None:
    parser = argparse.ArgumentParser(
        description="Generate all geometry evaluator survey materials."
    )
    parser.add_argument(
        "--fresh",
        action="store_true",
        help="Delete prior survey outputs and all validated/ artifacts before regenerating.",
    )
    parser.add_argument(
        "--step",
        type=int,
        choices=[1, 2, 3],
        default=None,
        help="Run only one step (default: run all three in order).",
    )
    parser.add_argument(
        "--skip-clean-validated",
        action="store_true",
        help="With --fresh, keep existing validated/ files (only clears outputs/ and refined/).",
    )
    parser.add_argument(
        "--freeze",
        metavar="TAG",
        nargs="?",
        const="v1",
        help="Snapshot current Pipeline 1 outputs into outputs_pipeline1_TAG_frozen/ (default TAG: v1).",
    )
    args = parser.parse_args()
    py = sys.executable

    if args.freeze:
        print(f"=== Freezing Pipeline 1 outputs (tag: {args.freeze}) ===")
        freeze_pipeline1(args.freeze)

    if args.fresh:
        print("=== Cleaning prior survey artifacts ===")
        clean_survey_artifacts(validated=not args.skip_clean_validated)

    steps = [args.step] if args.step else [1, 2, 3]
    if 1 in steps:
        step1_generate(py)
    if 2 in steps:
        step2_refine_nl(py)
    if 3 in steps:
        step3_refine_schema(py)

    readiness_check(py)


if __name__ == "__main__":
    main()