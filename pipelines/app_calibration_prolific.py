"""
app_calibration_prolific.py — Prolific-facing version of the 10-problem IRR
calibration study.

Same 10 problems, same rubric, same Google Sheets backend as app_calibration.py,
but wired for anonymous Prolific participants instead of named internal raters:
  * Consent was already obtained and approved earlier in the study, so this phase
    opens with a short intro screen (no consent gate).
  * Participant identity comes from Prolific's PROLIFIC_PID URL parameter, NOT a
    typed name/email. No personally identifying information is collected here.
  * A completion-code screen at the end so participants can be paid on Prolific.
  * Its own data scope ("cal_prolific") so Prolific data never mixes with the
    internal teacher calibration ("cal").

The rubric, anchors, styling, problem loader, and sidebar are imported directly
from app_calibration.py so the two studies CANNOT drift out of sync — the whole
point of a shared calibration is that both cohorts see an identical instrument.

Run locally:   streamlit run pipelines/app_calibration_prolific.py
               (writes to local files; append ?PROLIFIC_PID=test01 to the URL)
"""
from __future__ import annotations

import streamlit as st

import storage
from app_calibration import RUBRIC, ANCHORS, CSS, load_problems, sidebar, DIRECTIONS_MD

SCOPE = "cal_prolific"

# ------------------------------------------------------------------ CONFIG
# Set these two per Prolific study before you publish.
# Prolific gives you a completion code (and a matching completion URL) in the
# study's "How to record completion" step. Paste that code here.
COMPLETION_CODE = "CGUGWE4I" 
COMPLETION_URL = f"https://app.prolific.com/submissions/complete?cc=CGUGWE4I"

# ------------------------------------------------------------------ INTRO
INTRO_MD = """
You will rate **10 geometry practice problems** on three criteria, using the
written 0\u20134 scoring guide. Some problems are well written and some have flaws;
score each one exactly as it is written.
"""

# Prolific-only instructions (kept out of the shared DIRECTIONS_MD so the teacher
# app is unchanged).
PROLIFIC_DIRECTIONS_MD = """
**Before you begin**

- **Complete all 10 problems in one sitting.** This phase takes about 20 minutes,
  so please set aside that time before you start.
- **Score objectively.** Judge each problem strictly against the written 0\u20134
  definitions in the sidebar rubric, based on what the problem actually says, not
  on how you would have written it or on personal taste. Use the full 0\u20134 scale
  where the definitions call for it.
- **Payment.** You will receive **$5** through Prolific for this phase. When you
  submit your last rating you will be shown a completion code to enter on Prolific.
"""


# ------------------------------------------------------------------ helpers
def _params() -> dict:
    """Prolific passes PROLIFIC_PID / STUDY_ID / SESSION_ID as URL query params."""
    qp = st.query_params
    return {
        "pid": (qp.get("PROLIFIC_PID") or "").strip(),
        "study_id": (qp.get("STUDY_ID") or "").strip(),
        "session_id": (qp.get("SESSION_ID") or "").strip(),
    }


def save_draft(pid: str, ratings: dict, idx: int, total: int) -> None:
    storage.save_draft(SCOPE, pid, {"index": idx, "ratings": ratings})
    answered = sum(1 for v in ratings.values() if len(v) == len(RUBRIC))
    storage.save_progress(SCOPE, pid, "", answered, total, f"problem {idx + 1} of {total}")


def submit(pid: str, ratings: dict) -> None:
    # No real name is collected. The Prolific ID goes in the name column too, because
    # irr_report.py identifies each rater by evaluator_name and the shared cal_
    # tabs would otherwise hold blank names.
    storage.submit_response(SCOPE, pid, pid, ratings, [f for f, _, _, _ in RUBRIC])
    storage.delete_draft(SCOPE, pid)


def completion_screen() -> None:
    st.success("Your ratings have been submitted. Thank you.")
    st.markdown("### Return to Prolific to complete the study")
    st.write("Copy the completion code below, or click the button, to finish and "
             "receive payment on Prolific.")
    st.code(COMPLETION_CODE, language=None)
    st.link_button("Complete on Prolific →", COMPLETION_URL, type="primary")


# ------------------------------------------------------------------ main
def main() -> None:
    st.set_page_config(page_title="Geometry Problem Evaluation",
                       page_icon="📐", layout="centered")
    context, problems = load_problems()
    total = len(problems)
    if total == 0:
        st.error("calibration_problems.json not found in pipelines/survey_data/.")
        return

    params = _params()
    st.session_state.setdefault("step", "intro")
    st.session_state.setdefault("idx", 0)
    st.session_state.setdefault("ratings", {})
    # remember the PID across reruns once we have it
    if params["pid"]:
        st.session_state["pid"] = params["pid"]
        st.session_state.setdefault("study_id", params["study_id"])
        st.session_state.setdefault("session_id", params["session_id"])

    # ---------- terminal states ----------
    if st.session_state.step == "done":
        completion_screen()
        return

    # ---------- intro ----------
    if st.session_state.step == "intro":
        st.title("Geometry Problem Rating")
        st.markdown(INTRO_MD)
        st.markdown(DIRECTIONS_MD)
        st.markdown(PROLIFIC_DIRECTIONS_MD)
        st.divider()

        pid = st.session_state.get("pid", "")
        if pid:
            st.caption(f"Participant ID detected: `{pid}`")
        else:
            # Only reached in preview/testing (real Prolific links carry the PID).
            st.warning("No Prolific ID was found in the link. If you arrived from "
                       "Prolific, please return and use the study link. For testing, "
                       "enter an ID below.")
            pid = st.text_input("Prolific ID").strip()

        if st.button("Begin", type="primary", disabled=not pid):
            st.session_state["pid"] = pid
            # already finished earlier? recover the completion screen, no re-do
            if storage.has_submitted(SCOPE, pid):
                st.session_state.step = "done"
                st.rerun()
            d = storage.load_draft(SCOPE, pid)
            st.session_state.update(
                ratings=(d or {}).get("ratings", {}),
                idx=int((d or {}).get("index", 0)),
                step="survey")
            st.rerun()
        return

    # ---------- survey ----------
    pid = st.session_state["pid"]
    ratings = st.session_state["ratings"]
    idx = st.session_state["idx"]
    item = problems[idx]

    answered = sum(1 for v in ratings.values() if len(v) == len(RUBRIC))
    sidebar(context, answered, total)

    st.markdown(CSS, unsafe_allow_html=True)
    st.progress(idx / total)
    st.markdown(f"<div class='counter'>Problem {idx+1} of {total}</div>",
                unsafe_allow_html=True)
    st.markdown(f"<div class='problem-card'>{item['text']}</div>",
                unsafe_allow_html=True)

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
            submit_click = st.button("Submit ratings", type="primary",
                                     disabled=not complete, use_container_width=True)
            next_click = False
    with mid:
        if idx == total - 1 and not complete:
            st.caption(f"Rate all {total} problems on all three dimensions to submit.")

    # Persist only when the rater actually moves between problems, not on every
    # rerun — otherwise each radio click writes to Sheets and blows the API quota.
    if prev_click:
        save_draft(pid, ratings, idx - 1, total)
        st.session_state.idx = idx - 1
        st.rerun()
    elif next_click:
        save_draft(pid, ratings, idx + 1, total)
        st.session_state.idx = idx + 1
        st.rerun()
    elif submit_click:
        submit(pid, ratings)
        st.session_state.step = "done"
        st.rerun()


if __name__ == "__main__":
    main()