"""Scoring utilities – UO-SAT style.

Each question has 5 options (a–e), each independently True/False/Skip.
- Correct option state: +1
- Wrong option state:   -1
- Skipped option:        0

Maximum per question: 5.0
"""

from __future__ import annotations

from typing import Any


def score_question(user_answers: dict, correct_answers: dict) -> float:
    """Score one question (out of 5.0).

    Args:
        user_answers: {"a": True/False/None, ...}
        correct_answers: {"a": True/False, ...}

    Returns:
        Score for the question (can be negative).
    """
    score = 0.0
    for key, correct_val in correct_answers.items():
        user_val = user_answers.get(key)
        if user_val is None:
            continue
        score += 1.0 if user_val == correct_val else -1.0
    return score


def score_assessment(
    responses: dict,
    questions: list,
) -> dict:
    """Score a full quiz or exam.

    Args:
        responses: {question_id: {a: True/False/None, ...}, ...}
        questions: list of question dicts.

    Returns:
        Summary with total, per-question scores, max possible, etc.
    """
    by_question: dict[str, float] = {}
    total = 0.0
    answered = 0

    for question in questions:
        qid = question["id"]
        user = responses.get(qid, {})
        qscore = score_question(user, question["answers"])
        by_question[qid] = qscore
        total += qscore
        if user:
            answered += 1

    max_possible = len(questions) * 5.0

    return {
        "total_score": total,
        "max_possible": max_possible,
        "percentage": round((total / max_possible) * 100, 1) if max_possible else 0.0,
        "questions_answered": answered,
        "total_questions": len(questions),
        "question_scores": by_question,
    }
