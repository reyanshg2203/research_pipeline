"""
Rater calibration survey — 10 problems, used to establish inter-rater reliability
and to surface rubric disagreements BEFORE the main 90-problem study.

Completely separate from app.py: its own problem file and its own response folder.
Nothing here can touch the main survey's data.

Run: streamlit run pipelines/app_calibration.py
"""
from __future__ import annotations

import json
from datetime import datetime, timezone
from pathlib import Path

import streamlit as st

import storage

ROOT = Path(__file__).resolve().parent.parent
PROBLEMS_PATH = ROOT / "pipelines" / "survey_data" / "calibration_problems.json"
SCOPE = "cal"

RUBRIC = [
    ("geometric_accuracy", "Geometric Accuracy", "50%",
     "Are the relationships mathematically correct, consistent, and solvable?"),
    ("lesson_alignment", "Lesson Alignment", "30%",
     "Does it target the lesson's skill at an appropriate difficulty?"),
    ("linguistic_clarity", "Linguistic Clarity", "20%",
     "Is the wording unambiguous, clear, and with a fresh, engaging context?"),
]

ANCHORS = {
    "geometric_accuracy": {
        4: "All geometric relationships within the problem are mathematically correct and consistent.",
        3: "All major relationships are correct, but there's a slight caveat that affects determinability.",
        2: "One major relationship is incorrect; the problem seems fine but one part throws you off.",
        1: "Multiple major problem violations exist. Relationships are misleading or inconsistent.",
        0: "Problem is completely nonsensical / makes no sense. The answer is stated in the problem.",
    },
    "lesson_alignment": {
        4: "Integrates a supporting lesson concept, ideally with two or more solution steps.",
        3: "Appropriately challenging and almost aligned to the lesson, but one part is wrong (in alignment or correctness).",
        2: "Targets a related but imprecise skill; the problem is trivially easy or too difficult.",
        1: "The problem is related, but requires a skill beyond the current scope.",
        0: "Wrong skill, completely off topic.",
    },
    "linguistic_clarity": {
        4: "The problem is concise and clear. A fresh, engaging context is included.",
        3: "Clear, but the problem lacks context and is boring / blocky.",
        2: "Unambiguous, but facts are stated that are trivially true or repetitive.",
        1: "Decipherable with effort but contains ambiguous phrasing.",
        0: "Broken grammar, missing information, or contradictory constraints make the problem unsolvable as written.",
    },
}

# Task directions, shown on the intro (teacher app) and consent (Prolific app)
# screens so both cohorts receive identical instructions.
DIRECTIONS_MD = """
**How to complete this task**

- Once you begin, open the **sidebar on the left**. It holds the full rubric and
  the 0–4 score definitions for all three dimensions. Keep it open and refer back
  to it for every problem.
- Score each problem on all three dimensions: **Geometric Accuracy**, **Lesson
  Alignment**, and **Linguistic Clarity**.
- When judging **Lesson Alignment**, use the lesson alignment concepts listed in
  the sidebar (dilations and similar triangles: scale factor, corresponding
  sides, AA / SSS / SAS similarity).
"""

CSS = """
<style>
  .problem-card { font-size:1.3rem; line-height:1.8; padding:1.8rem 2rem;
                  margin:.5rem 0 1.5rem 0; border:1px solid rgba(128,128,128,.3);
                  border-radius:10px; }
  .counter { font-variant-numeric:tabular-nums; opacity:.7; font-size:.95rem; }
  .dim-name { font-weight:600; font-size:1.05rem; margin-bottom:-.35rem; }
  .dim-help { opacity:.65; font-size:.85rem; margin-bottom:.15rem; }
  div[role="radiogroup"] { display:flex; justify-content:space-between; gap:.25rem; }
  div[role="radiogroup"] > label { flex:1 1 0; justify-content:center; margin:0; }
</style>
"""

# The grading rubric lives in the sidebar; graders must actually read it, so it is
# deliberately enlarged and the score anchors are shown open (not hidden in expanders).
SIDEBAR_CSS = """
<style>
  section[data-testid="stSidebar"] { min-width: 23rem; }
  section[data-testid="stSidebar"] .stMarkdown p,
  section[data-testid="stSidebar"] .stMarkdown li { font-size: 1.06rem; line-height: 1.55; }
  section[data-testid="stSidebar"] h3 { font-size: 1.32rem; margin: .5rem 0 .2rem; }
  section[data-testid="stSidebar"] [data-testid="stCaptionContainer"] p { font-size: .98rem; }
  .rubric-callout { background: rgba(255,193,7,.16); border: 1px solid rgba(255,193,7,.55);
                    border-radius: 8px; padding: .75rem .9rem; font-size: 1.07rem;
                    line-height: 1.5; margin-bottom: .7rem; }
  .dim-head { font-size: 1.12rem; font-weight: 700; margin: .5rem 0 .1rem; }
  .anchor-line { font-size: 1.03rem; line-height: 1.5; margin: .12rem 0; }
  .anchor-line b { display: inline-block; min-width: 1.1rem; }
</style>
"""


def load_problems() -> tuple[str, list[dict]]:
    if not PROBLEMS_PATH.is_file():
        return "", []
    data = json.loads(PROBLEMS_PATH.read_text(encoding="utf-8"))
    # strip the researcher key so it can never reach the browser
    probs = [{"item_id": p["item_id"], "text": p["text"]} for p in data["problems"]]
    return data.get("lesson_context", ""), probs


def save_draft(email, name, ratings, idx) -> None:
    storage.save_draft(SCOPE, email, {"evaluator_name": name, "index": idx,
                                      "ratings": ratings})
    answered = sum(1 for v in ratings.values() if len(v) == len(RUBRIC))
    storage.save_progress(SCOPE, email, name, answered, 10,
                          f"problem {idx + 1} of 10")


def load_draft(email: str) -> dict | None:
    return storage.load_draft(SCOPE, email)


def submit(email, name, ratings) -> None:
    storage.submit_response(SCOPE, email, name, ratings,
                            [f for f, _, _, _ in RUBRIC])
    storage.delete_draft(SCOPE, email)


def sidebar(context: str, answered: int, total: int) -> None:
    with st.sidebar:
        st.markdown(SIDEBAR_CSS, unsafe_allow_html=True)
        st.markdown(
            "<div class='rubric-callout'>📋 <b>Score every problem against this rubric.</b> "
            "Keep this panel open and refer to it for all three dimensions on each problem.</div>",
            unsafe_allow_html=True)
        if context:
            st.markdown("### Lesson alignment concepts")
            st.markdown(context)
        st.divider()
        st.markdown("### Rating guide")
        for field, label, weight, blurb in RUBRIC:
            st.markdown(f"<div class='dim-head'>{label} · {weight}</div>",
                        unsafe_allow_html=True)
            st.caption(blurb)
            for s in (4, 3, 2, 1, 0):
                st.markdown(f"<div class='anchor-line'><b>{s}</b> — {ANCHORS[field][s]}</div>",
                            unsafe_allow_html=True)
            st.write("")
        st.divider()
        st.caption(f"Answered {answered} of {total}")


def main() -> None:
    st.set_page_config(page_title="Rater Calibration", page_icon="🎯", layout="centered")
    context, problems = load_problems()
    total = len(problems)

    if total == 0:
        st.error("calibration_problems.json not found in pipelines/survey_data/.")
        return

    st.session_state.setdefault("step", "intro")
    st.session_state.setdefault("idx", 0)
    st.session_state.setdefault("ratings", {})

    if st.session_state.step == "done":
        st.success("Calibration submitted. Thank you — we'll review these together "
                   "before the main study.")
        return

    if st.session_state.step == "intro":
        st.title("Rater Calibration")
        st.write(
            f"This is a short **{total}-problem** warm-up before the main study. "
            "Its purpose is to check that we're all reading the rubric the same way — "
            "not to test you. Some of these problems have deliberate flaws; others are fine."
        )
        st.info("Please score independently and **do not discuss with the other raters** "
                "until we meet. Disagreement here is useful — it tells us where the "
                "rubric needs sharpening.")
        st.markdown(DIRECTIONS_MD)
        st.markdown(context)
        name = st.text_input("Name")
        email = st.text_input("Email")
        if st.button("Begin", type="primary", disabled=not (name and email)):
            d = load_draft(email)
            st.session_state.update(
                evaluator_name=name, evaluator_email=email,
                ratings=(d or {}).get("ratings", {}), idx=int((d or {}).get("index", 0)),
                step="survey")
            st.rerun()
        return

    email = st.session_state["evaluator_email"]
    name = st.session_state["evaluator_name"]
    ratings = st.session_state["ratings"]
    idx = st.session_state["idx"]
    item = problems[idx]

    answered = sum(1 for v in ratings.values() if len(v) == len(RUBRIC))
    sidebar(context, answered, total)

    st.markdown(CSS, unsafe_allow_html=True)
    st.progress(idx / total)
    st.markdown(f"<div class='counter'>Problem {idx+1} of {total}</div>", unsafe_allow_html=True)
    st.markdown(f"<div class='problem-card'>{item['text']}</div>", unsafe_allow_html=True)

    current = ratings.get(item["item_id"], {})
    for field, label, weight, blurb in RUBRIC:
        st.markdown(f"<div class='dim-name'>{label} "
                    f"<span style='opacity:.5;font-weight:400'>· {weight}</span></div>",
                    unsafe_allow_html=True)
        st.markdown(f"<div class='dim-help'>{blurb}</div>", unsafe_allow_html=True)
        prev = current.get(field)
        choice = st.radio(label, options=[0, 1, 2, 3, 4],
                          index=prev if prev is not None else None,
                          key=f"{item['item_id']}__{field}",
                          horizontal=True, label_visibility="collapsed")
        if choice is not None:
            current[field] = choice
        st.write("")
    ratings[item["item_id"]] = current

    complete = all(len(ratings.get(p["item_id"], {})) == len(RUBRIC) for p in problems)
    left, mid, right = st.columns([1, 2, 1])
    with left:
        prev_click = st.button("← Previous", disabled=(idx == 0), use_container_width=True)
    with right:
        if idx < total - 1:
            next_click = st.button("Next →", type="primary", use_container_width=True)
            submit_click = False
        else:
            submit_click = st.button("Submit calibration", type="primary",
                                     disabled=not complete, use_container_width=True)
            next_click = False
    with mid:
        if idx == total - 1 and not complete:
            st.caption("Rate all 10 problems on all three dimensions to submit.")

    # Persist only on navigation, not on every rerun, to stay well under the
    # Google Sheets API rate limit.
    if prev_click:
        save_draft(email, name, ratings, idx - 1)
        st.session_state.idx = idx - 1
        st.rerun()
    elif next_click:
        save_draft(email, name, ratings, idx + 1)
        st.session_state.idx = idx + 1
        st.rerun()
    elif submit_click:
        submit(email, name, ratings)
        st.session_state.step = "done"
        st.rerun()


if __name__ == "__main__":
    main()