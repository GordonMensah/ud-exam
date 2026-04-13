"""Runtime quiz/exam engine with mode-specific behavior.

Quiz Mode  = chapter-based questions (5 per quiz variant)
Exam Mode  = ALL chapters compiled together (120 per exam variant)
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Literal

from .scoring import score_assessment, score_question

Mode = Literal["test", "exam"]


@dataclass
class SessionState:
    """In-memory state for one quiz/exam attempt."""

    mode: Mode
    questions: list
    responses: dict = field(default_factory=dict)
    submitted: bool = False
    flagged: set = field(default_factory=set)


class QuizEngine:
    """Engine supporting Test Mode and Exam Mode."""

    def __init__(self, questions: list, mode: Mode = "test") -> None:
        self.state = SessionState(mode=mode, questions=questions)
        self._question_map = {q["id"]: q for q in questions}

    # ── answering ───────────────────────────────────────────────────────

    def answer_question(
        self, question_id: str, user_answers: dict,
    ) -> dict:
        """Record an answer.

        Test mode: returns immediate feedback.
        Exam mode: just confirms recording.
        """
        if self.state.submitted:
            raise RuntimeError("Answers are locked after submission.")
        if question_id not in self._question_map:
            raise KeyError(f"Unknown question_id: {question_id}")

        self.state.responses[question_id] = user_answers

        if self.state.mode == "test":
            q = self._question_map[question_id]
            s = score_question(user_answers, q["answers"])
            return {
                "mode": "test",
                "question_score": s,
                "max_score": 5.0,
                "correct_answers": q["answers"],
                "source": q["source"],
            }

        return {"mode": "exam", "message": "Answer recorded."}

    # ── flagging ────────────────────────────────────────────────────────

    def toggle_flag(self, question_id: str) -> bool:
        if question_id in self.state.flagged:
            self.state.flagged.discard(question_id)
            return False
        self.state.flagged.add(question_id)
        return True

    # ── submission ──────────────────────────────────────────────────────

    def submit(self) -> dict:
        if self.state.submitted:
            return self.results()
        self.state.submitted = True
        return self.results()

    def results(self) -> dict:
        summary = score_assessment(self.state.responses, self.state.questions)
        summary["mode"] = self.state.mode
        summary["submitted"] = self.state.submitted
        return summary
