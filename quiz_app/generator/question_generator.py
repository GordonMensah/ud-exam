"""UO-SAT exam-style question generation.

Key principles (learned from actual UO-SAT screenshots):
─────────────────────────────────────────────────────────
1. Quoted text near a ref IS the verse → pair it with the CLOSEST ref.
2. Wrong ref options must be TRICKY (same chapter/diff book, same book/diff verse).
3. "talks about" options = short 3-8 word topic descriptions.
4. "quotations can/cannot be found" options = actual short verse phrases.
5. "biblical basis of" options = book teaching statements.
6. "according to" options = patterned lists (all follow the same prefix).
"""

from __future__ import annotations

import random
import re
from dataclasses import dataclass, field

from .epub_parser import Chapter  # noqa: F401

# ── Regex ──────────────────────────────────────────────────────────────────

_BOOK_NAMES = (
    r"Genesis|Exodus|Leviticus|Numbers|Deuteronomy|Joshua|Judges|Ruth|"
    r"1\s*Samuel|2\s*Samuel|1\s*Kings|2\s*Kings|1\s*Chronicles|2\s*Chronicles|"
    r"Ezra|Nehemiah|Esther|Job|Psalms?|Proverbs|Ecclesiastes|"
    r"Song\s*of\s*Solomon|Isaiah|Jeremiah|Lamentations|Ezekiel|Daniel|"
    r"Hosea|Joel|Amos|Obadiah|Jonah|Micah|Nahum|Habakkuk|Zephaniah|"
    r"Haggai|Zechariah|Malachi|"
    r"Matthew|Mark|Luke|John|Acts|Romans|"
    r"1\s*Corinthians|2\s*Corinthians|Galatians|Ephesians|Philippians|"
    r"Colossians|1\s*Thessalonians|2\s*Thessalonians|"
    r"1\s*Timothy|2\s*Timothy|Titus|Philemon|Hebrews|James|"
    r"1\s*Peter|2\s*Peter|1\s*John|2\s*John|3\s*John|Jude|Revelation|"
    r"Gênesis|Êxodo|Levítico|Números|Deuteronômio|Josué|Juízes|Rute|"
    r"1\s*Reis|2\s*Reis|1\s*Crônicas|2\s*Crônicas|Esdras|Neemias|Ester|"
    r"Jó|Salmos|Provérbios|Eclesiastes|Cânticos|Isaías|Jeremias|"
    r"Lamentações|Ezequiel|Oséias|Amós|Obadias|Jonas|Miquéias|Naum|"
    r"Habacuque|Sofonias|Ageu|Zacarias|Malaquias|Mateus|Marcos|Lucas|"
    r"João|Atos|Romanos|1\s*Coríntios|2\s*Coríntios|Gálatas|Efésios|"
    r"Filipenses|Colossenses|1\s*Tessalonicenses|2\s*Tessalonicenses|"
    r"1\s*Timóteo|2\s*Timóteo|Tito|Filemom|Hebreus|Tiago|"
    r"1\s*Pedro|2\s*Pedro|1\s*João|2\s*João|3\s*João|Judas|Apocalipse"
)

_SCRIPTURE_RE = re.compile(
    rf"(?:({_BOOK_NAMES})\s+(\d+)\s*:\s*(\d+)(?:\s*[-\u2013]\s*(\d+))?)",
    re.IGNORECASE,
)

_QUOTE_RE = re.compile(
    r'(?:["\u201c\u201d]|\.{3}|…)([^"\u201c\u201d]{6,150}?)(?:["\u201c\u201d]|\.{3}|…)',
)

_SENTENCE_RE = re.compile(r"(?<=[.!?])\s+")

LABELS = ["a", "b", "c", "d", "e"]

# All Bible books for generating tricky wrong refs
_ALL_BOOKS = [
    "Genesis", "Exodus", "Leviticus", "Numbers", "Deuteronomy",
    "Joshua", "Judges", "Ruth", "1 Samuel", "2 Samuel",
    "1 Kings", "2 Kings", "1 Chronicles", "2 Chronicles",
    "Ezra", "Nehemiah", "Esther", "Job", "Psalm", "Proverbs",
    "Ecclesiastes", "Song of Solomon", "Isaiah", "Jeremiah",
    "Lamentations", "Ezekiel", "Daniel", "Hosea", "Joel", "Amos",
    "Obadiah", "Jonah", "Micah", "Nahum", "Habakkuk", "Zephaniah",
    "Haggai", "Zechariah", "Malachi",
    "Matthew", "Mark", "Luke", "John", "Acts", "Romans",
    "1 Corinthians", "2 Corinthians", "Galatians", "Ephesians",
    "Philippians", "Colossians", "1 Thessalonians", "2 Thessalonians",
    "1 Timothy", "2 Timothy", "Titus", "Philemon", "Hebrews",
    "James", "1 Peter", "2 Peter", "1 John", "2 John", "3 John",
    "Jude", "Revelation",
]


# ── Data classes ───────────────────────────────────────────────────────────

@dataclass
class ScriptureRef:
    book: str
    chapter: int
    verse_start: int
    verse_end: int
    full_ref: str
    position: int  # char offset in the chapter text
    paired_quotes: list = field(default_factory=list)   # actual verse quotes
    commentary: list = field(default_factory=list)       # author's remarks near ref
    topics: list = field(default_factory=list)           # short topic descriptions
    teaching_points: list = field(default_factory=list)  # numbered points from the book


# ── Helpers ────────────────────────────────────────────────────────────────

def _norm_ref(book: str, ch: int, vs: int, ve: int) -> str:
    r = f"{book} {ch}:{vs}"
    if ve and ve != vs:
        r += f"-{ve}"
    return r


def _dedup(items: list) -> list:
    seen, out = set(), []
    for x in items:
        low = x.strip().lower()
        if low not in seen and len(low) > 2:
            seen.add(low)
            out.append(x.strip())
    return out


def _tricky_wrong_refs(correct: ScriptureRef, all_refs: list, rng: random.Random, n: int = 4) -> list:
    """Generate tricky wrong references that LOOK similar to the correct one.

    Strategies (matching UO-SAT patterns):
    1. Same chapter:verse, different book  (Genesis 31:20 → Leviticus 31:20)
    2. Same book, different chapter:verse  (Revelation 21:14 → Revelation 2:14)
    3. Same book+chapter, different verse  (2 Samuel 15:2 → 2 Samuel 15:5)
    4. Fall back to other refs from the text
    """
    wrong = []
    ch, vs, ve = correct.chapter, correct.verse_start, correct.verse_end

    # Strategy 1: same chapter:verse, different book
    other_books = [b for b in _ALL_BOOKS if b.lower() != correct.book.lower()]
    rng.shuffle(other_books)
    for b in other_books[:3]:
        wrong.append(_norm_ref(b, ch, vs, ve))

    # Strategy 2: same book, different chapter (nearby)
    for offset in [1, -1, 2, -2, 10, -10]:
        new_ch = ch + offset
        if new_ch > 0:
            wrong.append(_norm_ref(correct.book, new_ch, vs, ve))

    # Strategy 3: same book+chapter, different verse (nearby)
    # Always use a single-verse ref here to avoid inverted ranges like '17:16-13'.
    for offset in [1, -1, 2, -2, 3, -3]:
        new_vs = vs + offset
        if new_vs > 0:
            wrong.append(_norm_ref(correct.book, ch, new_vs, new_vs))

    # Strategy 4: actual other refs from the text
    text_refs = [r.full_ref for r in all_refs if r.full_ref != correct.full_ref]
    wrong.extend(text_refs)

    # Remove duplicates and the correct answer
    wrong = [w for w in dict.fromkeys(wrong) if w != correct.full_ref]
    return rng.sample(wrong, k=min(n, len(wrong))) if len(wrong) >= n else wrong[:n]


# ── Extraction ─────────────────────────────────────────────────────────────

def _extract_refs_with_context(text: str) -> list:
    """Extract all scripture refs and pair them with nearby quotes + commentary.

    Key fix: a quoted phrase is paired with the CLOSEST scripture ref,
    not just any ref. This ensures "mine own familiar friend..." pairs
    with Psalm 41:9 (the actual verse source).
    """
    # Step 1: find all refs with positions
    refs = []
    seen = set()
    for m in _SCRIPTURE_RE.finditer(text):
        book = m.group(1).strip()
        ch = int(m.group(2))
        vs = int(m.group(3))
        ve = int(m.group(4)) if m.group(4) else vs
        full = _norm_ref(book, ch, vs, ve)
        if full in seen:
            continue
        seen.add(full)
        refs.append(ScriptureRef(
            book=book, chapter=ch, verse_start=vs, verse_end=ve,
            full_ref=full, position=m.start(),
        ))

    if not refs:
        return refs

    # Step 2: find all quoted phrases with positions.
    # Each tuple is (char_position, quote_text, is_ellipsis).
    # is_ellipsis=True for …/... delimited quotes (verse fragments deliberately
    # truncated with ellipsis marks); False for smart/straight-quote delimited.
    quotes_with_pos = []
    for m in _QUOTE_RE.finditer(text):
        q = m.group(1).strip()
        open_char = m.group(0)[0]
        is_ell = open_char in ('\u2026', '.')  # U+2026 or ASCII dot(s)
        if 5 <= len(q) <= 150:
            if not _SCRIPTURE_RE.search(q):
                quotes_with_pos.append((m.start(), q, is_ell))
            elif is_ell:
                # Ellipsis-quoted verse fragment contains an embedded scripture
                # reference (e.g. "…compassed about and slew him. 2 Sam 18:15…").
                # Use only the text BEFORE the embedded reference so the quote
                # remains a clean, citable verse snippet.
                rm = _SCRIPTURE_RE.search(q)
                q_before = q[:rm.start()].strip().rstrip(' .,;\u2026')
                if len(q_before) >= 6:
                    quotes_with_pos.append((m.start(), q_before, True))

    # Secondary overlapping scan: re.finditer is non-overlapping, so alternating
    # …A…B…C… sequences only capture A and C (odd-indexed).  Run a lookahead-
    # based pass to also capture B (the even-indexed quotes whose opening …
    # was consumed as the closing … of the preceding match).
    _seen_qpos = {p for p, _, _ in quotes_with_pos}
    for m in re.finditer(r'(?=\u2026([^\u2026\u201c\u201d"]{6,150}?)\u2026)', text):
        q = m.group(1).strip()
        pos = m.start()
        if pos in _seen_qpos:
            continue
        if 5 <= len(q) <= 150 and not _SCRIPTURE_RE.search(q):
            quotes_with_pos.append((pos, q, True))
            _seen_qpos.add(pos)

    # Build a position-sorted list of refs once for midpoint calculations.
    _refs_by_pos = sorted(refs, key=lambda r: r.position)

    # Fallback: capture single-ellipsis verse snippets that end right before a
    # citation, even when there isn't a closing ellipsis nearby.
    # Example: "…out of the abundance of the heart the mouth speaketh. Matthew 12:34"
    for r in _refs_by_pos:
        ref_pos = r.position
        back_start = max(0, ref_pos - 260)
        back = text[back_start:ref_pos]
        epos = back.rfind('\u2026')
        if epos == -1:
            continue
        frag = back[epos + 1:].strip()
        # Prefer cutting at sentence end if present; avoid dragging headings.
        cut = max(frag.rfind('.'), frag.rfind('!'), frag.rfind('?'))
        if cut != -1 and cut >= 20:
            frag = frag[:cut].strip()
        frag = frag.strip().rstrip(' .,;:\u2026')
        if 6 <= len(frag) <= 150 and not _SCRIPTURE_RE.search(frag):
            qpos = back_start + epos
            if qpos not in _seen_qpos:
                quotes_with_pos.append((qpos, frag, True))
                _seen_qpos.add(qpos)

    def _midpoint_window(pos: int) -> tuple:
        """Return (lo, hi) clipped to the midpoints between adjacent refs.

        This ensures a quote (or commentary sentence) that sits between two
        refs is assigned only to the ref it is genuinely closest to, rather
        than being pulled into a ±N-char window that crosses into the next
        ref's territory.
        """
        lo, hi = 0, len(text)
        for i, r in enumerate(_refs_by_pos):
            if r.position <= pos:
                lo = (_refs_by_pos[i - 1].position + r.position) // 2 if i > 0 else 0
            else:
                hi = (r.position + _refs_by_pos[i - 1].position) // 2 if i > 0 else r.position
                break
        # Also cap at the boundary of the "winning" ref vs next ref
        for i, r in enumerate(_refs_by_pos):
            if r.position > pos:
                hi = min(hi, (_refs_by_pos[i - 1].position + r.position) // 2) if i > 0 else hi
                break
        return lo, hi

    # Step 3: pair each quote with the nearest ref that FOLLOWS it.
    # In this book the citation always appears AFTER the quoted verse text,
    # so the correct pairing is the first (nearest) ref at or after q_pos.
    # Fall back to nearest-by-distance only when no ref follows within limit.
    _INTERNAL_SENTENCE_RE = re.compile(r'[.!?]\s+[A-Z]')
    for q_pos, q_text, is_ellipsis in quotes_with_pos:
        # Skip body-text fragments captured between two uses of the same
        # quoted word (e.g. '"muddy" ... body text ... "muddy"').  Real
        # scripture quotes are a single flowing clause; they do NOT contain
        # an internal sentence boundary like ". B" or "! T".
        if _INTERNAL_SENTENCE_RE.search(q_text):
            continue
        # For smart/straight-quote delimited text, skip if it starts with a
        # lowercase letter (these are genuine mid-sentence continuations).
        # For ellipsis-delimited text, lowercase is expected — the author
        # deliberately truncates verse text with "…", so the fragment may
        # start mid-sentence but is still a valid verse passage.
        if not is_ellipsis and q_text and q_text[0].islower():
            continue
        # _refs_by_pos is already position-sorted, so the first element
        # with position >= q_pos is the nearest following ref.
        after = [r for r in _refs_by_pos if r.position >= q_pos]
        if after:
            closest = after[0]
            dist = closest.position - q_pos
        else:
            closest = min(refs, key=lambda r: abs(r.position - q_pos))
            dist = abs(closest.position - q_pos)
        if dist < 500:  # within 500 chars
            closest.paired_quotes.append(q_text)

    # Step 4: extract numbered teaching points ("12. Be genuinely happy...")
    # These are the author's actual teaching content that scripture refs support.
    # Text is whitespace-normalized (no newlines), so we match after sentence-end
    # punctuation or start-of-text, then a point label + separator.
    # Handles three formats used in this book:
    #   Arabic:      "1. Make mention…"      (after sentence-end or ": ")
    #   Roman lower: "i. When it comes…"     (after ": " typically)
    #   Alpha-paren: "a) Give ample notice…" (after sentence-end)
    # Group 1 = label,  Group 2 = content text
    _NUMBERED_POINT_RE = re.compile(
        # Lookbehind handles points after sentence-end punctuation AND after
        # scripture references which end in a digit (e.g. "Proverbs 17:13 f)").
        r'(?:^|(?<=\.\s)|(?<=\?\s)|(?<=!\s)|(?<=:\s)|(?<=\d\s))'
        r'(\d{1,3}|[ivx]{1,5}|[a-o])'   # label: arabic / lowercase roman / letter
        r'[.)]\s+'                         # separator: period or paren
        r'([A-Z][^.!?]{10,400})',          # content starts with capital
    )

    # Collect ALL numbered-point boundary positions so we can detect when
    # a teaching point and a ref belong to DIFFERENT numbered points.
    all_point_boundaries = sorted(
        m.start() for m in _NUMBERED_POINT_RE.finditer(text)
    )

    def _same_point_block(pos_a: int, pos_b: int) -> bool:
        """Return True if both positions fall within the same numbered-point block.

        Two positions are in the same block if no numbered-point boundary
        sits between them (inclusive of the upper endpoint).

        Using <= hi (not strict < hi) is essential: the teaching point
        extraction records pos_a = m.start(), which IS the boundary itself.
        If the ref sits before this boundary (pos_b < pos_a), the boundary
        at pos_a == hi must count as a separator — otherwise a teaching
        from point 4 gets paired with a ref that belongs to point 3.
        """
        lo, hi = min(pos_a, pos_b), max(pos_a, pos_b)
        for bp in all_point_boundaries:
            if lo < bp <= hi:
                return False
        return True

    # Pattern that detects a heading-to-body transition in normalized text.
    # After whitespace normalization, a numbered-point heading like
    # "7. In order to reap our full reward" is immediately followed by
    # the first body sentence "Those who benefit from..." with NO
    # punctuation between them.  The signature is: a content word ending
    # in a lowercase letter, then a space, then a sentence-initial word
    # that would never appear mid-phrase (pronoun, intensifier, etc.).
    _HEADING_CONCAT_RE = re.compile(r'(?<=[a-z]) (?:Those|These|They|Very|There|The|I)\b')

    _VAGUE_DEMON_RE = re.compile(
        r'\b(?:that|this|these|those)\s+'
        r'(?:mistake|error|sin|thing|habit|practice|act|approach|attitude|behaviour|behavior)\b',
        re.IGNORECASE,
    )

    points_with_pos = []
    for m in _NUMBERED_POINT_RE.finditer(text):
        point_text = m.group(2).strip().rstrip(".")
        # Take just the first sentence of the point
        first_sent = re.split(r'(?<=[.!?])\s+', point_text)[0].rstrip(".")
        # If the first "sentence" is actually a heading+body concatenation,
        # truncate to just the heading (the part before the join point).
        # E.g. "In order to reap our full reward Those who benefit..."
        #   → "In order to reap our full reward"
        hc = _HEADING_CONCAT_RE.search(first_sent)
        if hc:
            first_sent = first_sent[:hc.start()].rstrip()
        if 4 <= len(first_sent.split()) <= 25 and not _VAGUE_DEMON_RE.search(first_sent):
            points_with_pos.append((m.start(), first_sent))

    # Also extract sentences that start with key teaching verbs
    _TEACHING_SENT_RE = re.compile(
        r'(?:^|(?<=[.!?])\s+)'
        r'((?:A (?:good|bad|loyal|disloyal|treacherous|faithful) '
        r'(?:assistant|associate|leader|pastor|person|minister)|'
        r'(?:Be |Do not |Ensure |Make |Always |Never |Genuinely |You must ))'
        r'[^.]{10,120})',
        re.MULTILINE,
    )
    for m in _TEACHING_SENT_RE.finditer(text):
        t = m.group(1).strip().rstrip(".")
        if 5 <= len(t.split()) <= 25 and not _VAGUE_DEMON_RE.search(t):
            points_with_pos.append((m.start(), t))

    # Pair each teaching point with the CLOSEST ref — but ONLY if they
    # are in the same numbered-point block.  Points without a scripture
    # ref in their block won't get paired (correct behaviour).
    for pt_pos, pt_text in points_with_pos:
        # Filter to refs in the same point block first
        same_block_refs = [r for r in refs if _same_point_block(pt_pos, r.position)]
        if not same_block_refs:
            continue
        closest = min(same_block_refs, key=lambda r: abs(r.position - pt_pos))
        dist = abs(closest.position - pt_pos)
        if dist < 800:
            closest.teaching_points.append(pt_text)

    # Step 5: extract commentary and topics
    # Phrases that signal author meta-commentary rather than verse content.
    _META_PREFIXES = (
        "it is my prayer", "let us all", "the answer is",
        "as i said", "i believe", "i have seen", "i have rarely",
        "i have often", "i have wondered", "i have known",
        "what about", "why is", "this is why",
        "in other words", "this is another reason", "we all",
        "this will invite", "it cannot possibly", "the reason why",
        "it is important to note", "please note", "note that",
        "you will notice", "you will see", "you will find",
    )

    def _good_text(s):
        """Filter out fragments that are too short, garbled, or authorial meta-commentary."""
        s = s.strip().rstrip(".,;:!?")
        if not s or len(s) < 15:
            return None
        if _SCRIPTURE_RE.search(s):
            return None
        alpha = sum(1 for c in s if c.isalpha())
        if alpha < len(s) * 0.5:
            return None
        if s[0].islower() and not s.startswith(("a ", "an ", "the ")):
            return None
        if not s[0].isalpha():
            return None
        # Reject authorial meta-commentary ("It is my prayer...", "Let us all...")
        s_lower = s.lower()
        if any(s_lower.startswith(p) for p in _META_PREFIXES):
            return None
        # Reject vague demonstrative references that only make sense with prior
        # context, e.g. "Do not make that mistake" / "Avoid this error".
        # These appear as imperatives where the object is a demonstrative noun
        # phrase — meaningless as a standalone quiz option.
        if re.search(r'\b(?:that|this|these|those)\s+(?:mistake|error|sin|thing|habit|practice|act|approach|attitude|behaviour|behavior)\b', s_lower):
            return None
        # Reject apparent mid-word truncations: last word ends in letters but
        # the original sentence clearly continued (e.g. "or retra").
        # Heuristic: if the raw text ended at a window boundary and the last
        # word is ≤4 chars and not a known short word, discard.
        return s

    # Sort refs by position so we can find adjacent refs for window clamping.
    refs_by_pos = sorted(refs, key=lambda r: r.position)

    for ref in refs:
        # Clamp the context window to the same numbered-point block.
        # Find the point boundary just before and just after this ref.
        block_start = 0
        block_end = len(text)
        for bp in all_point_boundaries:
            if bp <= ref.position:
                block_start = bp
            elif bp > ref.position:
                block_end = bp
                break

        # Further clamp to the midpoint between adjacent refs so that text
        # sitting between two refs goes to the ref it is actually closer to.
        # This prevents "Hearken now unto my voice..." (between Exodus 4:18
        # and Exodus 18:7) from appearing in Exodus 4:18's commentary.
        idx = refs_by_pos.index(ref)
        if idx > 0:
            prev_pos = refs_by_pos[idx - 1].position
            block_start = max(block_start, (prev_pos + ref.position) // 2)
        if idx < len(refs_by_pos) - 1:
            next_pos = refs_by_pos[idx + 1].position
            block_end = min(block_end, (ref.position + next_pos) // 2)

        start = max(block_start, ref.position - 400)
        # Forward window is intentionally small (150 chars).
        # In this book's style the cited verse FOLLOWS the teaching statement,
        # so the relevant content is mostly BEFORE the ref.  A large forward
        # window bleeds past the next section heading (e.g. "Can Rebels
        # Repent?") into completely unrelated material.
        end = min(block_end, ref.position + 150)
        window = text[start:end]
        # Trim to last sentence boundary so we never get partial sentences
        # from the window edge (avoids truncated options like "or retra").
        last_boundary = max(
            (window.rfind(c) for c in ('.', '!', '?')),
            default=-1,
        )
        if last_boundary > 20:
            window = window[:last_boundary + 1]

        # Short topic descriptions from sentences.
        # We iterate with finditer to preserve the trailing delimiter so that
        # rhetorical questions (ending in "?") and short exclamatory headings
        # (e.g. "Friendly and Flashy!") are skipped.
        for _tm in re.finditer(r'([^.;!?]+)([.;!?])', window):
            if _tm.group(2) == '?':
                continue  # skip rhetorical / interrogative sentences
            if _tm.group(2) == '!' and len(_tm.group(1).split()) <= 5:
                continue  # skip short exclamatory headings
            cleaned = _good_text(_tm.group(1))
            if not cleaned:
                continue
            wc = len(cleaned.split())
            if 3 <= wc <= 12:
                ref.topics.append(cleaned)

        # Teaching/commentary statements (longer sentences near the ref).
        # Same finditer approach as topics so that ?-ending rhetorical
        # questions and short ! headings are filtered out here too.
        for _cm in re.finditer(r'([^.!?]+)([.!?])', window):
            if _cm.group(2) == '?':
                continue  # skip questions (rhetorical or otherwise)
            if _cm.group(2) == '!' and len(_cm.group(1).split()) <= 5:
                continue  # skip short exclamatory headings
            cleaned = _good_text(_cm.group(1))
            if not cleaned:
                continue
            wc = len(cleaned.split())
            if 6 <= wc <= 30:
                ref.commentary.append(cleaned)

        # Fix C: for window sentences that contain an embedded scripture
        # reference (e.g. "2 Sam 18:12 This unnamed person was loyal to him"),
        # extract the text immediately AFTER the last ref in the sentence.
        # This captures context that follows an inline citation in cases where
        # the citation sits at the start of the sentence (so the whole segment
        # was filtered by _good_text's not-alpha-start check).
        for _cm in re.finditer(r'([^.!?]+)([.!?])', window):
            seg = _cm.group(1)
            sc_matches = list(_SCRIPTURE_RE.finditer(seg))
            if not sc_matches:
                continue
            tail = seg[sc_matches[-1].end():].strip()
            cleaned = _good_text(tail)
            if not cleaned:
                continue
            wc = len(cleaned.split())
            if 3 <= wc <= 12:
                ref.topics.append(cleaned)
            if 6 <= wc <= 30:
                ref.commentary.append(cleaned)

        ref.paired_quotes = _dedup(ref.paired_quotes)
        ref.topics = _dedup(ref.topics)
        ref.commentary = _dedup(ref.commentary)
        ref.teaching_points = _dedup(ref.teaching_points)

    # Fix D: second pass for refs that are STILL bare (no topics, commentary,
    # paired_quotes, or teaching_points) after the midpoint-clamped first pass.
    # Widen the backward window to 600 chars, using only the numbered-point
    # block boundary as the floor (skip the midpoint clamp).  This lets refs
    # embedded in densely-packed execution-list or subtitle-list sections pick
    # up nearby sentences that the narrow clamped window excluded.
    for ref in refs:
        if ref.topics or ref.commentary or ref.paired_quotes or ref.teaching_points:
            continue
        pos = ref.position
        # Recompute block boundaries (numbered-point only, no midpoint clamp).
        bare_block_start = 0
        bare_block_end = len(text)
        for bp in all_point_boundaries:
            if bp <= pos:
                bare_block_start = bp
            elif bp > pos:
                bare_block_end = bp
                break
        wide_start = max(bare_block_start, pos - 600)
        wide_end = min(bare_block_end, pos + 300)
        window = text[wide_start:wide_end]
        # If the window starts mid-sentence (lowercase/digit first char that
        # doesn't look like a sentence opener), skip past the first fragment.
        if window and not window[0].isupper() and window[0] not in ('"', '\u201c'):
            first_end = max(window.find('.'), window.find('!'), window.find('?'))
            if 0 < first_end < len(window) - 1:
                window = window[first_end + 1:]
        for _cm in re.finditer(r'([^.!?]+)([.!?])', window):
            if _cm.group(2) == '?':
                continue
            if _cm.group(2) == '!' and len(_cm.group(1).split()) <= 5:
                continue
            seg = _cm.group(1)
            # Try text after embedded scripture refs (same as Fix C).
            sc_matches = list(_SCRIPTURE_RE.finditer(seg))
            if sc_matches:
                seg = seg[sc_matches[-1].end():].strip()
            cleaned = _good_text(seg)
            if not cleaned:
                continue
            wc = len(cleaned.split())
            if 3 <= wc <= 12:
                ref.topics.append(cleaned)
            if 6 <= wc <= 30:
                ref.commentary.append(cleaned)
        ref.topics = _dedup(ref.topics)
        ref.commentary = _dedup(ref.commentary)

    return refs


def _extract_teachings(text: str) -> list:
    """Extract teaching statements from the full chapter for 'biblical basis' options."""
    teachings = []
    patterns = [
        # "The X stage/sign/key/principle of Y"
        r"((?:The|A|An)\s+(?:\w+\s+)?(?:stage|sign|key|principle|mark|"
        r"danger|fruit|test|proof|characteristic|indicator|spirit|type|"
        r"form|nature|result|reason|cause|root|basis|foundation)\s+"
        r"(?:of|for|behind|in)\s+.{5,60}?)(?:\.|,|;|$)",
        # "A person/leader who X is Y"
        r"((?:A|The)\s+(?:person|leader|pastor|minister|assistant|man|woman|"
        r"loyal\s+\w+|disloyal\s+\w+|faithful\s+\w+|good\s+\w+|bad\s+\w+|"
        r"treacherous\s+\w+)\s+"
        r"(?:who|that|which|is|does|will|must|can|should)\s+.{10,80}?)(?:\.|;|$)",
        # "Loyalty/Disloyalty is/demands/requires X"
        r"((?:Loyalty|Disloyalty|Faithfulness)\s+"
        r"(?:is|demands|requires|has|means|involves|leads|causes)\s+.{5,60}?)(?:\.|,|;|$)",
        # Teaching imperatives: "Do not X", "Be X", "Ensure X", etc.
        r"((?:Do not|Be |Ensure |Make |Always |Never |You must |You should )"
        r"[a-z].{15,80}?)(?:\.|;|$)",
    ]
    for pat in patterns:
        for m in re.finditer(pat, text):
            t = m.group(1).strip().rstrip(".,;:!?")
            wc = len(t.split())
            if 5 <= wc <= 25 and not _SCRIPTURE_RE.search(t):
                teachings.append(t)
    return _dedup(teachings)


def _extract_patterned_lists(text: str) -> dict:
    """Extract items that share a common prefix pattern for 'according to' questions."""
    groups = {}

    patterns = [
        (r"(?:the\s+key\s+of\s+)(.{5,50}?)(?:\.|,|;|$)", "keys to developing a culture of allegiance"),
        (r"(the\s+\w+\s+stage\s+(?:of\s+)?.{3,40}?)(?:\.|,|;|$)", "stages of disloyalty"),
        (r"(the\s+sign\s+of\s+.{5,40}?)(?:\.|,|;|$)", "signs of disloyalty"),
        (r"(?:reason(?:s)?\s+(?:why|for)\s+)(.{5,60}?)(?:\.|,|;|$)", "reasons why the subject of loyalty is important"),
        (r"(mark(?:s)?\s+of\s+(?:godly\s+)?repentance.{0,40}?)(?:\.|,|;|$)", "marks of godly repentance"),
    ]

    # Reject prose-pattern items that start with a pronoun/common-subject word —
    # these are accidental matches of whole sentences, not actual list items.
    _PROSE_REJECT_RE = re.compile(
        r'^(?:you |we |it |this |that |some |jesus |i |there |they |your |he |she )',
        re.IGNORECASE,
    )
    # Trim body commentary after a Stage title.
    # "The Critical Stage A disloyal person…" → "The Critical Stage"
    # "The Political Stage When a person becomes political" → "The Political Stage"
    # Only fires when a capital word follows "Stage " (new sentence, not "of disloyalty").
    _STAGE_BODY_TRIM_RE = re.compile(r'(\bStage\b)(\s+[A-Z].+$)')

    for pat, group_name in patterns:
        for m in re.finditer(pat, text, re.IGNORECASE):
            t = m.group(1).strip().rstrip(".,;:!?") if m.group(1) else m.group(0).strip().rstrip(".,;:!?")
            # Skip pronoun-led prose fragments
            if _PROSE_REJECT_RE.match(t):
                continue
            # Trim body commentary that follows a Stage title
            t = _STAGE_BODY_TRIM_RE.sub(r'\1', t).strip()
            if 3 <= len(t.split()) <= 15:
                groups.setdefault(group_name, []).append(t)

    # Numbered points starting with infinitive or prepositional phrases are
    # the book’s explicit “reasons why loyalty is important” list.
    # They look like: “2. To fight the 5th column”, “3. For the love of God…”
    # \b\d+\. anchors to a word-boundary digit — no fragile lookbehind needed.
    _ORD_SUBS = [
        (re.compile(r'\b1st\b'), 'first'),
        (re.compile(r'\b2nd\b'), 'second'),
        (re.compile(r'\b3rd\b'), 'third'),
        (re.compile(r'\b4th\b'), 'fourth'),
        (re.compile(r'\b5th\b'), 'fifth'),
        (re.compile(r'\b6th\b'), 'sixth'),
        (re.compile(r'\b7th\b'), 'seventh'),
        (re.compile(r'\b8th\b'), 'eighth'),
    ]
    reason_items = []
    for m in re.finditer(
        r'\b\d{1,2}\.\s+((?:To |For |In order )[^.!?\n]{5,80})',
        text,
        re.MULTILINE,
    ):
        raw = m.group(1)
        item = _trim_reason_phrase(raw).rstrip('.,;:!?')
        for pat, repl in _ORD_SUBS:
            item = pat.sub(repl, item)
        if 3 <= len(item.split()) <= 12:
            reason_items.append(item)
    if len(reason_items) >= 3:
        groups.setdefault("reasons why the subject of loyalty is important", []).extend(reason_items)

    # Drop items that end with a bare digit (artefact from prose-pattern stopping at "1.").
    for k in list(groups):
        groups[k] = [t for t in groups[k] if not re.search(r'\d$', t)]

    for k in groups:
        groups[k] = _dedup(groups[k])
    return {k: v for k, v in groups.items() if len(v) >= 3}


# Names that are different labels for the same biblical entity.
# When multiple names in a group appear in the text, keep only the
# canonical (first listed) form so both don't appear as separate
# options in the same question.
_NAME_ALIAS_GROUPS: list[list[str]] = [
    ["Lucifer", "Satan"],   # the dragon / the devil / Lucifer / Satan — one entity
]

# Categorise names so _q_names picks semantically correct options.
# 'rebel': disloyal / betrayed their leader.
# 'loyal': showed loyalty / stayed faithful.
_REBEL_NAMES: frozenset = frozenset({
    "Lucifer", "Satan", "Absalom", "Ahithophel", "Judas", "Joab",
    "Shemei", "Korah", "Dathan", "Abiram", "Diotrephes", "Demas",
    "Alexander", "Jezebel", "Miriam", "Ziba", "Laban", "Esau",
})
_LOYAL_NAMES: frozenset = frozenset({
    "David", "Zadok", "Ahimaaz", "Barnabas", "Paul", "Peter",
    "Timothy", "Titus", "Philemon", "Jonathan", "Samuel", "Moses",
    "Eli", "Gehazi", "Aaron", "Jacob",
})
# Topic keywords that determine which pool is 'correct' in _q_names.
_REBEL_TOPIC_KEYWORDS = ("betray", "rebel", "disloy", "eighth stage", "independent spirit")
_LOYAL_TOPIC_KEYWORDS = ("loyal", "faithful", "allegian", "characters who showed")


def _extract_names(text: str) -> list:
    """Extract biblical character names."""
    # Common biblical names that appear in Loyalty & Disloyalty
    biblical_names = [
        "Absalom", "Ahithophel", "Ahimaaz", "Shemei", "Ziba", "Zadok",
        "Joab", "David", "Judas", "Moses", "Aaron", "Miriam", "Korah",
        "Dathan", "Abiram", "Saul", "Jonathan", "Samuel", "Eli",
        "Gehazi", "Elisha", "Diotrephes", "Barnabas", "Paul", "Peter",
        "Timothy", "Titus", "Philemon", "Demas", "Alexander",
        "Jezebel", "Lucifer", "Satan", "Jacob", "Laban", "Esau",
    ]
    found = []
    for name in biblical_names:
        if name.lower() in text.lower() and name not in found:
            found.append(name)
    # Deduplicate aliases: if more than one name from a group appears, keep
    # only the canonical (first-in-group) form.
    shadowed: set[str] = set()
    for group in _NAME_ALIAS_GROUPS:
        first_found = next((n for n in group if n in found), None)
        if first_found:
            for name in group:
                if name != first_found:
                    shadowed.add(name)
    return [n for n in found if n not in shadowed]


# ── Question builders ──────────────────────────────────────────────────────

def _build_opts(true_items: list, false_items: list, rng: random.Random):
    items = [(t, True) for t in true_items] + [(f, False) for f in false_items]
    rng.shuffle(items)
    opts = {LABELS[i]: items[i][0] for i in range(5)}
    ans = {LABELS[i]: items[i][1] for i in range(5)}
    return opts, ans


_STOPWORDS = frozenset({
    "a", "an", "the", "and", "or", "but", "of", "to", "in", "on", "at", "for", "with",
    "from", "into", "over", "under", "as", "by", "is", "are", "was", "were", "be", "been",
    "being", "that", "this", "these", "those", "it", "its", "his", "her", "their", "our",
    "your", "my", "we", "you", "i", "he", "she", "they", "not",
})

_META_PREFIXES_GLEANED = (
    "it is my prayer", "let us all", "the answer is",
    "as i said", "i believe", "i have seen", "i have rarely",
    "i have often", "i have wondered", "i have known",
    "what about", "why is", "this is why",
    "in other words", "this is another reason", "we all",
    "this will invite", "it cannot possibly", "the reason why",
    "it is important to note", "please note", "note that",
    "you will notice", "you will see", "you will find",
)


def _norm_key(s: str) -> str:
    """Normalize an option/statement/quote for dedup + overlap checks."""
    s = (s or "").strip().lower()
    s = s.replace("\u2019", "'").replace("\u2018", "'")
    s = s.replace("\u201c", '"').replace("\u201d", '"')
    s = re.sub(r"[\"'`]+", "", s)
    s = re.sub(r"[^a-z0-9\s]", " ", s)
    s = re.sub(r"\s+", " ", s).strip()
    return s


def _token_set(s: str) -> set:
    return {t for t in _norm_key(s).split() if t and t not in _STOPWORDS}


def _jaccard(a: set, b: set) -> float:
    if not a and not b:
        return 1.0
    if not a or not b:
        return 0.0
    return len(a & b) / len(a | b)


def _too_similar(a: str, b: str, threshold: float = 0.86) -> bool:
    """Detect near-duplicates (including 'X increasing / Y decreasing' reversals)."""
    na, nb = _norm_key(a), _norm_key(b)
    if not na or not nb:
        return False
    if na == nb:
        return True
    if na in nb or nb in na:
        return True
    return _jaccard(_token_set(a), _token_set(b)) >= threshold


def _dedup_norm(items: list[str]) -> list[str]:
    out = []
    seen = set()
    for it in items:
        k = _norm_key(it)
        if not k or k in seen:
            continue
        seen.add(k)
        out.append(it)
    return out


def _sample_diverse(pool: list[str], k: int, rng: random.Random, used: list[str] | None = None) -> list[str]:
    """Greedy sample that avoids near-duplicates against itself and `used`."""
    used = used or []
    rng.shuffle(pool)
    picked = []
    for cand in pool:
        if any(_too_similar(cand, p) for p in picked):
            continue
        if any(_too_similar(cand, u) for u in used):
            continue
        picked.append(cand)
        if len(picked) >= k:
            return picked
    # Fallback: no diversity possible, return simple sample if available.
    if len(pool) >= k:
        return pool[:k]
    return picked


def _build_tf_options(true_pool: list[str], false_pool: list[str], rng: random.Random,
                      min_true: int = 2, max_true: int = 3) -> tuple[dict, dict] | tuple[None, None]:
    """Build 5 T/F options with hard guarantees:

    - At least 1 True and 1 False
    - No normalized duplicates
    - Avoid near-duplicates where possible
    """
    true_pool = _dedup_norm(list(true_pool or []))
    false_pool = _dedup_norm(list(false_pool or []))

    true_keys = {_norm_key(x) for x in true_pool}
    false_pool = [x for x in false_pool if _norm_key(x) not in true_keys]

    if not true_pool or not false_pool:
        return None, None

    total = 5
    candidates = []
    for nt in range(min_true, max_true + 1):
        nf = total - nt
        if 1 <= nt <= len(true_pool) and 1 <= nf <= len(false_pool):
            candidates.append(nt)
    if not candidates:
        for nt in range(1, total):
            nf = total - nt
            if 1 <= nt <= len(true_pool) and 1 <= nf <= len(false_pool):
                candidates.append(nt)
    if not candidates:
        return None, None

    nt = rng.choice(candidates)
    nf = total - nt

    tp = _sample_diverse(true_pool, nt, rng)
    fp = _sample_diverse(false_pool, nf, rng, used=tp)
    if len(tp) != nt or len(fp) != nf:
        return None, None

    opts, ans = _build_opts(tp, fp, rng)
    keys = [_norm_key(v) for v in opts.values()]
    if len(set(keys)) != total:
        return None, None
    if not (any(ans.values()) and not all(ans.values())):
        return None, None
    return opts, ans


def _quote_ok(q: str) -> bool:
    q = (q or "").strip()
    if not q:
        return False
    # Avoid ultra-common tiny fragments like "Well done" that appear in many verses.
    if len(q.split()) < 3:
        return False
    if len(q) < 10:
        return False
    if _SCRIPTURE_RE.search(q):
        return False
    return True


def _is_gleaned_candidate(s: str) -> bool:
    s = (s or "").strip().rstrip(".,;:!?")
    if not s:
        return False
    if _SCRIPTURE_RE.search(s):
        return False
    if "…" in s or "..." in s:
        return False
    wc = len(s.split())
    if wc < 6 or wc > 30:
        return False
    s_lower = s.lower()
    if any(s_lower.startswith(p) for p in _META_PREFIXES_GLEANED):
        return False
    # Require some specificity: enough non-stopword content tokens.
    tokens = [t for t in re.findall(r"[a-z]{4,}", s_lower) if t not in _STOPWORDS]
    if len(set(tokens)) < 5:
        return False
    return True


def _mkq(stem, opts, ans, ref_str, context=""):
    return {
        "question": stem, "options": opts, "answers": ans,
        "source": {"text": context, "reference": ref_str},
    }


# T1/T2: "[Ref] talks about" / "[Ref] does not talk about"
def _q_talks_about(ref, all_topics, rng, negated=False):
    my = _dedup_norm(ref.topics[:10])
    my_keys = {_norm_key(t) for t in my}
    other = [t for t in _dedup_norm(all_topics) if _norm_key(t) not in my_keys]
    if len(my) < 1 or len(other) < 3:
        return None

    verb = "does not talk about" if negated else "talks about"
    stem = f"{ref.full_ref}: {verb}"

    true_pool = other if negated else my
    false_pool = my if negated else other

    opts, ans = _build_tf_options(true_pool, false_pool, rng, min_true=2, max_true=3)
    if not opts:
        return None
    verse_text = ref.paired_quotes[0] if ref.paired_quotes else (ref.commentary[0] if ref.commentary else "")
    return _mkq(stem, opts, ans, ref.full_ref, verse_text)


# T3/T4: "[Ref] is [not] the biblical basis of"
def _q_biblical_basis(ref, all_teachings, rng, negated=False):
    # Prefer explicit numbered teaching points; fall back to commentary only
    # when it reads like a discrete teaching statement.
    my_pool = list(ref.teaching_points or [])
    if not my_pool:
        # Commentary fallback: only keep teaching-like statements.
        my_pool = [c for c in (ref.commentary or []) if re.search(r"\b(?:is|are|demands|requires|means|involves|stage|sign|key|mark)\b", c, re.IGNORECASE)]

    my = _dedup_norm(my_pool[:10])
    # Exclude ALL of this ref's teaching points/commentary from the wrong pool
    # (avoid a ref's own items leaking into its false options via slicing).
    exclude = {_norm_key(t) for t in _dedup_norm(my_pool)}
    other = [t for t in _dedup_norm(all_teachings) if _norm_key(t) not in exclude]

    if len(my) < 1 or len(other) < 3:
        return None

    neg = "not " if negated else ""
    stem = f"{ref.full_ref} is {neg}the biblical basis of"

    true_pool = other if negated else my
    false_pool = my if negated else other
    # Non-negated: typically fewer True options reads better.
    if negated:
        opts, ans = _build_tf_options(true_pool, false_pool, rng, min_true=2, max_true=3)
    else:
        opts, ans = _build_tf_options(true_pool, false_pool, rng, min_true=1, max_true=2)
    if not opts:
        return None

    ctx = (ref.paired_quotes[0] if ref.paired_quotes else None) or (my[0] if my else "")
    return _mkq(stem, opts, ans, ref.full_ref, ctx)


# T5/T6: "The following quotations can[not] be found in [Ref]"
def _q_quotation(ref, all_quotes_flat, rng, negated=False, quote_index: dict | None = None):
    my_all = [q for q in (ref.paired_quotes or []) if _quote_ok(q)]
    if quote_index:
        # Prefer quotes that uniquely belong to this reference.
        uniq = [q for q in my_all if quote_index.get(_norm_key(q), set()) == {ref.full_ref}]
        my_all = uniq or my_all

    my = _dedup_norm(my_all[:10])
    my_keys = {_norm_key(q) for q in my}
    other = [q for q in _dedup_norm(all_quotes_flat) if _norm_key(q) not in my_keys and _quote_ok(q)]

    # Need at least 1 quote from this ref and enough other quotes to build 5 options.
    if len(my) < 1 or len(other) < 3:
        return None

    verb = "cannot" if negated else "can"
    stem = f"The following quotations {verb} be found in {ref.full_ref}"

    true_pool = other if negated else my
    false_pool = my if negated else other
    opts, ans = _build_tf_options(true_pool, false_pool, rng, min_true=1 if not negated else 2, max_true=2 if not negated else 3)
    if not opts:
        return None

    return _mkq(stem, opts, ans, ref.full_ref, "; ".join(my[:2]))


# T7/T8: 'The scripture "…" can[not] be found in' → tricky similar refs
def _q_scripture_found(ref, quote, all_refs, rng, negated=False):
    wrong = _tricky_wrong_refs(ref, all_refs, rng, n=4)
    if len(wrong) < 4:
        return None
    verb = "cannot" if negated else "can"
    stem = f'The scripture "{quote}" {verb} be found in'
    if negated:
        # True  = wrong refs (scripture genuinely CANNOT be found there)
        # False = correct ref (scripture CAN be found → "cannot" is False)
        opts, ans = _build_opts(wrong, [ref.full_ref], rng)
    else:
        opts, ans = _build_opts([ref.full_ref], wrong, rng)
    return _mkq(stem, opts, ans, ref.full_ref, quote)


# T9/T10: 'The statement "…" can[not] be gleaned from' → tricky refs
# Numbered-point reason phrases like "For the love of God to fill the church"
# are dependent clauses. Prefix them so the stem is a complete sentence:
#   "Loyalty is important for the love of God to fill the church"
_INCOMPLETE_REASON_RE = re.compile(r'^(?:To |For (?:the )?|In order to )', re.IGNORECASE)

# Words that typically open body-commentary sentences appended right after a reason title.
# Used by _trim_reason_phrase to strip that suffix.
_BODY_STARTER_RE = re.compile(
    r'\s+(?=(?:Very|The|One|As|Those|But|This|Each|When|While|If|Many|Most|Now'
    r'|We|You|He|She|They|Your|My|Our|I)\b)'
)


def _trim_reason_phrase(text: str) -> str:
    """Strip body-commentary suffix from an extracted infinitive reason phrase.

    Reason titles like 'To fight the fifth column' are followed directly
    (without any punctuation) by body text like 'Very early in my ministry…'.
    This function truncates at the first sentence-opening word that follows
    the infinitive prefix (first 12 chars are skipped to avoid trimming within
    the prefix itself).
    """
    m = _BODY_STARTER_RE.search(text, 12)
    if m:
        return text[: m.start()].strip()
    return text.strip()


def _q_gleaned_from(ref, statement, all_refs, rng, negated=False):
    stmt = (statement or "").strip().rstrip(".,;:!?")
    if _INCOMPLETE_REASON_RE.match(stmt):
        # Make dependent-clause reason phrases read as complete statements
        # without injecting book-specific wording.
        stmt = "It is important " + stmt[0].lower() + stmt[1:]
    if not _is_gleaned_candidate(stmt):
        return None

    wrong = _tricky_wrong_refs(ref, all_refs, rng, n=4)
    if len(wrong) < 4:
        return None

    verb = "cannot" if negated else "can"
    stem = f'The statement "{stmt}" {verb} be gleaned from'
    if negated:
        # True  = wrong refs (statement genuinely CANNOT be gleaned from them)
        # False = correct ref (statement CAN be gleaned → "cannot" is False)
        opts, ans = _build_opts(wrong, [ref.full_ref], rng)
    else:
        opts, ans = _build_opts([ref.full_ref], wrong, rng)
    return _mkq(stem, opts, ans, ref.full_ref, stmt)


# T10/T11: "According to various texts / several authorities on the Doctrine of …,
#            the following are [not] [topic]"
_ACCORDING_TO_STEMS = [
    "According to the book",
    "Based on the book",
    "From the book",
    "In the book",
]


def _q_according_to(book_title, topic, correct, wrong, rng, negated=False):
    correct = _dedup_norm(list(correct or []))
    wrong = _dedup_norm(list(wrong or []))
    if len(correct) < 1 or len(wrong) < 3:
        return None

    neg = "not " if negated else ""
    intro = rng.choice(_ACCORDING_TO_STEMS)
    stem = f"{intro} {book_title}, the following are {neg}{topic}"

    true_pool = wrong if negated else correct
    false_pool = correct if negated else wrong

    opts, ans = _build_tf_options(true_pool, false_pool, rng, min_true=2, max_true=3)
    if not opts:
        return None
    return _mkq(stem, opts, ans, book_title, f"See {book_title}")


# T12: Name-based: "the following are [not] rebels/characters who [X]"
def _q_names(book_title, topic, correct_names, wrong_names, rng, negated=False):
    """Generate a question about biblical characters matching (or not) a topic.

    Correct names are drawn from the semantically-right pool for the topic
    (rebels for betrayal topics, loyal for loyalty topics).  Wrong names
    are drawn from the opposite pool.
    """
    # Re-sort correct/wrong based on topic semantics so David never appears
    # as a 'betrayer' and Absalom never appears as a 'loyal character'.
    topic_lower = topic.lower()
    if any(kw in topic_lower for kw in _REBEL_TOPIC_KEYWORDS):
        true_pool  = [n for n in correct_names + wrong_names if n in _REBEL_NAMES]
        false_pool = [n for n in correct_names + wrong_names if n in _LOYAL_NAMES]
    elif any(kw in topic_lower for kw in _LOYAL_TOPIC_KEYWORDS):
        true_pool  = [n for n in correct_names + wrong_names if n in _LOYAL_NAMES]
        false_pool = [n for n in correct_names + wrong_names if n in _REBEL_NAMES]
    else:
        true_pool, false_pool = correct_names, wrong_names
    if not true_pool or not false_pool:
        true_pool, false_pool = correct_names, wrong_names  # fall back to caller's pools
    if len(true_pool) < 1 or len(false_pool) < 3:
        return None
    neg = "not " if negated else ""
    intro = rng.choice(_ACCORDING_TO_STEMS)
    stem = f"{intro} {book_title}, the following are {neg}{topic}"
    if negated:
        nt = rng.randint(2, 3)
        nf = 5 - nt
        tp, fp = false_pool, true_pool   # negated: true items are the WRONG pool
    else:
        nt = rng.randint(2, 3)
        nf = 5 - nt
        tp, fp = true_pool, false_pool
    if len(tp) < nt or len(fp) < nf:
        nt = min(nt, len(tp))
        nf = min(nf, len(fp))
        if nt + nf < 5:
            return None
    opts, ans = _build_opts(rng.sample(tp, k=nt), rng.sample(fp, k=nf), rng)
    return _mkq(stem, opts, ans, book_title, f"See {book_title}")


# ── Pool generation ────────────────────────────────────────────────────────

def generate_question_pool(chapter, pool_size=None, seed=None, config=None, global_teachings=None, global_patterned_items=None, global_patterned_by_group=None):
    """Generate a UO-SAT-style question pool for one chapter.

    The pool size is automatically scaled so that every scripture reference in
    the chapter receives at least one question.  The caller-supplied pool_size
    (or 15 as the default) acts as a *minimum*; the actual count may be higher
    when the chapter contains more refs than that minimum.

    Notes for this book's exam style:
    - Many items are answered via per-option True/False (UO-SAT). Question
      builders must avoid duplicates and near-duplicates, and must include at
      least one True and one False option.
    """
    rng = random.Random(seed)
    book_title = (config or {}).get("book_title") or "the book"

    refs = _extract_refs_with_context(chapter.text)
    all_teachings = _extract_teachings(chapter.text)
    patterned = _extract_patterned_lists(chapter.text)
    names = _extract_names(chapter.text)

    # Scale target so every ref can get a question.
    # At least (pool_size or 15), but never fewer than the number of refs.
    base_target = pool_size or 15
    target = max(base_target, len(refs))

    # Merge teaching_points from all refs into all_teachings pool
    # This ensures FALSE options for biblical-basis questions are real
    # teaching points from OTHER refs (not random fragments).
    all_teachings = _dedup(
        all_teachings + [tp for r in refs for tp in r.teaching_points]
    )

    # Supplement with cross-chapter teachings so that biblical-basis FALSE
    # options can include topics from other chapters (e.g. "The execution
    # stage of disloyalty" as a distractor for a ch1 verse question).
    # Patterned-list items (reason phrases, stage names) are intentionally
    # excluded here to avoid them appearing as biblical-basis options.
    if global_teachings:
        local_set = set(t.lower() for t in all_teachings)
        all_teachings = _dedup(
            all_teachings + [t for t in global_teachings if t.lower() not in local_set]
        )

    # Build a combined patterned-item pool for According-to wrong options.
    # Prefer same-group cross-chapter items when available.
    extra_patterned = list(global_patterned_items or [])
    global_patterned_by_group = global_patterned_by_group or {}

    # Flat pools for wrong answers
    all_topics = _dedup([t for r in refs for t in r.topics])
    all_quotes = _dedup([q for r in refs for q in r.paired_quotes if _quote_ok(q)])

    # Quote index (normalized quote -> set of refs that contain it). Used to
    # avoid ambiguous quote/ref questions.
    quote_index: dict[str, set] = {}
    for r in refs:
        for q in (r.paired_quotes or []):
            if not _quote_ok(q):
                continue
            k = _norm_key(q)
            quote_index.setdefault(k, set()).add(r.full_ref)

    questions = []
    qid = 1

    def _add(q):
        nonlocal qid
        if q is None or len(questions) >= target:
            return False
        q["id"] = f"ch{chapter.chapter_id:03d}_q{qid:03d}"
        q["chapter_id"] = chapter.chapter_id
        ratio = qid / max(target, 1)
        q["difficulty"] = "easy" if ratio < 0.33 else "medium" if ratio < 0.66 else "hard"
        questions.append(q)
        qid += 1
        return True

    rng.shuffle(refs)

    # Weights: talks, !talks, basis, !basis, quot, !quot, scrip, !scrip, glean, !glean, acc, !acc, names
    WEIGHTS = [3, 2, 2, 2, 4, 3, 3, 1, 3, 2, 2, 1, 1]

    def _try(ref):
        t = rng.choices(range(13), weights=WEIGHTS, k=1)[0]

        if t == 0:
            return _q_talks_about(ref, all_topics, rng)
        if t == 1:
            return _q_talks_about(ref, all_topics, rng, negated=True)
        if t == 2:
            return _q_biblical_basis(ref, all_teachings, rng)
        if t == 3:
            return _q_biblical_basis(ref, all_teachings, rng, negated=True)
        if t == 4 and ref.paired_quotes:
            return _q_quotation(ref, all_quotes, rng, quote_index=quote_index)
        if t == 5 and ref.paired_quotes:
            return _q_quotation(ref, all_quotes, rng, negated=True, quote_index=quote_index)
        if t == 6 and ref.paired_quotes:
            qs = [q for q in ref.paired_quotes if _quote_ok(q)]
            if quote_index:
                uniq = [q for q in qs if quote_index.get(_norm_key(q), set()) == {ref.full_ref}]
                qs = uniq or qs
            if not qs:
                return None
            return _q_scripture_found(ref, rng.choice(qs), refs, rng)
        if t == 7 and ref.paired_quotes:
            qs = [q for q in ref.paired_quotes if _quote_ok(q)]
            if quote_index:
                uniq = [q for q in qs if quote_index.get(_norm_key(q), set()) == {ref.full_ref}]
                qs = uniq or qs
            if not qs:
                return None
            return _q_scripture_found(ref, rng.choice(qs), refs, rng, negated=True)
        if t == 8 and (ref.commentary or ref.teaching_points):
            pool = [s for s in (ref.teaching_points or []) + (ref.commentary or []) if _is_gleaned_candidate(s)]
            if not pool:
                return None
            stmt = rng.choice(pool)
            return _q_gleaned_from(ref, stmt, refs, rng)
        if t == 9 and (ref.commentary or ref.teaching_points):
            pool = [s for s in (ref.teaching_points or []) + (ref.commentary or []) if _is_gleaned_candidate(s)]
            if not pool:
                return None
            stmt = rng.choice(pool)
            return _q_gleaned_from(ref, stmt, refs, rng, negated=True)
        if t == 10 and patterned:
            gn = rng.choice(list(patterned.keys()))
            items = patterned[gn]
            # Prefer same-group global patterned items as distractors.
            same_group = [x for x in global_patterned_by_group.get(gn, []) if x not in items]
            wp = same_group or [i for grp in patterned.values() for i in grp if i not in items]
            # Supplement with legacy cross-chapter patterned items as additional distractors.
            wp = _dedup(wp + [x for x in extra_patterned if x not in items and x not in wp])
            if not wp:
                wp = all_topics[:10]
            return _q_according_to(book_title, gn, items, wp, rng)
        if t == 11 and patterned:
            gn = rng.choice(list(patterned.keys()))
            items = patterned[gn]
            same_group = [x for x in global_patterned_by_group.get(gn, []) if x not in items]
            wp = same_group or [i for grp in patterned.values() for i in grp if i not in items]
            wp = _dedup(wp + [x for x in extra_patterned if x not in items and x not in wp])
            if not wp:
                wp = all_topics[:10]
            return _q_according_to(book_title, gn, items, wp, rng, negated=True)
        if t == 12 and len(names) >= 5:
            topic = rng.choice([
                "rebels who ended up at the eighth stage of disloyalty",
                "characters who showed loyalty",
                "people who betrayed their leaders",
            ])
            cn = rng.sample(names, k=min(3, len(names)))
            wn = [n for n in names if n not in cn]
            if len(wn) < 2:
                wn = ["Zadok", "Ahimaaz", "Hushai", "Ittai"]
            return _q_names(book_title, topic, cn, wn, rng, negated=rng.choice([True, False]))
        return None

    def _try_any(ref):
        """Exhaust all question types for this ref until one yields a question.

        Used in the first pass to guarantee every ref gets at least one question.
        Types are tried in rough priority order: scripture_found first (most
        specific), then biblical_basis / talks_about (always possible), then
        gleaned_from (needs context text).
        """
        # --- scripture / quotation types (need paired_quotes) ---
        if ref.paired_quotes:
            qs = [q for q in ref.paired_quotes if _quote_ok(q)]
            if quote_index:
                uniq = [q for q in qs if quote_index.get(_norm_key(q), set()) == {ref.full_ref}]
                qs = uniq or qs
            if qs:
                q = _q_scripture_found(ref, rng.choice(qs), refs, rng)
                if q:
                    return q
            q = _q_quotation(ref, all_quotes, rng, quote_index=quote_index)
            if q:
                return q
        # --- basis / talks (always fallback-available) ---
        for neg in (False, True):
            q = _q_biblical_basis(ref, all_teachings, rng, negated=neg)
            if q:
                return q
            q = _q_talks_about(ref, all_topics, rng, negated=neg)
            if q:
                return q
        # --- gleaned-from (needs commentary / teaching points) ---
        pool = [s for s in (ref.teaching_points or []) + (ref.commentary or []) if _is_gleaned_candidate(s)]
        if pool:
            for neg in (False, True):
                q = _q_gleaned_from(ref, rng.choice(pool), refs, rng, negated=neg)
                if q:
                    return q
        return None

    # ── First pass: guarantee one question per scripture ref ──────────────
    # No early-break so every ref is attempted regardless of target.
    for ref in refs:
        _add(_try_any(ref))

    # ── Second pass: fill remaining slots with weighted-random types ──────
    attempts = 0
    while len(questions) < target and refs and attempts < target * 10:
        attempts += 1
        ref = rng.choice(refs)
        _add(_try(ref))

    # ── Fallback: generic According-to questions if still short ──────────
    if len(questions) < target:
        dummy_topics = all_teachings or all_topics
        dummy_wrong = all_topics or all_teachings
        fallback_attempts = 0
        fallback_max = (target - len(questions)) * 10
        while len(questions) < target and dummy_topics and dummy_wrong and fallback_attempts < fallback_max:
            topic = rng.choice([
                "qualities of a good leader",
                "signs of poor leadership",
                "reasons why good character is important",
                "common leadership mistakes",
                "keys to effective leadership",
            ])
            fallback_attempts += 1
            cn = rng.sample(dummy_topics[:15], k=min(3, len(dummy_topics)))
            cw = rng.sample(dummy_wrong[:20], k=min(4, len(dummy_wrong)))
            _add(_q_according_to(book_title, topic, cn, cw, rng, negated=rng.choice([True, False])))

    return questions


def generate_all_chapter_questions(chapters, pool_size=None, seed=None, book_title=None):
    """Generate question pools for all chapters."""
    master_rng = random.Random(seed)

    # First pass: collect all teachings and patterned-list items from every
    # chapter so they can be used as cross-chapter FALSE options.
    # Patterned-list items are kept SEPARATE so they don't pollute the
    # biblical-basis wrong-option pool with reason-phrase / stage items.
    global_teachings = []
    global_patterned_items = []
    global_patterned_by_group: dict[str, list[str]] = {}
    for chapter in chapters:
        global_teachings.extend(_extract_teachings(chapter.text))
        refs = _extract_refs_with_context(chapter.text)
        global_teachings.extend(tp for r in refs for tp in r.teaching_points)
        pat = _extract_patterned_lists(chapter.text)
        for group_name, items in pat.items():
            global_patterned_items.extend(items)   # legacy flat list
            global_patterned_by_group.setdefault(group_name, []).extend(items)
    global_teachings = _dedup(global_teachings)
    global_patterned_items = _dedup(global_patterned_items)
    for k in list(global_patterned_by_group):
        global_patterned_by_group[k] = _dedup(global_patterned_by_group[k])

    output = {}
    for chapter in chapters:
        ch_seed = master_rng.randint(1, 1_000_000)
        output[chapter.chapter_id] = generate_question_pool(
            chapter=chapter, pool_size=pool_size, seed=ch_seed,
            config={"book_title": book_title} if book_title else None,
            global_teachings=global_teachings,
            global_patterned_items=global_patterned_items,
            global_patterned_by_group=global_patterned_by_group,
        )
    return output
