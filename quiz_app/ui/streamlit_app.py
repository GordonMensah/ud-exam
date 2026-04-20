"""Streamlit UI matching the UO-SAT exam format exactly."""

from __future__ import annotations

import json
import os
import sys
import tempfile
import time
from pathlib import Path

_APP_ROOT = str(Path(__file__).resolve().parents[1])
_REPO_ROOT = Path(__file__).resolve().parents[2]
if _APP_ROOT not in sys.path:
    sys.path.insert(0, _APP_ROOT)

import streamlit as st  # noqa: E402

from engine.quiz_engine import QuizEngine  # noqa: E402
from engine.scoring import score_question as _score_q  # noqa: E402
from generator.epub_parser import parse_epub  # noqa: E402
from generator.question_generator import generate_all_chapter_questions  # noqa: E402
from generator.variant_generator import generate_exam_variants, generate_quiz_variants  # noqa: E402

# Data directory: use /tmp on cloud for writes, but use app's data/ for local runs.
_LOCAL_DATA = Path(_APP_ROOT) / "data"
_CLOUD_DATA = Path("/tmp/ud_exam_data")

# Local dev venv is at repo root; Streamlit Cloud typically has no repo-root .venv.
# Allow env override if needed.
_IS_CLOUD = os.environ.get("UD_EXAM_CLOUD", "").strip().lower() in {"1", "true", "yes"} or not (_REPO_ROOT / ".venv").exists()

DATA_DIR = _CLOUD_DATA if _IS_CLOUD else _LOCAL_DATA
DATA_DIR.mkdir(parents=True, exist_ok=True)

# Bundle: on cloud, prefer /tmp copy (user-uploaded); locally prefer app/data/.
_CLOUD_BUNDLE = _CLOUD_DATA / "books_bundle.json"
_LOCAL_BUNDLE = _LOCAL_DATA / "books_bundle.json"


def _bundle_path() -> Path:
    if _IS_CLOUD:
        return _CLOUD_BUNDLE if _CLOUD_BUNDLE.exists() else _LOCAL_BUNDLE
    return _LOCAL_BUNDLE if _LOCAL_BUNDLE.exists() else _CLOUD_BUNDLE


LABELS = ["a", "b", "c", "d", "e"]

# ── helpers ────────────────────────────────────────────────────────────────

def _save_json(path: Path, data) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8") as f:
        json.dump(data, f, indent=2, ensure_ascii=False)


def _load_json(path: Path, default=None):
    if not path.exists():
        return default or {}
    with path.open("r", encoding="utf-8") as f:
        return json.load(f)


def _load_books_bundle() -> dict:
    """Load the books bundle, merging local and cloud copies when both exist."""
    if _IS_CLOUD:
        merged: dict = dict(_load_json(_LOCAL_BUNDLE, {}))
        merged.update(_load_json(_CLOUD_BUNDLE, {}))
        return merged

    merged = dict(_load_json(_CLOUD_BUNDLE, {}))
    merged.update(_load_json(_LOCAL_BUNDLE, {}))
    return merged


def _build_book_payload(questions_by_chapter: dict) -> dict:
    quiz_variants: dict = {}
    for ch_id, pool in questions_by_chapter.items():
        if pool:
            quiz_variants[ch_id] = generate_quiz_variants(
                pool, num_variants=5, questions_per_quiz=min(5, len(pool))
            )
    all_q = [q for pool in questions_by_chapter.values() for q in pool]
    exam_variants = (
        generate_exam_variants(all_q, num_variants=6, exam_size=min(120, len(all_q)))
        if all_q else []
    )
    return {
        "questions": questions_by_chapter,
        "quiz_variants": quiz_variants,
        "exam_variants": exam_variants,
    }


# ── CSS ────────────────────────────────────────────────────────────────────

_CSS = """
<style>
/* Question card */
.q-card {
    background: #d9edf7;
    border: 1px solid #bcdcf0;
    border-radius: 4px;
    padding: 12px 16px 6px 16px;
    margin-bottom: 20px;
}
.q-stem {
    font-weight: bold;
    font-size: 1.02rem;
    margin-bottom: 10px;
}
/* Option row */
.opt-row {
    padding: 8px 10px;
    border-bottom: 1px solid #e0e0e0;
    font-size: 0.97rem;
}
.opt-row-even { background: #fffde7; }
.opt-row-odd  { background: #ffffff; }
.opt-label { font-weight: bold; color: #333; }
/* Timer */
.timer-wrap {
    float: right;
    background: #fff3cd;
    border: 2px solid #dc3545;
    border-radius: 4px;
    padding: 4px 14px;
    font-weight: bold;
    font-size: 1rem;
    color: #dc3545;
}
/* Nav buttons */
.nav-btn { text-align: center; }
/* Meta panel */
.q-meta {
    font-size: 0.82rem;
    color: #555;
    line-height: 1.6;
}
.q-meta b { color: #222; }
/* Score badges */
.badge-correct {
    display: inline-block;
    background: #d4edda; border: 1px solid #28a745;
    border-radius: 4px; padding: 4px 10px;
    font-size: 0.9rem; margin-top: 4px;
}
.badge-wrong {
    display: inline-block;
    background: #f8d7da; border: 1px solid #dc3545;
    border-radius: 4px; padding: 4px 10px;
    font-size: 0.9rem; margin-top: 4px;
}
/* Radio buttons — ensure visible */
div[data-testid="stRadio"] > div {
    flex-direction: row !important;
    gap: 1.5rem !important;
}
div[data-testid="stRadio"] label {
    font-size: 0.95rem !important;
    color: #333 !important;
    cursor: pointer !important;
}
div[data-testid="stRadio"] label span[data-testid="stMarkdownContainer"] p {
    font-size: 0.95rem !important;
    color: #333 !important;
}
div[data-testid="stRadio"] input[type="radio"] {
    accent-color: #0d6efd !important;
    width: 16px !important;
    height: 16px !important;
}
</style>
"""


# ── question renderer ──────────────────────────────────────────────────────

def _render_question(
    q_num: int,
    question: dict,
    engine: QuizEngine,
    show_feedback: bool,
) -> None:
    qid = question["id"]
    is_submitted = engine.state.submitted
    is_flagged = qid in engine.state.flagged
    prev_response = engine.state.responses.get(qid, {})
    answered = bool(prev_response)

    # ── outer columns: meta-left | question-center ──────────────────────
    meta_col, q_col = st.columns([1, 8])

    with meta_col:
        flag_icon = "🚩" if is_flagged else "🏳"
        st.markdown(
            f"""<div class="q-meta">
            <b>Question {q_num}</b><br>
            {'<span style="color:green">Answered</span>' if answered else 'Not yet answered'}<br>
            Marked out of 5.0<br>
            </div>""",
            unsafe_allow_html=True,
        )
        if st.button(f"{flag_icon} Flag", key=f"flag_{qid}", use_container_width=True):
            engine.toggle_flag(qid)

    with q_col:
        # Question stem
        st.markdown(
            f'<div class="q-card"><div class="q-stem">{question["question"]}</div>',
            unsafe_allow_html=True,
        )

        # Option rows — table-style: option text | ○True | ○False | ○Skip
        for i, label in enumerate(LABELS):
            opt_text = question["options"][label]
            row_class = "opt-row-even" if i % 2 == 1 else "opt-row-odd"

            prev_val = prev_response.get(label)
            if prev_val is True:
                default_idx = 0
            elif prev_val is False:
                default_idx = 1
            else:
                default_idx = 2

            st.markdown(
                f'<div class="opt-row {row_class}"><span class="opt-label">{label}.</span> {opt_text}</div>',
                unsafe_allow_html=True,
            )
            st.radio(
                f"response_{label}",
                options=["True", "False", "Skip"],
                index=default_idx,
                key=f"R_{qid}_{label}",
                horizontal=True,
                disabled=is_submitted,
                label_visibility="collapsed",
            )

        # Scripture reference block (always visible for 'talks about' questions)
        src_text = question["source"].get("text", "")
        src_ref = question["source"].get("reference", "")
        is_talks_about = "talks about" in question["question"].lower()
        if is_talks_about and src_text and not src_text.lower().startswith("see "):
            st.markdown(
                f'<div style="margin:8px 0 4px 0; padding:10px 14px; '
                f'background:#f0f4ff; border-left:4px solid #4a6fa5; '
                f'border-radius:4px; font-style:italic; font-size:0.95em;">'
                f'<span style="font-weight:600; font-style:normal;">📖 {src_ref}:</span> '
                f'"{src_text}"</div>',
                unsafe_allow_html=True,
            )

        st.markdown("</div>", unsafe_allow_html=True)

        # Save / feedback
        if not is_submitted:
            if st.button("💾 Save Answer", key=f"save_{qid}"):
                response = {}
                for label in LABELS:
                    val = st.session_state.get(f"R_{qid}_{label}", "Skip")
                    if val == "True":
                        response[label] = True
                    elif val == "False":
                        response[label] = False
                    else:
                        response[label] = None
                feedback = engine.answer_question(qid, response)
                if show_feedback:
                    sc = feedback["question_score"]
                    badge = "badge-correct" if sc >= 0 else "badge-wrong"
                    st.markdown(
                        f'<span class="{badge}">Score: {sc}/5.0 &nbsp;|&nbsp; '
                        f'Ref: {feedback["source"]["reference"]}</span>',
                        unsafe_allow_html=True,
                    )
                    fb_text = feedback["source"].get("text", "")
                    fb_ref = feedback["source"].get("reference", "")
                    if fb_text and not fb_text.lower().startswith("see "):
                        st.markdown(
                            f'<div style="margin:4px 0; padding:8px 12px; '
                            f'background:#f0f4ff; border-left:4px solid #4a6fa5; '
                            f'border-radius:4px; font-style:italic; font-size:0.9em;">'
                            f'<span style="font-weight:600; font-style:normal;">📖 {fb_ref}:</span> '
                            f'"{fb_text}"</div>',
                            unsafe_allow_html=True,
                        )
                    else:
                        st.caption(fb_text)

        # Post-submission review (exam mode)
        if is_submitted:
            resp = engine.state.responses.get(qid, {})
            sc = _score_q(resp, question["answers"])
            badge = "badge-correct" if sc >= 0 else "badge-wrong"
            correct_str = " | ".join(
                f"{lb}.{'T' if question['answers'][lb] else 'F'}" for lb in LABELS
            )
            st.markdown(
                f'<span class="{badge}">Score: {sc}/5.0 &nbsp;|&nbsp; '
                f'Correct: {correct_str} &nbsp;|&nbsp; '
                f'{question["source"]["reference"]}</span>',
                unsafe_allow_html=True,
            )
            rev_text = question["source"].get("text", "")
            rev_ref = question["source"].get("reference", "")
            if rev_text and not rev_text.lower().startswith("see "):
                st.markdown(
                    f'<div style="margin:4px 0; padding:8px 12px; '
                    f'background:#f0f4ff; border-left:4px solid #4a6fa5; '
                    f'border-radius:4px; font-style:italic; font-size:0.9em;">'
                    f'<span style="font-weight:600; font-style:normal;">📖 {rev_ref}:</span> '
                    f'"{rev_text}"</div>',
                    unsafe_allow_html=True,
                )


# ── main app ───────────────────────────────────────────────────────────────

def main() -> None:
    st.set_page_config(
        page_title="UO-SAT Scripture Exam", layout="wide", initial_sidebar_state="expanded"
    )
    st.markdown(_CSS, unsafe_allow_html=True)

    # ── sidebar: upload & settings ─────────────────────────────────────
    with st.sidebar:
        st.markdown("## 📚 Scripture Exam")
        st.markdown("---")

        with st.expander("📂 Upload & Generate", expanded=True):
            uploaded = st.file_uploader("EPUB file(s)", type=["epub"], accept_multiple_files=True)
            seed = st.number_input("Seed", min_value=0, value=42, step=1)
            if st.button("🔄 Generate Questions", use_container_width=True):
                if not uploaded:
                    st.warning("Upload at least one EPUB.")
                else:
                    # Merge into existing bundle so adding the next book doesn't wipe earlier ones.
                    bundle_out: dict = dict(_load_books_bundle())

                    bar = st.progress(0)
                    for idx, epub_file in enumerate(uploaded):
                        with tempfile.NamedTemporaryFile(delete=False, suffix=".epub") as tmp:
                            tmp.write(epub_file.read())
                            tmp_path = Path(tmp.name)
                        chapters = parse_epub(tmp_path)
                        pools = generate_all_chapter_questions(
                            chapters,
                            pool_size=25,
                            seed=int(seed) + idx,
                            book_title=Path(epub_file.name).stem,
                        )
                        ser = {str(k): v for k, v in pools.items()}
                        bundle_out[Path(epub_file.name).stem] = _build_book_payload(ser)
                        total = sum(len(v) for v in ser.values())
                        st.markdown(
                            f"✅ **{epub_file.name}** — {len(chapters)} chapters, {total} questions"
                        )
                        bar.progress((idx + 1) / len(uploaded))

                    # On cloud, save to writable /tmp; locally save to app data/
                    save_target = _CLOUD_BUNDLE if _IS_CLOUD else _LOCAL_BUNDLE
                    _save_json(save_target, bundle_out)
                    st.success("Done! Scroll to Diagnostics tab to verify.")

        st.markdown("---")

    # ── load data ──────────────────────────────────────────────────────
    bundle = _load_books_bundle()
    if not bundle:
        st.info("👆 Upload EPUB file(s) and click **Generate Questions** to begin.")
        return

    # ── tabs ───────────────────────────────────────────────────────────
    tab_quiz, tab_exam, tab_diag = st.tabs(["📖 Quiz (Chapter)", "📋 Exam (All Chapters)", "🔍 Diagnostics"])

    # ──────────────────── QUIZ TAB ────────────────────────────────────
    with tab_quiz:
        with st.sidebar:
            st.markdown("### ⚙️ Quiz Settings")
            book_q = st.selectbox("Book", sorted(bundle.keys()), key="book_q")
            book_data_q = bundle[book_q]
            ch_ids = sorted(
                [k for k, v in book_data_q["quiz_variants"].items() if v],
                key=int,
            )
            if not ch_ids:
                st.warning("No quiz variants found.")
            else:
                ch_id = st.selectbox("Chapter", ch_ids, format_func=lambda x: f"Chapter {x}", key="ch_sel")
                ch_vars = book_data_q["quiz_variants"][ch_id]
                var_labels = [v["variant_id"] for v in ch_vars]
                var_sel = st.selectbox("Variant", var_labels, key="qvar_sel")
                quiz_qs = next((v["questions"] for v in ch_vars if v["variant_id"] == var_sel), [])

                if st.button("▶ Start Quiz", use_container_width=True, key="start_quiz"):
                    st.session_state.quiz_engine = QuizEngine(quiz_qs, mode="test")
                    st.session_state.quiz_key = f"quiz:{book_q}:{ch_id}:{var_sel}"

        if "quiz_engine" not in st.session_state:
            st.info("👈 Choose a chapter and variant in the sidebar, then click **Start Quiz**.")
        else:
            engine_q: QuizEngine = st.session_state.quiz_engine
            qs = engine_q.state.questions

            # Quiz nav bar
            nav_cols = st.columns(len(qs) + 2)
            for i, q in enumerate(qs):
                is_ans = q["id"] in engine_q.state.responses
                label = f"{'✅' if is_ans else str(i+1)}"
                with nav_cols[i]:
                    st.markdown(f"<div class='nav-btn'>{label}</div>", unsafe_allow_html=True)

            st.markdown("---")

            for i, q in enumerate(qs):
                _render_question(i + 1, q, engine_q, show_feedback=True)

    # ──────────────────── EXAM TAB ────────────────────────────────────
    with tab_exam:
        with st.sidebar:
            st.markdown("### 📋 Exam Settings")
            book_e = st.selectbox("Book", sorted(bundle.keys()), key="book_e")
            book_data_e = bundle[book_e]
            exam_vars = book_data_e.get("exam_variants", [])
            if not exam_vars:
                st.warning("No exam variants. Re-generate with more chapters.")
            else:
                exam_var_labels = [v["variant_id"] for v in exam_vars]
                exam_var_sel = st.selectbox("Exam Variant", exam_var_labels, key="evar_sel")
                exam_qs = next((v["questions"] for v in exam_vars if v["variant_id"] == exam_var_sel), [])
                timer_mins = st.number_input("⏱ Timer (min)", min_value=1, value=60, step=5, key="timer_min")

                if st.button("▶ Start Exam", use_container_width=True, key="start_exam"):
                    st.session_state.exam_engine = QuizEngine(exam_qs, mode="exam")
                    st.session_state.exam_key = f"exam:{book_e}:{exam_var_sel}"
                    st.session_state.exam_start = time.time()
                    st.session_state.exam_secs = int(timer_mins) * 60
                    st.session_state.exam_page = 0

        if "exam_engine" not in st.session_state:
            st.info("👈 Choose an exam variant and click **Start Exam**.")
        else:
            engine_e: QuizEngine = st.session_state.exam_engine
            all_exam_qs = engine_e.state.questions
            is_submitted = engine_e.state.submitted

            # Timer
            if not is_submitted and st.session_state.get("exam_secs", 0) > 0:
                elapsed = time.time() - st.session_state.get("exam_start", time.time())
                remaining = max(0, st.session_state.exam_secs - elapsed)
                mins_left = int(remaining // 60)
                secs_left = int(remaining % 60)
                color = "#dc3545" if remaining < 120 else "#856404"
                st.markdown(
                    f'<div style="text-align:right">'
                    f'<span style="background:#fff3cd;border:2px solid {color};'
                    f'border-radius:4px;padding:4px 16px;font-weight:bold;color:{color};">'
                    f'Time left {mins_left:02d}:{secs_left:02d}</span></div>',
                    unsafe_allow_html=True,
                )
                if remaining <= 0:
                    engine_e.submit()
                    is_submitted = True

            # Question navigation panel (top)
            PER_PAGE = 5
            total_pages = max(1, (len(all_exam_qs) + PER_PAGE - 1) // PER_PAGE)
            cur_page = st.session_state.get("exam_page", 0)

            top_cols = st.columns(min(total_pages, 15) + 2)
            for pg in range(min(total_pages, 15)):
                page_start_q = pg * PER_PAGE
                page_qs = all_exam_qs[page_start_q: page_start_q + PER_PAGE]
                all_answered = all(q["id"] in engine_e.state.responses for q in page_qs)
                btn_label = f"{'✅' if all_answered else str(pg * PER_PAGE + 1)}"
                with top_cols[pg]:
                    if st.button(btn_label, key=f"pg_{pg}", use_container_width=True):
                        st.session_state.exam_page = pg

            with top_cols[-1]:
                if not is_submitted:
                    if st.button("Finish attempt…", type="primary", key="finish_exam"):
                        results = engine_e.submit()
                        is_submitted = True

            st.markdown("---")

            # Page of questions
            page_start = cur_page * PER_PAGE
            page_end = min(page_start + PER_PAGE, len(all_exam_qs))
            for i, q in enumerate(all_exam_qs[page_start:page_end], start=page_start + 1):
                _render_question(i, q, engine_e, show_feedback=False)

            # Prev / Next
            prev_c, _, next_c = st.columns([1, 5, 1])
            with prev_c:
                if cur_page > 0 and st.button("⬅ Prev"):
                    st.session_state.exam_page = cur_page - 1
            with next_c:
                if cur_page < total_pages - 1 and st.button("Next ➡"):
                    st.session_state.exam_page = cur_page + 1

            # Final score banner
            if is_submitted:
                results = engine_e.results()
                st.markdown("---")
                c1, c2, c3 = st.columns(3)
                c1.metric("Final Score", f"{results['total_score']:.1f} / {results['max_possible']:.0f}")
                c2.metric("Percentage", f"{results['percentage']}%")
                c3.metric("Answered", f"{results['questions_answered']} / {results['total_questions']}")

    # ──────────────────── DIAGNOSTICS TAB ────────────────────────────
    with tab_diag:
        st.subheader("🔍 Generation Diagnostics")
        diag_book = st.selectbox("Book", sorted(bundle.keys()), key="diag_book")
        diag = bundle[diag_book]
        qs_data = diag.get("questions", {})
        total = sum(len(v) for v in qs_data.values())

        c1, c2, c3 = st.columns(3)
        c1.metric("Chapters", len(qs_data))
        c2.metric("Total Questions", total)
        c3.metric("Exam Variants", len(diag.get("exam_variants", [])))

        st.markdown("---")
        for ch_id in sorted(qs_data.keys(), key=int):
            pool = qs_data[ch_id]
            scripture_types = [
                "is the biblical basis", "talks about", "can be found in",
                "cannot be found in", "can be gleaned from", "According to",
            ]
            has_scripture = any(any(t in q["question"] for t in scripture_types) for q in pool)
            icon = "✅" if has_scripture else "⚠️"
            label = "scripture-based" if has_scripture else "fallback — no scripture refs detected"
            with st.expander(f"{icon} Chapter {ch_id} — {len(pool)} questions ({label})"):
                for n, q in enumerate(pool[:5], 1):
                    st.markdown(f"**Q{n}: {q['question']}**")
                    for k in LABELS:
                        mark = "✓" if q["answers"][k] else "✗"
                        st.write(f"  {k}. [{mark}] {q['options'][k][:90]}")
                    st.caption(f"Source: {q['source']['reference']} — {q['source']['text'][:80]}")
                    st.markdown("---")


if __name__ == "__main__":
    main()
