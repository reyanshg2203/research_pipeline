"""
Geometry evaluator survey — four-round comparison across pipeline variants.

Round 1  Haiku baseline: generate_schema → schema_to_text (outputs_pipeline1_v1_frozen/)
Round 2  Opus-judge loop:  baseline NL → refine_nl (refined/)
Round 3  Schema repair:    two versions of validated schema (validated/)
Round 4  Rate Version B variants marked faithful in Round 3

Run: streamlit run pipelines/app.py
"""

from __future__ import annotations

import json
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path

import pandas as pd
import streamlit as st

ROOT = Path(__file__).resolve().parent.parent
OUTPUTS_DIR = ROOT / "outputs"
FROZEN_DIR = ROOT / "outputs_pipeline1_v1_frozen"
REFINED_DIR = ROOT / "refined"
VALIDATED_DIR = ROOT / "validated"
RESPONSES_DIR = ROOT / "pipelines" / "survey_responses"
RESPONSES_CSV = RESPONSES_DIR / "evaluator_responses.csv"
RESPONSES_JSONL = RESPONSES_DIR / "evaluator_responses.jsonl"
DRAFTS_DIR = RESPONSES_DIR / "drafts"

LESSON_IDS = [
    "lesson_01",
    "lesson_03",
    "lesson_05",
    "lesson_06",
    "lesson_08",
    "lesson_09",
    "lesson_10",
    "lesson_14",
    "lesson_15",
    "lesson_16",
]

RUBRIC_DIMENSIONS = [
    ("geometric_accuracy", "Geometric Accuracy"),
    ("lesson_alignment", "Lesson Alignment"),
    ("linguistic_clarity", "Linguistic Clarity"),
]

SCORE_OPTIONS = list(range(5))


@dataclass
class SurveyProblem:
    lesson_id: str
    lesson_num: str
    problem_id: str
    schema_stem: str
    part1_baseline: str | None
    part2_refined_nl: str | None
    part3_functional: str | None
    part3_prose: str | None
    part1_missing: str | None = None
    part2_missing: str | None = None
    part3_missing: str | None = None


def _lesson_num(lesson_id: str) -> str:
    return lesson_id.replace("lesson_", "")


def _read_text(path: Path) -> str | None:
    if path.is_file():
        text = path.read_text(encoding="utf-8").strip()
        return text or None
    return None


def _functional_from_trace(problem_id: str) -> str | None:
    trace_path = VALIDATED_DIR / f"schema_{problem_id}_refined_trace.json"
    if not trace_path.is_file():
        return None
    try:
        trace = json.loads(trace_path.read_text(encoding="utf-8"))
    except json.JSONDecodeError:
        return None
    text = (trace.get("function_translated_nl") or "").strip()
    return text or None


def _problem_id_for_lesson(lesson_id: str) -> tuple[str, str] | None:
    """Return (problem_id, schema_stem) from outputs_pipeline1_v1_frozen/schema_lesson_XX_001.json."""
    stem = f"schema_{lesson_id}_001"
    schema_path = FROZEN_DIR / f"{stem}.json"
    if not schema_path.is_file():
        return None
    try:
        data = json.loads(schema_path.read_text(encoding="utf-8"))
    except json.JSONDecodeError:
        return None
    problem_id = data.get("problem_id")
    if not problem_id:
        return None
    return problem_id, stem


def _load_part3_pair(problem_id: str) -> tuple[str | None, str | None, str | None]:
    functional = _read_text(VALIDATED_DIR / f"schema_{problem_id}_functional.txt")
    prose = _read_text(VALIDATED_DIR / f"schema_{problem_id}_refined.txt")

    if functional is None:
        functional = _functional_from_trace(problem_id)
    if functional is None:
        functional = _read_text(VALIDATED_DIR / f"schema_{problem_id}_refined.txt")

    missing_parts: list[str] = []
    if functional is None:
        missing_parts.append("Version A")
    if prose is None:
        missing_parts.append("Version B")
    if functional and prose and functional == prose:
        missing_parts.append(
            "distinct Version A vs Version B texts (re-run refine_schema with prose enabled)"
        )

    missing = ", ".join(missing_parts) if missing_parts else None
    return functional, prose, missing


def load_survey_problems() -> list[SurveyProblem]:
    problems: list[SurveyProblem] = []
    for lesson_id in LESSON_IDS:
        lesson_num = _lesson_num(lesson_id)
        meta = _problem_id_for_lesson(lesson_id)
        if meta is None:
            problems.append(
                SurveyProblem(
                    lesson_id=lesson_id,
                    lesson_num=lesson_num,
                    problem_id="",
                    schema_stem=f"schema_{lesson_id}_001",
                    part1_baseline=None,
                    part2_refined_nl=None,
                    part3_functional=None,
                    part3_prose=None,
                    part1_missing=f"missing {FROZEN_DIR.name}/schema_{lesson_id}_001.txt",
                    part2_missing=f"missing {REFINED_DIR.name}/schema_{lesson_id}_001_refined.txt",
                    part3_missing=f"missing validated outputs for {lesson_id}",
                )
            )
            continue

        problem_id, schema_stem = meta
        part1 = _read_text(FROZEN_DIR / f"{schema_stem}.txt")
        part2 = _read_text(REFINED_DIR / f"{schema_stem}_refined.txt")
        part3_functional, part3_prose, part3_missing = _load_part3_pair(problem_id)

        problems.append(
            SurveyProblem(
                lesson_id=lesson_id,
                lesson_num=lesson_num,
                problem_id=problem_id,
                schema_stem=schema_stem,
                part1_baseline=part1,
                part2_refined_nl=part2,
                part3_functional=part3_functional,
                part3_prose=part3_prose,
                part1_missing=None if part1 else f"missing {FROZEN_DIR.name}/{schema_stem}.txt",
                part2_missing=None
                if part2
                else f"missing {REFINED_DIR.name}/{schema_stem}_refined.txt",
                part3_missing=part3_missing,
            )
        )
    return problems


# ---------------------------------------------------------------------------
# Draft persistence
# ---------------------------------------------------------------------------

def _draft_path(evaluator_email: str) -> Path:
    safe = evaluator_email.replace("@", "_at_").replace(".", "_")
    return DRAFTS_DIR / f"{safe}_draft.json"


def save_draft(evaluator_email: str, state: dict) -> None:
    DRAFTS_DIR.mkdir(parents=True, exist_ok=True)
    _draft_path(evaluator_email).write_text(
        json.dumps(state, default=str), encoding="utf-8"
    )


def load_draft(evaluator_email: str) -> dict | None:
    path = _draft_path(evaluator_email)
    if path.is_file():
        try:
            return json.loads(path.read_text(encoding="utf-8"))
        except json.JSONDecodeError:
            return None
    return None


def delete_draft(evaluator_email: str) -> None:
    path = _draft_path(evaluator_email)
    if path.is_file():
        path.unlink()


# ---------------------------------------------------------------------------
# UI helpers
# ---------------------------------------------------------------------------

def _score_selectbox(label: str, key: str, default: int = 0) -> int:
    return st.selectbox(
        label,
        options=SCORE_OPTIONS,
        index=default,
        format_func=lambda n: f"{n}",
        key=key,
    )


def _render_problem_text(text: str) -> None:
    with st.container(border=True):
        st.markdown(text)


def _render_rubric_block(prefix: str, lesson_id: str, saved: dict | None = None) -> dict[str, int]:
    scores: dict[str, int] = {}
    cols = st.columns(3)
    for col, (field, label) in zip(cols, RUBRIC_DIMENSIONS):
        with col:
            default = int(saved.get(field, 0)) if saved else 0
            scores[field] = _score_selectbox(
                label,
                key=f"{prefix}_{lesson_id}_{field}",
                default=default,
            )
    return scores


def _readiness(problems: list[SurveyProblem]) -> dict[str, int]:
    return {
        "part1": sum(1 for p in problems if p.part1_baseline),
        "part2": sum(1 for p in problems if p.part2_refined_nl),
        "part3": sum(
            1
            for p in problems
            if p.part3_functional and p.part3_prose and p.part3_functional != p.part3_prose
        ),
    }


def _save_response(payload: dict) -> None:
    RESPONSES_DIR.mkdir(parents=True, exist_ok=True)
    flat = {
        "submitted_at": payload["submitted_at"],
        "evaluator_name": payload.get("evaluator_name", ""),
        "evaluator_email": payload.get("evaluator_email", ""),
    }
    for part_key in ("part1", "part2", "part3", "part4"):
        for lesson_id, entry in payload.get(part_key, {}).items():
            for k, v in entry.items():
                flat[f"{part_key}_{lesson_id}_{k}"] = v

    row = pd.DataFrame([flat])
    if RESPONSES_CSV.is_file():
        existing = pd.read_csv(RESPONSES_CSV)
        updated = pd.concat([existing, row], ignore_index=True)
    else:
        updated = row
    updated.to_csv(RESPONSES_CSV, index=False)

    with RESPONSES_JSONL.open("a", encoding="utf-8") as f:
        f.write(json.dumps(payload) + "\n")


def _render_sidebar(problems: list[SurveyProblem]) -> None:
    ready = _readiness(problems)
    st.sidebar.header("Survey materials")
    st.sidebar.markdown(
        f"- **Round 1**: {ready['part1']}/10\n"
        f"- **Round 2**: {ready['part2']}/10\n"
        f"- **Round 3**: {ready['part3']}/10"
    )
    with st.sidebar.expander("Missing files"):
        for p in problems:
            notes = [n for n in (p.part1_missing, p.part2_missing, p.part3_missing) if n]
            if notes:
                st.markdown(f"**{p.lesson_id}**")
                for note in notes:
                    st.caption(note)


# ---------------------------------------------------------------------------
# Survey rendering
# ---------------------------------------------------------------------------

def _render_parts_1_to_3(problems: list[SurveyProblem], draft: dict) -> dict | None:
    part1: dict[str, dict] = {}
    part2: dict[str, dict] = {}
    part3: dict[str, dict] = {}

    # ── Round 1 ──────────────────────────────────────────────────────────────
    st.header("Round 1")
    for p in problems:
        with st.expander(f"Problem {p.lesson_num}", expanded=False):
            if p.part1_baseline:
                _render_problem_text(p.part1_baseline)
                saved = draft.get("part1", {}).get(p.lesson_id)
                scores = _render_rubric_block("p1", p.lesson_id, saved)
                part1[p.lesson_id] = scores
            else:
                st.warning("Problem not yet available.")

    # auto-save draft after Round 1 widgets render
    _maybe_save_draft(part1, part2, part3)

    st.divider()

    # ── Round 2 ──────────────────────────────────────────────────────────────
    st.header("Round 2")
    for p in problems:
        with st.expander(f"Problem {p.lesson_num}", expanded=False):
            if p.part2_refined_nl:
                _render_problem_text(p.part2_refined_nl)
                saved = draft.get("part2", {}).get(p.lesson_id)
                scores = _render_rubric_block("p2", p.lesson_id, saved)
                part2[p.lesson_id] = scores
            else:
                st.warning("Problem not yet available.")

    _maybe_save_draft(part1, part2, part3)

    st.divider()

    # ── Round 3 ──────────────────────────────────────────────────────────────
    st.header("Round 3")
    st.caption(
        "Each problem appears in two versions. Rate each version independently, "
        "then indicate whether Version B preserves the same mathematical content as Version A."
    )
    for p in problems:
        with st.expander(f"Problem {p.lesson_num}", expanded=False):
            if p.part3_functional and p.part3_prose and p.part3_functional != p.part3_prose:
                saved_p3 = draft.get("part3", {}).get(p.lesson_id, {})

                st.markdown("**Version A**")
                _render_problem_text(p.part3_functional)

                st.markdown("**Version B**")
                _render_problem_text(p.part3_prose)

                faithful_default = saved_p3.get("faithful", "yes")
                faithful = st.radio(
                    "Does Version B preserve the mathematical content of Version A?",
                    options=["yes", "no"],
                    index=0 if faithful_default == "yes" else 1,
                    horizontal=True,
                    key=f"p3_faithful_{p.lesson_id}",
                )
                part3[p.lesson_id] = {
                    "problem_id": p.problem_id,
                    "faithful": faithful,
                }
            else:
                st.warning("Problem not yet available.")

    _maybe_save_draft(part1, part2, part3)

    if st.button("Continue to Round 4", type="primary"):
        required_p1 = {p.lesson_id for p in problems if p.part1_baseline}
        required_p2 = {p.lesson_id for p in problems if p.part2_refined_nl}
        missing_ratings = []
        for lid in required_p1:
            if lid not in part1:
                missing_ratings.append(f"Round 1 ratings for problem {_lesson_num(lid)}")
        for lid in required_p2:
            if lid not in part2:
                missing_ratings.append(f"Round 2 ratings for problem {_lesson_num(lid)}")
        if missing_ratings:
            st.error(
                "Please rate every available problem before continuing:\n- "
                + "\n- ".join(missing_ratings)
            )
            return None

        return {
            "evaluator_name": st.session_state.get("evaluator_name", ""),
            "evaluator_email": st.session_state.get("evaluator_email", ""),
            "part1": part1,
            "part2": part2,
            "part3": part3,
        }
    return None


def _maybe_save_draft(part1: dict, part2: dict, part3: dict) -> None:
    email = st.session_state.get("evaluator_email", "").strip()
    if not email:
        return
    save_draft(email, {
        "evaluator_name": st.session_state.get("evaluator_name", ""),
        "evaluator_email": email,
        "survey_step": st.session_state.get("survey_step", "parts_1_3"),
        "part1": part1,
        "part2": part2,
        "part3": part3,
    })


def _lesson_num(lesson_id: str) -> str:
    return lesson_id.replace("lesson_", "")


def _render_part_4(problems: list[SurveyProblem], prior: dict) -> None:
    faithful_lessons = [
        lid for lid, entry in prior.get("part3", {}).items() if entry.get("faithful") == "yes"
    ]

    st.header("Round 4")
    if not faithful_lessons:
        st.info("No problems were marked as faithful in Round 3. Submit to finish the survey.")
    else:
        st.caption(
            f"Rate the {len(faithful_lessons)} Version B problem(s) you marked as "
            "mathematically faithful in Round 3."
        )

    part4: dict[str, dict] = {}
    problem_by_lesson = {p.lesson_id: p for p in problems}
    for lesson_id in faithful_lessons:
        p = problem_by_lesson[lesson_id]
        with st.expander(f"Problem {p.lesson_num}", expanded=False):
            if p.part3_prose:
                _render_problem_text(p.part3_prose)
                part4[lesson_id] = {
                    "problem_id": p.problem_id,
                    **_render_rubric_block("p4", lesson_id),
                }
            else:
                st.warning("Problem not yet available.")

    if st.button("Submit survey", type="primary"):
        if faithful_lessons:
            missing = [lid for lid in faithful_lessons if lid not in part4]
            if missing:
                st.error("Please rate every problem shown above before submitting.")
                return

        payload = {
            "submitted_at": datetime.now(timezone.utc).isoformat(),
            "evaluator_name": prior.get("evaluator_name", ""),
            "evaluator_email": prior.get("evaluator_email", ""),
            "part1": prior.get("part1", {}),
            "part2": prior.get("part2", {}),
            "part3": prior.get("part3", {}),
            "part4": part4,
        }
        _save_response(payload)
        delete_draft(prior.get("evaluator_email", ""))
        st.session_state.survey_step = "done"
        st.session_state.survey_payload = payload
        st.success("Survey submitted. Thank you!")
        st.rerun()


# ---------------------------------------------------------------------------
# Main
# ---------------------------------------------------------------------------

def main() -> None:
    st.set_page_config(
        page_title="Geometry Problem Evaluation",
        page_icon="📐",
        layout="wide",
    )

    if "survey_step" not in st.session_state:
        st.session_state.survey_step = "intro"
    if "parts_1_3" not in st.session_state:
        st.session_state.parts_1_3 = None

    problems = load_survey_problems()
    _render_sidebar(problems)

    st.title("Geometry Problem Evaluation")
    st.markdown(
        "You will review geometry problems across four rounds. "
        "Rate each problem 0–4 on geometric accuracy, lesson alignment, and linguistic clarity. "
        "Your progress is saved automatically — you can close this tab and return at any time."
    )

    if st.session_state.survey_step == "done":
        st.success("Your responses have been recorded. Thank you!")
        if st.button("Start a new response"):
            st.session_state.survey_step = "intro"
            st.session_state.parts_1_3 = None
            st.rerun()
        return

    if st.session_state.survey_step == "intro":
        st.subheader("Before you begin")
        name = st.text_input("Name")
        email = st.text_input("Email")

        if name:
            st.session_state.evaluator_name = name
        if email:
            st.session_state.evaluator_email = email

        # Check for existing draft
        if email:
            draft = load_draft(email)
            if draft:
                st.info(
                    "A saved draft was found for this email. "
                    "Click **Resume** to pick up where you left off, or **Start over** to begin fresh."
                )
                col1, col2 = st.columns(2)
                with col1:
                    if st.button("Resume", type="primary"):
                        st.session_state.evaluator_name = draft.get("evaluator_name", name)
                        st.session_state.evaluator_email = email
                        st.session_state.survey_step = draft.get("survey_step", "parts_1_3")
                        st.rerun()
                with col2:
                    if st.button("Start over"):
                        delete_draft(email)
                        st.session_state.survey_step = "parts_1_3"
                        st.rerun()
                return

        if st.button("Begin", type="primary", disabled=not (name and email)):
            st.session_state.survey_step = "parts_1_3"
            st.rerun()
        return

    email = st.session_state.get("evaluator_email", "")
    draft = load_draft(email) or {}

    if st.session_state.survey_step == "parts_1_3":
        prior = _render_parts_1_to_3(problems, draft)
        if prior is not None:
            st.session_state.parts_1_3 = prior
            st.session_state.survey_step = "part_4"
            if email:
                save_draft(email, {**draft, "survey_step": "part_4"})
            st.rerun()
        return

    if st.session_state.survey_step == "part_4":
        if st.session_state.parts_1_3 is None:
            st.session_state.survey_step = "parts_1_3"
            st.rerun()
            return
        _render_part_4(problems, st.session_state.parts_1_3)


if __name__ == "__main__":
    main()