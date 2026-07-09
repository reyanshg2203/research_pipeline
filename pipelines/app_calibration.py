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

import pandas as pd
import streamlit as st

ROOT = Path(__file__).resolve().parent.parent
PROBLEMS_PATH = ROOT / "pipelines" / "survey_data" / "calibration_problems.json"
CAL_DIR = ROOT / "pipelines" / "calibration_responses"
CAL_CSV = CAL_DIR / "calibration_responses.csv"
CAL_JSONL = CAL_DIR / "calibration_responses.jsonl"
DRAFTS_DIR = CAL_DIR / "drafts"

RUBRIC = [
    ("geometric_accuracy", "Geometric Accuracy", "50%",
     "Are the relationships mathematically correct, consistent, and solvable?"),
    ("lesson_alignment", "Lesson Alignment", "30%",
     "Does it target the lesson's skill at an appropriate difficulty?"),
    ("linguistic_clarity", "Linguistic Clarity", "20%",
     "Is the wording unambiguous and pitched at the right reading level?"),
]

ANCHORS = {
    "geometric_accuracy": {
        4: "All relationships correct and consistent. No contradictions.",
        3: "Major relationships correct; minor deviations that don't affect interpretation.",
        2: "One major relationship wrong or unsolvable, or several minor inconsistencies.",
        1: "Multiple major violations. Relationships misleading or inconsistent.",
        0: "Internally inconsistent or mathematically invalid.",
    },
    "lesson_alignment": {
        4: "Tightly aligned; integrates a supporting concept; productive edge of difficulty.",
        3: "Cleanly aligned to the lesson skill and appropriately challenging.",
        2: "Right skill, but generic or with a minor content gap.",
        1: "Related but imprecise skill; trivially easy or far too hard; surface reskin.",
        0: "Wrong skill, off-topic, or copied verbatim from a lesson example.",
    },
    "linguistic_clarity": {
        4: "Every term deliberate; fresh context; scaffolds without giving the answer away.",
        3: "Well-phrased and concise. A student reads once and knows what's asked.",
        2: "Unambiguous but clunky, verbose, or slightly mismatched to the audience.",
        1: "Decipherable with effort; ambiguous phrasing or undefined variables.",
        0: "Broken grammar, missing information, or contradictory constraints.",
    },
}

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


def load_problems() -> tuple[str, list[dict]]:
    if not PROBLEMS_PATH.is_file():
        return "", []
    data = json.loads(PROBLEMS_PATH.read_text(encoding="utf-8"))
    # strip the researcher key so it can never reach the browser
    probs = [{"item_id": p["item_id"], "text": p["text"]} for p in data["problems"]]
    return data.get("lesson_context", ""), probs


def _safe(e: str) -> str:
    return e.strip().lower().replace("@", "_at_").replace(".", "_")


def save_draft(email, name, ratings, idx) -> None:
    DRAFTS_DIR.mkdir(parents=True, exist_ok=True)
    (DRAFTS_DIR / f"{_safe(email)}.json").write_text(json.dumps(
        {"evaluator_name": name, "evaluator_email": email,
         "index": idx, "ratings": ratings}, indent=2), encoding="utf-8")


def load_draft(email: str) -> dict | None:
    p = DRAFTS_DIR / f"{_safe(email)}.json"
    if not p.is_file():
        return None
    try:
        return json.loads(p.read_text(encoding="utf-8"))
    except json.JSONDecodeError:
        return None


def submit(email, name, ratings) -> None:
    CAL_DIR.mkdir(parents=True, exist_ok=True)
    payload = {"submitted_at": datetime.now(timezone.utc).isoformat(),
               "evaluator_name": name, "evaluator_email": email, "ratings": ratings}
    rows = [{"evaluator_name": name, "evaluator_email": email, "item_id": iid, **scores}
            for iid, scores in ratings.items()]
    df = pd.DataFrame(rows)
    if CAL_CSV.is_file():
        df = pd.concat([pd.read_csv(CAL_CSV), df], ignore_index=True)
    df.to_csv(CAL_CSV, index=False)
    with CAL_JSONL.open("a", encoding="utf-8") as f:
        f.write(json.dumps(payload) + "\n")


def sidebar(context: str, answered: int, total: int) -> None:
    with st.sidebar:
        st.markdown("### Lesson context")
        st.caption(context)
        st.divider()
        st.markdown("### Rating guide")
        for field, label, weight, blurb in RUBRIC:
            st.markdown(f"**{label}** · {weight}")
            st.caption(blurb)
            with st.expander("Score anchors"):
                for s in (4, 3, 2, 1, 0):
                    st.markdown(f"**{s}** — {ANCHORS[field][s]}")
        st.divider()
        st.caption(f"Answered {answered} of {total}")


def main() -> None:
    st.set_page_config(page_title="Rater Calibration", page_icon="🎯", layout="centered")
    st.sidebar.caption(f"backend: {storage.backend_name()}")
    st.sidebar.caption(f"secrets keys: {list(st.secrets.keys())}")
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
        st.caption(context)
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

    save_draft(email, name, ratings, idx)

    if prev_click:
        st.session_state.idx = idx - 1
        st.rerun()
    elif next_click:
        st.session_state.idx = idx + 1
        st.rerun()
    elif submit_click:
        submit(email, name, ratings)
        st.session_state.step = "done"
        st.rerun()


if __name__ == "__main__":
    main()
