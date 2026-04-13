"""EPUB parsing utilities."""

from __future__ import annotations

import re
from dataclasses import asdict, dataclass
from pathlib import Path
from typing import Any

from bs4 import BeautifulSoup
from ebooklib import ITEM_DOCUMENT, epub


@dataclass
class Chapter:
    """Structured chapter object."""

    chapter_id: int
    title: str
    text: str

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


_WHITESPACE_RE = re.compile(r"\s+")

# Titles / filenames that indicate front-matter to skip.
_SKIP_PATTERNS = re.compile(
    r"\b("
    r"introduction|intro|foreword|preface|prologue|"
    r"acknowledgement|acknowledgment|dedication|epigraph|"
    r"table\s*of\s*contents|contents|toc|"
    r"cover|title\s*page|half\s*title|copyright|"
    r"about\s*the\s*author|author\s*bio|"
    r"front\s*matter|frontmatter|"
    r"endorsement|commendation|"
    r"list\s*of\s*figures|list\s*of\s*tables|"
    r"abbreviation|glossary|index|bibliography|"
    r"appendix|backmatter|back\s*matter|"
    r"also\s*by|other\s*books"
    r")\b",
    re.IGNORECASE,
)

# Pattern that positively identifies a real chapter.
_CHAPTER_RE = re.compile(
    r"\b(chapter|ch\.?|part|lesson|section|unit)\s*\d",
    re.IGNORECASE,
)


def _clean_text(text: str) -> str:
    """Normalize whitespace and trim text."""
    return _WHITESPACE_RE.sub(" ", text).strip()


def _extract_title(soup: BeautifulSoup, fallback: str) -> str:
    """Extract chapter title from heading/title tags."""
    for selector in ("h1", "h2", "title"):
        node = soup.find(selector)
        if node and node.get_text(strip=True):
            return node.get_text(strip=True)
    return fallback


def _is_front_or_back_matter(title: str, filename: str) -> bool:
    """Return True if the section looks like intro / front-matter / back-matter."""
    combined = f"{title} {filename}"
    return bool(_SKIP_PATTERNS.search(combined))


def _is_chapter_heading(title: str) -> bool:
    """Return True if the title explicitly says 'Chapter N' or similar."""
    return bool(_CHAPTER_RE.search(title))


def parse_epub(epub_path: str | Path, min_chapter_chars: int = 200) -> list[Chapter]:
    """Parse an EPUB into chapter objects, skipping front/back matter.

    Args:
        epub_path: Path to EPUB file.
        min_chapter_chars: Minimum character count to keep a chapter.

    Returns:
        A list of Chapter objects (only real content chapters).
    """
    book = epub.read_epub(str(epub_path))

    # --- First pass: collect all candidate sections -------------------------
    raw_sections: list[tuple[str, str, str]] = []  # (title, text, filename)
    for item in book.get_items_of_type(ITEM_DOCUMENT):
        raw_html = item.get_content().decode("utf-8", errors="ignore")
        soup = BeautifulSoup(raw_html, "html.parser")
        text = _clean_text(soup.get_text(" "))
        if not text:
            continue
        filename = Path(item.get_name()).stem.replace("_", " ").title()
        title = _extract_title(soup, filename)
        raw_sections.append((title, text, filename))

    # --- Detect where real chapters begin -----------------------------------
    # Strategy: find the first section whose title matches "Chapter N" style.
    # If none match, fall back to skipping by keyword only.
    first_chapter_idx = 0
    for idx, (title, _text, _fn) in enumerate(raw_sections):
        if _is_chapter_heading(title):
            first_chapter_idx = idx
            break

    # --- Second pass: filter and number -------------------------------------
    chapters: list[Chapter] = []
    chapter_num = 1
    for idx, (title, text, filename) in enumerate(raw_sections):
        # Skip everything before the first real chapter
        if idx < first_chapter_idx:
            continue
        # Skip front/back matter that appears after chapter start
        if _is_front_or_back_matter(title, filename):
            continue
        # Skip very short sections (page breaks, blank pages)
        if len(text) < min_chapter_chars:
            continue

        chapters.append(Chapter(chapter_id=chapter_num, title=title, text=text))
        chapter_num += 1

    return chapters


def chapters_to_dict(chapters: list[Chapter]) -> list[dict[str, Any]]:
    """Serialize chapters for JSON storage."""
    return [chapter.to_dict() for chapter in chapters]
