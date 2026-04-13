"""CLI entrypoint for quiz and exam generation."""

from __future__ import annotations

import argparse
import json
from pathlib import Path
from typing import Any

from generator.epub_parser import chapters_to_dict, parse_epub
from generator.question_generator import generate_all_chapter_questions
from generator.variant_generator import generate_exam_variants, generate_quiz_variants

DATA_DIR = Path(__file__).resolve().parent / "data"
QUESTIONS_PATH = DATA_DIR / "questions.json"
QUIZ_VARIANTS_PATH = DATA_DIR / "quiz_variants.json"
EXAM_VARIANTS_PATH = DATA_DIR / "exam_variants.json"
CHAPTERS_PATH = DATA_DIR / "chapters.json"
VARIANTS_PATH = DATA_DIR / "variants.json"


def save_json(path: Path, data: Any) -> None:
    """Persist JSON data with UTF-8 encoding."""
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8") as f:
        json.dump(data, f, ensure_ascii=False, indent=2)


def generate_from_epub(epub_path: Path, seed: int = 42) -> dict[str, Any]:
    """Generate chapters, questions, and variants from one EPUB."""
    chapters = parse_epub(epub_path)
    questions_by_chapter = generate_all_chapter_questions(chapters, pool_size=15, seed=seed)

    quiz_variants = {
        str(chapter_id): generate_quiz_variants(pool, num_variants=5, questions_per_quiz=5, seed=seed)
        for chapter_id, pool in questions_by_chapter.items()
    }

    all_questions = [q for pool in questions_by_chapter.values() for q in pool]
    exam_size = min(120, len(all_questions))
    exam_variants = generate_exam_variants(all_questions, num_variants=6, exam_size=exam_size, seed=seed)

    return {
        "book_name": epub_path.stem,
        "chapters": chapters_to_dict(chapters),
        "questions": {str(k): v for k, v in questions_by_chapter.items()},
        "quiz_variants": quiz_variants,
        "exam_variants": exam_variants,
    }


def parse_args() -> argparse.Namespace:
    """Parse CLI arguments."""
    parser = argparse.ArgumentParser(description="Generate quiz/exam data from an EPUB")
    parser.add_argument("epub", type=Path, nargs="+", help="Path(s) to input EPUB files")
    parser.add_argument("--seed", type=int, default=42, help="Random seed")
    return parser.parse_args()


def main() -> None:
    """Run CLI workflow."""
    args = parse_args()
    books: dict[str, Any] = {}
    for offset, epub_path in enumerate(args.epub):
        book_seed = args.seed + offset
        book_payload = generate_from_epub(epub_path, seed=book_seed)
        books[book_payload["book_name"]] = {
            "chapters": book_payload["chapters"],
            "questions": book_payload["questions"],
            "quiz_variants": book_payload["quiz_variants"],
            "exam_variants": book_payload["exam_variants"],
        }

    # Backward-compatible single-book outputs when one EPUB is provided.
    if len(books) == 1:
        one_book = next(iter(books.values()))
        save_json(CHAPTERS_PATH, one_book["chapters"])
        save_json(QUESTIONS_PATH, one_book["questions"])
        save_json(QUIZ_VARIANTS_PATH, one_book["quiz_variants"])
        save_json(EXAM_VARIANTS_PATH, one_book["exam_variants"])

    save_json(VARIANTS_PATH, {name: value["quiz_variants"] for name, value in books.items()})
    save_json(DATA_DIR / "books_bundle.json", books)
    print(f"Generated JSON files in: {DATA_DIR}")


if __name__ == "__main__":
    main()
