"""
Haiku prose layer: polish function-translated NL into student-facing wording.

Takes deterministic NL from schema_to_text.schema_to_problem_text plus lesson
source material (same files as evaluate_schema.py) and returns revised prose
that preserves all mathematical content.

Standalone:
  python3 pipelines/prose_nl.py --validated-dir validated
  python3 pipelines/prose_nl.py --problem validated/schema_L16_P001_refined.txt --lesson-id lesson_16
"""

from __future__ import annotations

import argparse
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

from schema_to_text import schema_to_problem_text  # noqa: E402

load_dotenv(ROOT / ".env")

client = anthropic.Anthropic(api_key=os.getenv("ANTHROPIC_API_KEY"))

DEFAULT_HAIKU = "claude-haiku-4-5-20251001"
LESSONS_DIR = ROOT / "lessons"
VALIDATED_DIR = ROOT / "validated"

SYSTEM_PROMPT = """You are an expert Geometry curriculum writer. You turn a correct but mechanical, \
list-like math problem into one that reads naturally and engages a student — without \
touching the mathematics.

You will receive:
1. A function-translated natural-language problem (correct, but stiff and list-like).
2. The lesson content the problem belongs to.

HOW TO THINK ABOUT THE MATH
The mathematical content has already been verified by a separate system. Every number, \
label, relationship, and the target question are correct and final. You do not need to \
check, protect, or second-guess the math — treat every quantity as locked and simply \
carry it through unchanged. This frees you to focus entirely on how the problem reads.

YOUR PRIMARY JOB: ADD CONTEXT AND FLOW
The input reads like a list of asserted facts. Your job is to transform it into clear, \
motivated prose — and, in nearly every case, to wrap it in a concrete real-world \
scenario that gives the quantities a reason to exist. A real-world frame is the default, \
not the exception. Reach for one first; only fall back to plain (still flowing) prose \
when a scenario would genuinely mislead the student about the math (see THE FALLBACK).

- Use the lesson content as a seed for the *kind* of scenario (e.g. if the lesson frames \
  dilation through scale drawings, blueprints, maps, or shadows, draw your context from \
  that world). The lesson is your source of natural framing — mine it for context.
- Attach real-world nouns to the figures and quantities. "Triangle ABC with AB = 10" can \
  become "a triangular garden plot ABC whose side AB measures 10 meters" — the label ABC \
  and the value 10 are preserved, but now they mean something.
- Replace the "Let X be… Let Y be…" scaffolding with connected sentences that flow.
- PUT THE QUESTION INSIDE THE SCENARIO. The final ask is the part that most often stays \
  flat. Don't end on a bare "Find the length of DE." Make the question itself part of the \
  story: "How long should she cut the support cable?" / "What length of fencing does the \
  longest side need?" / "How tall is the flagpole?" The thing being solved for should \
  have a reason someone in the scenario cares about it.
- For multi-part problems (parts a, b, c…), keep every part and its order, but let the \
  scenario carry through all of them so the parts feel like one investigation, not a \
  list. A proof can still live in a real setting — the people in the scenario are \
  reasoning about why something must be true.

THE ONE BOUNDARY (this is the only hard rule)
Preserve every quantity and relationship exactly. Specifically:
- Every number, unit, label/letter, angle, length, and named relationship must appear, \
  unchanged in value and meaning.
- The target question must ask for exactly the same thing (you may dress *how* it is \
  asked in scenario language, but not *what* is asked).
- Do not add a new number, measurement, relationship, or constraint that wasn't in the \
  input. Do not remove one either.
You may freely add narrative, nouns, and setting around those quantities — you may not \
add, drop, or alter the quantities themselves. A real-world wrapper is encouraged *as \
long as it carries the identical quantities*. The four examples below all do exactly \
this: every number and label in the input survives unchanged in the output.

THE FALLBACK (use sparingly)
Skip the real-world scenario ONLY when wrapping the problem would distort the math — for \
example, a pure existence proof or an abstract classification where inventing a physical \
story would imply measurements or stakes that aren't really there. Even then, do NOT \
write a bare list: write clean, flowing, motivated prose with connected sentences. The \
fallback is "no gimmick," not "no craft." Treat the fallback as the rare case, not the \
safe default — most similarity, dilation, right-triangle, and measurement problems have \
an honest real-world home.

WHAT NOT TO DO
- Do NOT check or 'improve' lesson alignment, and do NOT judge whether the problem fits \
  the lesson's difficulty. That is handled elsewhere. Your only use of the lesson is as \
  a source of natural context.
- Do NOT withhold or hide information to avoid 'giving away the method'. If the input \
  states a scale factor, a similarity, or congruent angles, keep them stated. Removing \
  such details to make the problem 'harder' corrupts it — never do this.
- Do NOT force a scenario so hard that it becomes absurd or self-contradictory. A good \
  wrapper feels like a real reason these numbers exist; a bad one staples "a baker" onto \
  a triangle for no reason. If the obvious scenario feels silly, pick a better one — the \
  answer is a *better* context, not *no* context.

OUTPUT
Return only the revised student-facing problem. No commentary, labels, bullets, or JSON.

Before answering, silently verify:
1. Does every number, label, angle, length, relationship, and the target question from \
   the input appear, unchanged, in my version?
2. Did I add zero new quantities and remove none?
3. Does it read as natural, connected prose — not a list of asserted facts?
4. Did I default to a real-world scenario, and does the scenario carry the exact same \
   quantities? If I used the fallback, was that genuinely necessary, and is the prose \
   still vivid and flowing?
5. Is the final question itself inside the scenario (someone has a reason to want it), \
   rather than a bare "find X"?
6. Would a Geometry student read it once and know exactly what is being asked?
If any check fails, revise before giving the final problem.

=====================================================================
WORKED EXAMPLES
The four below span the range you will see: an easy-to-frame dilation, a right-triangle
measurement, a multi-part similarity proof (a proof CAN have a real setting), and a
genuinely abstract classification (the fallback done well). Study how each preserves
every quantity while giving the problem a reason to exist — and how each ends on a
question someone in the scenario would actually ask.
=====================================================================

--- Example 1 — dilation (real-world framing) ---

Input (function-translated):
Let triangle ABC be a triangle with sides AB = 10, BC = 15, AC = 12. Let triangle DEF
be a triangle. ABC is dilated to form DEF with scale factor 2.5, centered at point P.
Find the length of DE in DEF.

Revised (student-facing):
A landscape architect sketches a triangular garden bed ABC on her plan, with sides
AB = 10 feet, BC = 15 feet, and AC = 12 feet. To build a larger version for the public
park, she enlarges the design from a fixed anchor stake P using a scale factor of 2.5,
producing the full-size bed DEF. When she orders edging for the side DE, how many feet
should she ask for?

--- Example 2 — right triangle, find a side (real-world framing) ---

Input (function-translated):
Let triangle PQR be a right triangle with sides PQ = 12, QR = 9, where the right angle is
at Q. Find the length of PR in PQR.

Revised (student-facing):
A carpenter is bracing a rectangular gate with a single diagonal board, forming a right
triangle PQR. The two sides meeting at the square corner Q measure PQ = 12 inches and
QR = 9 inches. The diagonal brace runs along PR, the side opposite the right angle. How
long should the carpenter cut the diagonal brace PR?

--- Example 3 — multi-part similarity / geometric-mean proof (a proof in a real setting) ---

Input (function-translated):
Let triangle ABC be a right triangle with legs AC = 5, BC = 12, right angle at C. Let CD
be an altitude perpendicular to hypotenuse AB, meeting it at D, dividing AB into AD and
DB. Triangle ABC is similar to triangle ACD by AA. Triangle ABC is similar to triangle
BCD by AA. AC is the geometric mean of AB and AD. BC is the geometric mean of AB and DB.
(a) Explain why ABC ~ ACD and ABC ~ BCD by AA. (b) From ABC ~ ACD show AC^2 = AD * AB.
(c) From ABC ~ BCD show BC^2 = DB * AB. (d) Add the results to prove AB^2 = AC^2 + BC^2.
(e) Find the length of AB.

Revised (student-facing):
An engineer is checking the design of a triangular roof truss ABC that meets at a square
corner at the peak C, with the two rafters measuring AC = 5 meters and BC = 12 meters. A
vertical support post CD drops straight down from the peak, meeting the base beam AB at a
right angle at point D and splitting the base into the two segments AD and DB.

The post creates two smaller right triangles inside the truss, ACD and BCD.

(a) Explain why triangle ABC is similar to triangle ACD, and why triangle ABC is similar
to triangle BCD, using the Angle-Angle Similarity Theorem.
(b) Using the similarity of ABC and ACD, write a proportion between corresponding sides
and use it to show that AC^2 = AD * AB.
(c) Using the similarity of ABC and BCD, do the same to show that BC^2 = DB * AB.
(d) Add your two equations from (b) and (c), and use the fact that AD + DB = AB, to prove
that AB^2 = AC^2 + BC^2 — the relationship the engineer relies on.
(e) Find the length of the base beam AB.

--- Example 4 — abstract classification (the fallback, done well) ---

Input (function-translated):
Let triangle XYZ be a triangle with sides XY = 7, YZ = 24, XZ = 25. Determine whether
triangle XYZ is right, acute, or obtuse.

Revised (student-facing):
Triangle XYZ has side lengths XY = 7, YZ = 24, and XZ = 25. Without measuring any of its
angles, decide whether triangle XYZ is right, acute, or obtuse, and justify your
conclusion from the side lengths alone.
"""


def _build_user_prompt(function_translated_nl: str, lesson_text: str) -> str:
    return f"""Inputs:

Function-translated problem:
{function_translated_nl.strip()}

Associated lesson content:
{lesson_text.strip()}"""


def normalize_lesson_id(lesson_id: str) -> str:
    """Map '06', 'lesson_6', etc. to canonical 'lesson_06'."""
    lesson_id = lesson_id.strip()
    if re.fullmatch(r"\d+", lesson_id):
        return f"lesson_{int(lesson_id):02d}"
    m = re.search(r"lesson_(\d+)", lesson_id, re.IGNORECASE)
    if m:
        return f"lesson_{int(m.group(1)):02d}"
    return lesson_id


def load_lesson_text(lesson_id: str, lessons_dir: Path = LESSONS_DIR) -> str:
    """Load full lesson source text (e.g. lesson_03 from lessons/lesson_03.txt)."""
    lesson_id = normalize_lesson_id(lesson_id)
    lesson_path = lessons_dir / f"{lesson_id}.txt"
    if not lesson_path.exists():
        raise FileNotFoundError(f"Lesson file not found: {lesson_path}")
    return lesson_path.read_text(encoding="utf-8")


def prose_with_haiku(
    function_translated_nl: str,
    lesson_text: str,
    *,
    model: str = DEFAULT_HAIKU,
) -> str:
    """Revise function-translated NL into student-facing prose via Haiku."""
    message = client.messages.create(
        model=model,
        max_tokens=1500,
        system=SYSTEM_PROMPT,
        messages=[{"role": "user", "content": _build_user_prompt(function_translated_nl, lesson_text)}],
    )

    parts: list[str] = []
    for block in message.content:
        if block.type == "text":
            parts.append(block.text)
    prose = "\n".join(parts).strip()
    if not prose:
        raise RuntimeError("Haiku returned empty prose.")
    return prose


def prose_from_schema(
    schema_data: dict[str, Any],
    lesson_id: str,
    *,
    lessons_dir: Path = LESSONS_DIR,
    model: str = DEFAULT_HAIKU,
) -> tuple[str, str]:
    """
    Function-translate schema → NL, then Haiku prose layer.

    Returns (function_translated_nl, student_facing_prose).
    """
    function_translated = schema_to_problem_text(schema_data)
    lesson_text = load_lesson_text(normalize_lesson_id(lesson_id), lessons_dir)
    prose = prose_with_haiku(function_translated, lesson_text, model=model)
    return function_translated, prose


def _lesson_id_from_stem(stem: str) -> str | None:
    """schema_L16_P001_refined or schema_lesson_03_001 → lesson id."""
    m = re.search(r"lesson_(\d+)", stem, re.IGNORECASE)
    if m:
        return f"lesson_{m.group(1).zfill(2)}"
    m = re.search(r"_L(\d+)_", stem, re.IGNORECASE)
    if m:
        return f"lesson_{m.group(1).zfill(2)}"
    return None


def prose_one_validated_file(
    validated_path: Path,
    *,
    lesson_id: str | None = None,
    lessons_dir: Path = LESSONS_DIR,
    model: str = DEFAULT_HAIKU,
    schema_path: Path | None = None,
) -> str:
    """
    Run prose layer on one validated artifact.

    Uses function-translated NL from the sibling .json schema when present;
    otherwise reads the .txt as the function-translated input.
    """
    stem = validated_path.stem.removesuffix("_refined")
    resolved_lesson = lesson_id or _lesson_id_from_stem(validated_path.stem)
    if not resolved_lesson:
        raise ValueError(f"Could not determine lesson id for {validated_path.name}")

    json_path = schema_path or validated_path.with_name(f"{stem}_refined.json")
    if json_path.exists():
        schema_data = json.loads(json_path.read_text(encoding="utf-8"))
        function_translated = schema_to_problem_text(schema_data)
    else:
        function_translated = validated_path.read_text(encoding="utf-8")

    lesson_text = load_lesson_text(resolved_lesson, lessons_dir)
    return prose_with_haiku(function_translated, lesson_text, model=model)


def prose_directory(
    validated_dir: Path,
    *,
    lessons_dir: Path = LESSONS_DIR,
    model: str = DEFAULT_HAIKU,
) -> list[dict[str, str]]:
    """Apply Haiku prose to every schema_*_refined.json under validated_dir."""
    paths = sorted(validated_dir.glob("schema_*_refined.json"))
    if not paths:
        print(f"No schema_*_refined.json files under {validated_dir}")
        return []

    results: list[dict[str, str]] = []
    for json_path in paths:
        stem = json_path.stem  # schema_L16_P001_refined
        txt_path = json_path.with_suffix(".txt")
        try:
            schema_data = json.loads(json_path.read_text(encoding="utf-8"))
            lesson_id = schema_data.get("lesson") or _lesson_id_from_stem(stem)
            if not lesson_id:
                print(f"Skipping {json_path.name} — no lesson id.")
                continue
            function_translated, prose = prose_from_schema(
                schema_data, lesson_id, lessons_dir=lessons_dir, model=model
            )
            txt_path.write_text(prose, encoding="utf-8")
            print(f"  Wrote {txt_path.relative_to(ROOT)}")
            results.append(
                {
                    "json": json_path.name,
                    "txt": txt_path.name,
                    "lesson_id": lesson_id,
                    "function_translated_nl": function_translated,
                    "prose": prose,
                }
            )
        except Exception as exc:
            print(f"Skipping {json_path.name} — {exc}")

    print(f"\nProse complete: {len(results)}/{len(paths)} file(s)")
    return results


def main() -> None:
    parser = argparse.ArgumentParser(
        description="Haiku prose layer for function-translated geometry NL problems."
    )
    parser.add_argument(
        "--problem",
        type=Path,
        default=None,
        help="Single validated .txt or .json path. Writes/overwrites sibling .txt.",
    )
    parser.add_argument(
        "--validated-dir",
        type=Path,
        default=VALIDATED_DIR,
        help="Batch mode: all schema_*_refined.json in this directory.",
    )
    parser.add_argument(
        "--lesson-id",
        type=str,
        default=None,
        help="Lesson id (e.g. lesson_16). Required for --problem if stem has no lesson.",
    )
    parser.add_argument(
        "--lessons-dir",
        type=Path,
        default=LESSONS_DIR,
        help="Directory containing lesson source files.",
    )
    parser.add_argument(
        "--haiku-model",
        type=str,
        default=DEFAULT_HAIKU,
        help="Anthropic model for prose revision.",
    )
    args = parser.parse_args()

    if not os.getenv("ANTHROPIC_API_KEY"):
        sys.exit("ANTHROPIC_API_KEY is not set. Add it to .env in the repo root.")

    if args.problem:
        path = args.problem.resolve()
        if not path.exists():
            sys.exit(f"File not found: {path}")
        if path.suffix == ".json":
            schema_data = json.loads(path.read_text(encoding="utf-8"))
            lesson_id = args.lesson_id or schema_data.get("lesson")
            if not lesson_id:
                sys.exit("--lesson-id is required when lesson cannot be inferred.")
            function_translated, prose = prose_from_schema(
                schema_data,
                lesson_id,
                lessons_dir=args.lessons_dir,
                model=args.haiku_model,
            )
            txt_path = path.with_suffix(".txt")
        else:
            prose = prose_one_validated_file(
                path,
                lesson_id=args.lesson_id,
                lessons_dir=args.lessons_dir,
                model=args.haiku_model,
            )
            txt_path = path
        txt_path.write_text(prose, encoding="utf-8")
        print(f"Wrote {txt_path.relative_to(ROOT)}")
    else:
        prose_directory(
            args.validated_dir,
            lessons_dir=args.lessons_dir,
            model=args.haiku_model,
        )


if __name__ == "__main__":
    main()
