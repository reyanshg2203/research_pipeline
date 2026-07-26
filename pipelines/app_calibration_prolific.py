"""
app_calibration_prolific.py — Prolific-facing version of the 10-problem IRR
calibration study.

Same 10 problems, same rubric, same Google Sheets backend as app_calibration.py,
but wired for anonymous Prolific participants instead of named internal raters:

  * Informed-consent gate as the mandatory first screen (no rating screen renders
    until an explicit consent decision is recorded).
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
COMPLETION_CODE = "CHANGE_ME"  # e.g. "C1AB23CD"
COMPLETION_URL = f"https://app.prolific.com/submissions/complete?cc={COMPLETION_CODE}"

# Contact shown on the consent screen (matches the IRB consent form on file).
CONTACT_EMAIL = "saurabh3005@gmail.com"

# ------------------------------------------------------------------ CONSENT
# This text is the exact consent instrument attached to the IRB submission.
# Keep this string and the IRB attachment identical.
CONSENT_MD = f"""
### Research Study: Evaluating AI-Generated Geometry Practice Problems

Thank you for your interest in this study. Before you begin, please read the
information below.

**What this study is about**
This study compares different methods for generating geometry practice problems
using AI, including a method that checks problems with a formal logic
verification step. We are asking experienced geometry teachers to review a small
set of problems and share their professional judgment on their quality.

**What you will be asked to do**
You will review 10 geometry problems and rate them on a short set of criteria
such as correctness, difficulty, and clarity. This first phase should take about
20 minutes. If you continue to the next phase of this study, you will be asked to
review 90 additional problems (broken into smaller 10-problem chunks) using the
same rating process, which should take about 180 minutes.

**Compensation**
You will be paid $5 for this phase through Prolific, based on an estimated
completion time of 20 minutes. Payment is not affected by whether you choose to
continue to a later phase.

**Voluntary participation**
Taking part in this study is entirely voluntary. You may stop at any time and for
any reason, and you will still be paid for the portion of the task you completed.

**Confidentiality**
This study does not collect your name or any other personally identifying
information beyond what Prolific already manages for participant payment. Your
ratings will be combined with those of other teachers and reported only in
aggregate. No individual responses will be shared or published.

**About this research**
This is a student-led independent research project. The study design and this
consent process were reviewed by an adult supervisor to help ensure it meets
standard ethical research practices.

**Questions**
If you have any questions about this study, you may contact {CONTACT_EMAIL} at
any time.
"""

AGREE = "I have read the above and voluntarily agree to participate."
DECLINE = "I do not agree to participate."


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
    # name is intentionally blank — no personal data is stored for Prolific raters
    storage.submit_response(SCOPE, pid, "", ratings, [f for f, _, _, _ in RUBRIC])
    storage.delete_draft(SCOPE, pid)


def completion_screen() -> None:
    st.success("Your ratings have been submitted. Thank you.")
    st.markdown("### Return to Prolific to complete the study")
    st.write("Copy the completion code below, or click the button, to finish and "
             "receive payment on Prolific.")
    st.code(COMPLETION_CODE, language=None)
    st.link_button("Complete on Prolific →", COMPLETION_URL, type="primary")


def declined_screen() -> None:
    st.markdown("## Study ended")
    st.info("You chose not to participate, so the study has ended and no ratings "
            "were recorded. You may now close this window and return the study on "
            "Prolific. Thank you for your time.")


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
    st.session_state.setdefault("step", "consent")
    st.session_state.setdefault("idx", 0)
    st.session_state.setdefault("ratings", {})
    # remember the PID across reruns once we have it
    if params["pid"]:
        st.session_state["pid"] = params["pid"]
        st.session_state.setdefault("study_id", params["study_id"])
        st.session_state.setdefault("session_id", params["session_id"])

    # ---------- terminal states ----------
    if st.session_state.step == "declined":
        declined_screen()
        return

    if st.session_state.step == "done":
        completion_screen()
        return

    # ---------- consent gate ----------
    if st.session_state.step == "consent":
        st.markdown(CONSENT_MD)
        st.markdown(DIRECTIONS_MD)
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

        choice = st.radio("Please indicate your decision:",
                          options=[AGREE, DECLINE], index=None)

        can_continue = bool(pid) and choice is not None
        if st.button("Continue", type="primary", disabled=not can_continue):
            agreed = (choice == AGREE)
            storage.log_consent(SCOPE, pid, agreed,
                                st.session_state.get("study_id", ""),
                                st.session_state.get("session_id", ""))
            st.session_state["pid"] = pid
            if not agreed:
                st.session_state.step = "declined"
                st.rerun()
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