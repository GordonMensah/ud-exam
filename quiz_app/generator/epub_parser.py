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
    r"\b(chapter|ch\.?|part|lesson|unit)\s*\d",
    re.IGNORECASE,
)

# Extract the chapter number and optional subtitle from cleaned text.
# Text is whitespace-normalized (spaces only, no newlines).
# Subtitle: grab words until we hit a sentence boundary (lowercase word
# followed by lowercase, or punctuation like ? or .).
_CHAPTER_NUM_RE = re.compile(
    r"\bChapter\s+(\d+)\s+",
    re.IGNORECASE,
)


def _extract_chapter_subtitle(text: str) -> str:
    """Extract the short subtitle after 'Chapter N ' in cleaned text."""
    m = _CHAPTER_NUM_RE.search(text[:200])
    if not m:
        return ""
    after = text[m.end():m.end() + 80]
    # Take words until we hit a sentence-ending pattern.
    # Titles are like: "A Loyal Assistant", "Why Judas Betrayed Christ"
    # Body text starts with: "The assisting minister is anyone..."
    words = after.split()
    title_words = []
    for i, w in enumerate(words):
        # Stop at sentence punctuation
        if any(w.endswith(c) for c in (".", "?", "!", ":")):
            # Include this word if it's short (like "Loyalty?")
            cleaned = w.rstrip(".:?!")
            if cleaned and len(title_words) < 5:
                title_words.append(cleaned)
            break
        # Stop when we see two consecutive lowercase words (body text)
        if (i > 0 and w[0].islower()
                and i + 1 < len(words) and words[i + 1][0].islower()):
            break
        # Stop after collecting enough title words
        if len(title_words) >= 5:
            break
        title_words.append(w)
    return " ".join(title_words).strip()


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

    # --- Build TOC title lookup (filename stem → TOC title) -----------------
    toc_titles: dict[str, str] = {}
    for entry in book.toc:
        if hasattr(entry, "href") and hasattr(entry, "title"):
            stem = Path(entry.href.split("#")[0]).stem
            toc_titles[stem] = entry.title.strip()
        elif isinstance(entry, tuple):
            _sec, links = entry
            for link in links:
                stem = Path(link.href.split("#")[0]).stem
                toc_titles[stem] = link.title.strip()

    # --- First pass: collect all candidate sections -------------------------
    raw_sections: list[tuple[str, str, str]] = []  # (title, text, filename_stem)
    for item in book.get_items_of_type(ITEM_DOCUMENT):
        raw_html = item.get_content().decode("utf-8", errors="ignore")
        soup = BeautifulSoup(raw_html, "html.parser")
        text = _clean_text(soup.get_text(" "))
        if not text:
            continue
        stem = Path(item.get_name()).stem
        title = toc_titles.get(stem, _extract_title(soup, stem))
        raw_sections.append((title, text, stem))

    # --- Detect where real chapters begin -----------------------------------
    first_chapter_idx = 0
    for idx, (title, _text, _fn) in enumerate(raw_sections):
        if _is_chapter_heading(title):
            first_chapter_idx = idx
            break

    # --- Second pass: filter and number -------------------------------------
    chapters: list[Chapter] = []
    fallback_num = 1
    for idx, (title, text, stem) in enumerate(raw_sections):
        # Skip everything before the first real chapter
        if idx < first_chapter_idx:
            continue
        # Skip front/back matter that appears after chapter start
        if _is_front_or_back_matter(title, stem):
            continue
        # Skip very short sections (page breaks, blank pages)
        if len(text) < min_chapter_chars:
            continue

        # Extract actual book chapter number from text (e.g. "Chapter 7")
        ch_match = _CHAPTER_NUM_RE.search(text[:200])
        if ch_match:
            chapter_num = int(ch_match.group(1))
            # Prefer TOC title if available; fall back to text extraction
            toc_title = toc_titles.get(stem, "")
            if toc_title:
                # Normalize "Chapter N:Title" → "Chapter N: Title"
                display_title = re.sub(r":\s*", ": ", toc_title)
            else:
                subtitle = _extract_chapter_subtitle(text)
                display_title = f"Chapter {chapter_num}"
                if subtitle:
                    display_title += f": {subtitle}"
        else:
            # No "Chapter N" found – skip (e.g. copyright page)
            if not _is_chapter_heading(title):
                continue
            chapter_num = fallback_num
            display_title = title

        chapters.append(Chapter(chapter_id=chapter_num, title=display_title, text=text))
        fallback_num = chapter_num + 1

    return chapters


def chapters_to_dict(chapters: list[Chapter]) -> list[dict[str, Any]]:
    """Serialize chapters for JSON storage."""
    return [chapter.to_dict() for chapter in chapters]
