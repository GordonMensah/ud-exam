"""Quiz and exam variant generation."""

from __future__ import annotations

import random
from collections import defaultdict
from typing import Any


def _balanced_select(
    questions: list[dict[str, Any]],
    usage: dict[str, int],
    take: int,
    rng: random.Random,
) -> list[dict[str, Any]]:
    """Pick unique questions biased toward least-used items."""
    if take > len(questions):
        raise ValueError(f"Cannot take {take} unique questions from pool of {len(questions)}")

    selected: list[dict[str, Any]] = []
    selected_ids: set[str] = set()

    for _ in range(take):
        available = [q for q in questions if q["id"] not in selected_ids]
        min_usage = min(usage[q["id"]] for q in available)
        least_used = [q for q in available if usage[q["id"]] == min_usage]
        picked = rng.choice(least_used)
        selected.append(picked)
        selected_ids.add(picked["id"])
        usage[picked["id"]] += 1

    return selected


def generate_quiz_variants(
    question_pool: list[dict[str, Any]],
    num_variants: int = 5,
    questions_per_quiz: int = 5,
    seed: int | None = None,
) -> list[dict[str, Any]]:
    """Generate chapter quiz variants with no duplicates per variant."""
    rng = random.Random(seed)
    usage: dict[str, int] = defaultdict(int)

    variants: list[dict[str, Any]] = []
    for index in range(1, num_variants + 1):
        chosen = _balanced_select(question_pool, usage, questions_per_quiz, rng)
        variants.append(
            {
                "variant_id": f"quiz_v{index:02d}",
                "question_ids": [q["id"] for q in chosen],
                "questions": chosen,
            }
        )

    return variants


def generate_exam_variants(
    all_questions: list[dict[str, Any]],
    num_variants: int = 6,
    exam_size: int = 120,
    seed: int | None = None,
) -> list[dict[str, Any]]:
    """Generate exam variants from all chapter pools."""
    if exam_size > len(all_questions):
        raise ValueError(
            f"Exam size {exam_size} exceeds available unique questions {len(all_questions)}. "
            "Increase question pool or reduce exam size."
        )

    rng = random.Random(seed)
    usage: dict[str, int] = defaultdict(int)

    exams: list[dict[str, Any]] = []
    for index in range(1, num_variants + 1):
        chosen = _balanced_select(all_questions, usage, exam_size, rng)
        exams.append(
            {
                "variant_id": f"exam_v{index:02d}",
                "question_ids": [q["id"] for q in chosen],
                "questions": chosen,
            }
        )

    return exams
