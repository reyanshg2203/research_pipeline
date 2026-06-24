"""
Pipeline 2: Opus-as-Judge for NL Geometry Problems

Grades a natural-language geometry problem against the 3-criterion rubric
(Geometric Accuracy 50%, Lesson Alignment 30%, Linguistic Clarity 20%)
and emits structured feedback that Haiku can consume in a repair loop.

Input:
  - NL problem text (string)
  - Lesson text (string, full lesson source material)
  - Lesson id (string, for traceability)

Output:
  JSON structure:
  {
    "overall_score": float,           # 0.0 - 4.0, weighted
    "passed": bool,                   # True if overall_score >= 3.0
    "scores": {
        "geometric_accuracy": int,    # 0-4
        "lesson_alignment": int,      # 0-4
        "linguistic_clarity": int     # 0-4
    },
    "rationales": {
        "geometric_accuracy": str,
        "lesson_alignment": str,
        "linguistic_clarity": str
    },
    "feedback_for_haiku": str,        # plain-language repair instructions
    "specific_issues": [              # itemized list for targeted repair
        {"category": str, "severity": str, "issue": str, "suggested_fix": str}
    ]
  }

For a Haiku ↔ Opus repair loop (up to 3 iterations, early stop only on 4/4), use:
  python3 pipelines/refine_nl.py --problem outputs/schema_lesson_XX_YYY.txt
"""

from __future__ import annotations

import json
import os
import re
import sys
from pathlib import Path
from typing import Any

import anthropic
from dotenv import load_dotenv

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

load_dotenv(ROOT / ".env")

client = anthropic.Anthropic(api_key=os.getenv("ANTHROPIC_API_KEY"))

PASS_THRESHOLD = 3.0  # weighted score >= 3.0 considered passing


# ---------------------------------------------------------------------
# Rubric definitions
# ---------------------------------------------------------------------

RUBRIC_TEXT = """
=== RUBRIC ===

You are grading an AI-generated 10th-grade geometry problem against three criteria.
Score each criterion 0-4 (integers only). The weighted overall score is computed as:

  overall = 0.50 * geometric_accuracy + 0.30 * lesson_alignment + 0.20 * linguistic_clarity

HARD CAP: If geometric_accuracy <= 1, the overall score cannot exceed 2.0
regardless of other dimensions. Apply this cap when computing the overall.

---

CRITERION 1: GEOMETRIC ACCURACY (weight 50%)

  4 - All geometric relationships are mathematically correct and consistent.
      Angles, lengths, proportions, and relationships are accurate. No internal
      contradictions. Figures described are completely accurate.

  3 - All major relationships are correct; minor deviations or
      underdeterminations exist that do not meaningfully affect interpretation.
      (The kind of issue only a very attentive student would notice.)

  2 - One major geometric relationship is incorrect OR multiple minor
      inconsistencies exist. Problem remains mostly interpretable but contains
      noticeable errors.

  1 - Multiple major problem violations exist. Relationships are misleading or
      inconsistent. Problem has multiple interpretations or shifts mid-sentence.

  0 - Problem is internally inconsistent or mathematically invalid. Core
      relationships are incorrect. Completely nonsensical.

---

CRITERION 2: LESSON ALIGNMENT (weight 30%)

  4 - Tightly aligned and integrates a supporting lesson concept; pushes to the
      productive edge of difficulty.

  3 - Cleanly aligned to the lesson skill, appropriately challenging (requires
      genuine application), and original enough that pattern-matching won't
      solve it.

  2 - Targets the right skill with a multi-step problem but is generic,
      uninspired, or has a minor content gap.

  1 - Exercises a related but imprecise skill; trivially easy (single-step or
      direct recall); or reskinned from an existing problem with only surface
      changes.

  0 - Wrong skill, off-topic, or copied verbatim from a lesson example.

---

CRITERION 3: LINGUISTIC CLARITY (weight 20%)

  4 - Every term is deliberate; framing naturally scaffolds the student toward
      the right approach without giving it away. Fresh and engaging context.

  3 - Well-phrased, appropriately concise, and pitched at the right reading
      level. A student can read it once and know exactly what is being asked.

  2 - Unambiguous and grammatically sound; the task is clear, but phrasing is
      clunky, verbose, or slightly mismatched to the audience's level.

  1 - Decipherable with effort but contains ambiguous phrasing, undefined
      variables, or wording that could support multiple interpretations.

  0 - Broken grammar, missing information, or contradictory constraints make
      the problem unsolvable as written.

=== END RUBRIC ===
"""


# ---------------------------------------------------------------------
# Prompt construction
# ---------------------------------------------------------------------

def _build_judge_prompt(nl_problem: str, lesson_text: str, lesson_id: str) -> str:
    return f"""You are an expert math curriculum reviewer grading an AI-generated geometry problem.

{RUBRIC_TEXT}

=== LESSON SOURCE MATERIAL ({lesson_id}) ===

{lesson_text}

=== PROBLEM TO GRADE ===

{nl_problem}

=== YOUR TASK ===

Grade the problem above against all three criteria. For each criterion:
  1. Assign an integer score 0-4 based on the rubric descriptors above.
  2. Write a 1-3 sentence rationale that names specific evidence from the problem.

Then write a single "feedback_for_haiku" paragraph that:
  - Is addressed directly to the AI model that wrote the problem (use "you" / "your problem")
  - Identifies the most important fixable issues in plain language
  - Gives concrete, actionable repair instructions (NOT vague suggestions)
  - Does NOT mention rubric scores or grading — Haiku just needs to know what to fix

Then itemize specific issues. For each issue, provide:
  - category: one of "geometric_accuracy", "lesson_alignment", "linguistic_clarity"
  - severity: one of "critical", "major", "minor"
  - issue: what is wrong (one sentence)
  - suggested_fix: how to fix it (one sentence, concrete)

If the problem passes cleanly with no issues, return an empty issues list.

Return your evaluation as a single JSON object with the schema specified by the tool.
"""


# ---------------------------------------------------------------------
# JSON schema for tool use
# ---------------------------------------------------------------------

JUDGMENT_SCHEMA = {
    "type": "object",
    "properties": {
        "scores": {
            "type": "object",
            "properties": {
                "geometric_accuracy": {"type": "integer", "minimum": 0, "maximum": 4},
                "lesson_alignment":   {"type": "integer", "minimum": 0, "maximum": 4},
                "linguistic_clarity": {"type": "integer", "minimum": 0, "maximum": 4},
            },
            "required": ["geometric_accuracy", "lesson_alignment", "linguistic_clarity"],
        },
        "rationales": {
            "type": "object",
            "properties": {
                "geometric_accuracy": {"type": "string"},
                "lesson_alignment":   {"type": "string"},
                "linguistic_clarity": {"type": "string"},
            },
            "required": ["geometric_accuracy", "lesson_alignment", "linguistic_clarity"],
        },
        "feedback_for_haiku": {"type": "string"},
        "specific_issues": {
            "type": "array",
            "items": {
                "type": "object",
                "properties": {
                    "category": {
                        "type": "string",
                        "enum": ["geometric_accuracy", "lesson_alignment", "linguistic_clarity"],
                    },
                    "severity": {
                        "type": "string",
                        "enum": ["critical", "major", "minor"],
                    },
                    "issue": {"type": "string"},
                    "suggested_fix": {"type": "string"},
                },
                "required": ["category", "severity", "issue", "suggested_fix"],
            },
        },
    },
    "required": ["scores", "rationales", "feedback_for_haiku", "specific_issues"],
}


# ---------------------------------------------------------------------
# Score computation
# ---------------------------------------------------------------------

def _compute_overall(scores: dict[str, int]) -> float:
    """Apply weighted score formula with the geometric-accuracy hard cap."""
    raw = (
        0.50 * scores["geometric_accuracy"]
        + 0.30 * scores["lesson_alignment"]
        + 0.20 * scores["linguistic_clarity"]
    )
    # Hard cap from the rubric
    if scores["geometric_accuracy"] <= 1:
        raw = min(raw, 2.0)
    return round(raw, 2)


# ---------------------------------------------------------------------
# Main judging function
# ---------------------------------------------------------------------

def judge_problem(
    nl_problem: str,
    lesson_text: str,
    lesson_id: str,
    model: str = "claude-opus-4-7",
) -> dict[str, Any]:
    """
    Grade an NL geometry problem against the rubric.

    Returns a dict containing scores, rationales, an overall_score,
    a pass/fail flag, plain-language feedback for Haiku, and an itemized
    list of issues.
    """
    prompt = _build_judge_prompt(nl_problem, lesson_text, lesson_id)

    raw = None
    last_reason = None
    for attempt in range(2):  # one retry on a bad/truncated payload
        message = client.messages.create(
            model=model,
            max_tokens=4096,  # was 2000 — too low; truncated the tool JSON on long judgments
            messages=[{"role": "user", "content": prompt}],
            tools=[
                {
                    "name": "submit_judgment",
                    "description": "Submit your rubric evaluation of the geometry problem.",
                    "input_schema": JUDGMENT_SCHEMA,
                }
            ],
            tool_choice={"type": "tool", "name": "submit_judgment"},
        )
        last_reason = message.stop_reason

        tool_use = next(
            (b for b in message.content if b.type == "tool_use"), None
        )
        candidate = tool_use.input if tool_use else None

        # Some SDK paths hand back tool input as a JSON string — parse it.
        if isinstance(candidate, str):
            try:
                candidate = json.loads(candidate)
            except json.JSONDecodeError:
                candidate = None

        required = ("scores", "rationales", "feedback_for_haiku", "specific_issues")
        if (
            message.stop_reason != "max_tokens"
            and isinstance(candidate, dict)
            and all(k in candidate for k in required)
        ):
            raw = candidate
            break

    if raw is None:
        raise RuntimeError(
            f"Judge returned an unusable judgment after retry "
            f"(stop_reason={last_reason}); the tool JSON was likely truncated "
            f"or malformed."
        )

    scores = raw["scores"]
    if isinstance(scores, str):
        scores = json.loads(scores)
    overall = _compute_overall(scores)

    return {
        "overall_score": overall,
        "passed": overall >= PASS_THRESHOLD,
        "scores": scores,
        "rationales": raw["rationales"],
        "feedback_for_haiku": raw["feedback_for_haiku"],
        "specific_issues": raw["specific_issues"],
    }


# ---------------------------------------------------------------------
# Batch convenience: judge an entire outputs/ directory
# ---------------------------------------------------------------------

def judge_directory(
    problems_dir: Path,
    lessons_dir: Path,
    output_dir: Path,
    model: str = "claude-opus-4-7",
) -> list[dict[str, Any]]:
    """
    Walk a directory of NL problem .txt files, find each one's lesson file,
    judge it, and write the judgment JSON next to the problem.
    """
    output_dir.mkdir(parents=True, exist_ok=True)
    results = []

    for txt_path in sorted(problems_dir.glob("schema_lesson_*.txt")):
        nl = txt_path.read_text(encoding="utf-8")

        # Derive lesson id from filename: schema_lesson_03_001.txt -> lesson_03
        match = re.search(r"lesson_(\d+)", txt_path.stem)
        if not match:
            print(f"Skipping {txt_path.name} — couldn't parse lesson id.")
            continue
        lesson_id = f"lesson_{match.group(1).zfill(2)}"
        lesson_path = lessons_dir / f"{lesson_id}.txt"
        if not lesson_path.exists():
            print(f"Skipping {txt_path.name} — lesson file {lesson_path.name} not found.")
            continue
        lesson_text = lesson_path.read_text(encoding="utf-8")

        print(f"\n--- Judging {txt_path.name} (lesson: {lesson_id}) ---")
        try:
            judgment = judge_problem(nl, lesson_text, lesson_id, model=model)
        except Exception as e:
            print(f"  Error: {e}")
            continue

        out_path = output_dir / f"{txt_path.stem}_judgment.json"
        out_path.write_text(json.dumps(judgment, indent=2), encoding="utf-8")

        verdict = "PASS" if judgment["passed"] else "FAIL"
        print(f"  Overall: {judgment['overall_score']:.2f} [{verdict}]")
        print(f"  Scores: GA={judgment['scores']['geometric_accuracy']}/4, "
              f"LA={judgment['scores']['lesson_alignment']}/4, "
              f"LC={judgment['scores']['linguistic_clarity']}/4")
        print(f"  Issues: {len(judgment['specific_issues'])}")
        print(f"  Saved to {out_path.relative_to(ROOT)}")

        results.append({"file": txt_path.name, "judgment": judgment})

    return results


# ---------------------------------------------------------------------
# CLI entry point
# ---------------------------------------------------------------------

def main() -> None:
    import argparse

    parser = argparse.ArgumentParser(description="Pipeline 2: Opus-as-judge for NL geometry problems.")
    parser.add_argument(
        "--problem",
        type=Path,
        default=None,
        help="Path to a single NL problem .txt file. If omitted, runs batch mode.",
    )
    parser.add_argument(
        "--lesson-id",
        type=str,
        default=None,
        help="Lesson id (e.g. lesson_03). Required if --problem is provided.",
    )
    parser.add_argument(
        "--problems-dir",
        type=Path,
        default=ROOT / "outputs",
        help="Directory containing NL problem files (batch mode).",
    )
    parser.add_argument(
        "--lessons-dir",
        type=Path,
        default=ROOT / "lessons",
        help="Directory containing lesson source files.",
    )
    parser.add_argument(
        "--output-dir",
        type=Path,
        default=ROOT / "judgments",
        help="Where to write judgment JSON files.",
    )
    parser.add_argument(
        "--model",
        type=str,
        default="claude-opus-4-7",
        help="Anthropic model id for the judge.",
    )
    args = parser.parse_args()

    if not os.getenv("ANTHROPIC_API_KEY"):
        sys.exit("ANTHROPIC_API_KEY is not set. Add it to .env in the repo root.")

    if args.problem:
        if not args.lesson_id:
            sys.exit("--lesson-id is required when --problem is given.")
        nl = args.problem.read_text(encoding="utf-8")
        lesson_path = args.lessons_dir / f"{args.lesson_id}.txt"
        if not lesson_path.exists():
            sys.exit(f"Lesson file not found: {lesson_path}")
        lesson_text = lesson_path.read_text(encoding="utf-8")
        judgment = judge_problem(nl, lesson_text, args.lesson_id, model=args.model)
        print(json.dumps(judgment, indent=2))
    else:
        judge_directory(args.problems_dir, args.lessons_dir, args.output_dir, model=args.model)


if __name__ == "__main__":
    main()