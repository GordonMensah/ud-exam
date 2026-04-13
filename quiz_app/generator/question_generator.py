"""Question generation logic for scripture-focused exam-style questions.

Generates questions matching the UO-SAT exam format:
- "The following quotations can be found in [Scripture ref]"
- "The following quotations cannot be found in [Scripture ref]"
- "[Scripture ref] is the biblical basis of"
- "[Scripture ref] is not the biblical basis of"
- "[Scripture ref] talks about"
- 'The scripture "..." can be found in'
- 'The statement "..." can be gleaned from'
- "According to several authorities on [Book], the following are [topic]"
"""

from __future__ import annotations

import random
import re
from dataclasses import dataclass
from typing import Any, List, Optional, Tuple

from .epub_parser import Chapter

# ── Scripture reference extraction ──────────────────────────────────────────

_BOOK_NAMES = (
    # ── English ──────────────────────────────────────────────────────────
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
    # ── Portuguese ───────────────────────────────────────────────────────
    r"Gênesis|Êxodo|Ex|Levítico|Números|"
    r"Deuteronômio|Josué|Juízes|Rute|"
    r"1\s*Samuel|2\s*Samuel|1\s*Reis|2\s*Reis|"
    r"1\s*Crônicas|2\s*Crônicas|Esdras|Neemias|Ester|"
    r"Jó|Salmos|Provérbios|Eclesiastes|"
    r"Cânticos|Isaías|Jeremias|Lamentações|Ezequiel|Daniel|"
    r"Oséias|Joel|Amós|Obadias|Jonas|Miquéias|Naum|Habacuque|"
    r"Sofonias|Ageu|Zacarias|Malaquias|"
    r"Mateus|Marcos|Lucas|João|Atos|Romanos|"
    r"1\s*Coríntios|2\s*Coríntios|Gálatas|Efésios|Filipenses|"
    r"Colossenses|1\s*Tessalonicenses|2\s*Tessalonicenses|"
    r"1\s*Timóteo|2\s*Timóteo|Tito|Filemom|Hebreus|Tiago|"
    r"1\s*Pedro|2\s*Pedro|1\s*João|2\s*João|3\s*João|Judas|Apocalipse"
)

_SCRIPTURE_RE = re.compile(
    rf"(?:({_BOOK_NAMES})\s+(\d+)\s*:\s*(\d+)(?:\s*[-\u2013]\s*(\d+))?)",
    re.IGNORECASE,
)

_QUOTED_TEXT_RE = re.compile(r'["\u201c\u201d]([^"\u201c\u201d]{10,120})["\u201c\u201d]')

_SENTENCE_SPLIT_RE = re.compile(r"(?<=[.!?])\s+")


@dataclass
class ScriptureRef:
    """A parsed scripture reference with surrounding context."""

    book: str
    chapter: int
    verse_start: int
    verse_end: int
    full_ref: str
    context_sentence: str
    nearby_text: str


@dataclass
class QuestionConfig:
    """Question generation settings."""

    pool_min: int = 10
    pool_max: int = 20
    default_pool_size: int = 15
    min_sentence_length: int = 30


def _normalize_ref(book: str, chapter: int, v_start: int, v_end: int) -> str:
    base = f"{book} {chapter}:{v_start}"
    if v_end and v_end != v_start:
        base += f"-{v_end}"
    return base


def _get_surrounding_text(full_text: str, start: int, end: int, window: int = 400) -> str:
    s = max(0, start - window)
    e = min(len(full_text), end + window)
    return full_text[s:e].strip()


def _get_sentence_containing(full_text: str, start: int, end: int) -> str:
    s = full_text.rfind(".", 0, start)
    s = s + 1 if s != -1 else 0
    e = full_text.find(".", end)
    e = e + 1 if e != -1 else len(full_text)
    return full_text[s:e].strip()


# ── Extraction helpers ──────────────────────────────────────────────────────

def extract_scripture_refs(text: str) -> list:
    """Find all scripture references in text with surrounding context."""
    refs = []
    seen = set()
    for m in _SCRIPTURE_RE.finditer(text):
        book = m.group(1).strip()
        ch = int(m.group(2))
        vs = int(m.group(3))
        ve = int(m.group(4)) if m.group(4) else vs
        full = _normalize_ref(book, ch, vs, ve)
        if full in seen:
            continue
        seen.add(full)
        refs.append(ScriptureRef(
            book=book, chapter=ch, verse_start=vs, verse_end=ve,
            full_ref=full,
            context_sentence=_get_sentence_containing(text, m.start(), m.end()),
            nearby_text=_get_surrounding_text(text, m.start(), m.end()),
        ))
    return refs


def _extract_short_phrases(text: str, min_len: int = 15, max_len: int = 90) -> list:
    """Extract short, meaningful phrases from text near a scripture.

    These are actual sentence fragments from the book — the kind of thing
    that sounds like it could be a quotation from a verse.
    """
    phrases = []
    # 1. Actual quoted text in the book (curly/straight quotes)
    for m in _QUOTED_TEXT_RE.finditer(text):
        p = m.group(1).strip()
        if min_len <= len(p) <= max_len:
            phrases.append(p)

    # 2. Short sentence fragments (split on period/semicolon)
    for sent in re.split(r"[.;!?]", text):
        sent = sent.strip()
        if not sent:
            continue
        # Also split on commas to get sub-clauses
        for clause in re.split(r",\s+(?:and\s+|but\s+|or\s+|for\s+|that\s+)?", sent):
            clause = clause.strip()
            if min_len <= len(clause) <= max_len and not _SCRIPTURE_RE.search(clause):
                phrases.append(clause)

    # Deduplicate while keeping order
    seen = set()
    unique = []
    for p in phrases:
        low = p.lower()
        if low not in seen:
            seen.add(low)
            unique.append(p)
    return unique


def _extract_teachings(text: str) -> list:
    """Extract teaching-style phrases like 'you must...', 'a loyal...',
    'the sign of...' etc — things that could be right or wrong answers
    about what a passage teaches.
    """
    teachings = []
    patterns = [
        r"((?:you|we)\s+(?:must|should|need\s+to|ought\s+to|have\s+to)\s+.{10,80}?)(?:\.|,|;|$)",
        r"(it\s+is\s+(?:important|necessary|essential|wrong|right)\s+to\s+.{10,80}?)(?:\.|,|;|$)",
        r"(a\s+(?:loyal|disloyal|faithful|unfaithful|good|bad)\s+\w+\s+.{10,80}?)(?:\.|,|;|$)",
        r"(the\s+(?:sign|mark|characteristic|quality|trait)\s+of\s+.{10,80}?)(?:\.|,|;|$)",
    ]
    for pat in patterns:
        for m in re.finditer(pat, text, re.IGNORECASE):
            t = m.group(1).strip().rstrip(".,;")
            if 15 < len(t) < 100:
                teachings.append(t)

    # Deduplicate
    seen = set()
    unique = []
    for t in teachings:
        low = t.lower()
        if low not in seen:
            seen.add(low)
            unique.append(t)
    return unique


def _extract_concepts(text: str) -> list:
    """Extract concept phrases for 'according to' and 'biblical basis' templates."""
    concepts = []
    patterns = [
        r"the\s+(?:biblical\s+)?(?:basis|foundation|principle)\s+of\s+(.{5,60}?)(?:\.|,|;)",
        r"(?:talks?\s+about|refers?\s+to|speaks?\s+of|deals?\s+with)\s+(.{5,60}?)(?:\.|,|;)",
        r"(?:the\s+)?(?:doctrine|concept|principle|stage|sign|reason)\s+of\s+(.{5,60}?)(?:\.|,|;)",
        r"(?:is\s+about|concerns|addresses)\s+(.{5,60}?)(?:\.|,|;)",
    ]
    for pattern in patterns:
        for m in re.finditer(pattern, text, re.IGNORECASE):
            c = m.group(1).strip()
            if len(c) > 5:
                concepts.append(c)
    return concepts


# ── Question template builders ─────────────────────────────────────────────

def _shuffle_build(
    true_items: list, false_items: list, rng: random.Random,
) -> tuple:
    """Build 5 options dict + answers dict from true/false item lists."""
    labels = ["a", "b", "c", "d", "e"]
    items = [(t, True) for t in true_items] + [(f, False) for f in false_items]
    rng.shuffle(items)
    options = {labels[i]: items[i][0] for i in range(5)}
    answers = {labels[i]: items[i][1] for i in range(5)}
    return options, answers


def _build_quotation_q(
    ref: ScriptureRef,
    correct_phrases: list,
    wrong_phrases: list,
    rng: random.Random,
    negated: bool = False,
) -> dict:
    """'The following quotations can/cannot be found in [Ref]'

    Options are short phrases — some actually near the verse, some from
    other parts of the book.
    """
    if len(correct_phrases) < 2 or len(wrong_phrases) < 2:
        return None

    if negated:
        stem = f"The following quotations cannot be found in {ref.full_ref}"
        nt = rng.randint(2, 3)
        nf = 5 - nt
        tp, fp = wrong_phrases, correct_phrases
    else:
        stem = f"The following quotations can be found in {ref.full_ref}"
        nt = rng.randint(2, 3)
        nf = 5 - nt
        tp, fp = correct_phrases, wrong_phrases

    if len(tp) < nt or len(fp) < nf:
        return None
    opts, ans = _shuffle_build(rng.sample(tp, k=nt), rng.sample(fp, k=nf), rng)
    return {
        "question": stem, "options": opts, "answers": ans,
        "source": {"text": ref.context_sentence, "reference": ref.full_ref},
    }


def _build_biblical_basis_q(
    ref: ScriptureRef,
    correct_teachings: list,
    wrong_teachings: list,
    rng: random.Random,
    negated: bool = False,
) -> dict:
    """'[Ref] is / is not the biblical basis of'"""
    if len(correct_teachings) < 1 or len(wrong_teachings) < 3:
        return None

    stem = f"{ref.full_ref} is {'not ' if negated else ''}the biblical basis of"
    if negated:
        nt = rng.randint(2, 3)
        nf = 5 - nt
        tp, fp = wrong_teachings, correct_teachings
    else:
        nt = rng.randint(1, 2)
        nf = 5 - nt
        tp, fp = correct_teachings, wrong_teachings

    if len(tp) < nt or len(fp) < nf:
        return None
    opts, ans = _shuffle_build(rng.sample(tp, k=nt), rng.sample(fp, k=nf), rng)
    return {
        "question": stem, "options": opts, "answers": ans,
        "source": {"text": ref.context_sentence, "reference": ref.full_ref},
    }


def _build_talks_about_q(
    ref: ScriptureRef,
    correct_phrases: list,
    wrong_phrases: list,
    rng: random.Random,
) -> dict:
    """'[Ref] talks about'"""
    if len(correct_phrases) < 1 or len(wrong_phrases) < 3:
        return None

    stem = f"{ref.full_ref} talks about"
    nt = rng.randint(1, 2)
    nf = 5 - nt
    if len(correct_phrases) < nt or len(wrong_phrases) < nf:
        return None
    opts, ans = _shuffle_build(
        rng.sample(correct_phrases, k=nt),
        rng.sample(wrong_phrases, k=nf),
        rng,
    )
    return {
        "question": stem, "options": opts, "answers": ans,
        "source": {"text": ref.context_sentence, "reference": ref.full_ref},
    }


def _build_scripture_found_q(
    quote: str,
    correct_ref: ScriptureRef,
    all_refs: list,
    rng: random.Random,
) -> dict:
    """'The scripture "..." can be found in'

    Options are scripture references — one correct, four wrong.
    """
    other = [r for r in all_refs if r.full_ref != correct_ref.full_ref]
    if len(other) < 4:
        return None

    stem = f'The scripture "{quote}" can be found in'

    # Prefer refs from the same book (trickier) then others
    same_bk = [r for r in other if r.book == correct_ref.book]
    diff_bk = [r for r in other if r.book != correct_ref.book]
    pool = same_bk + diff_bk
    picked = rng.sample(pool, k=min(4, len(pool)))
    while len(picked) < 4:
        picked.append(rng.choice(other))

    wrong = [r.full_ref for r in picked[:4]]
    opts, ans = _shuffle_build([correct_ref.full_ref], wrong, rng)
    return {
        "question": stem, "options": opts, "answers": ans,
        "source": {"text": quote, "reference": correct_ref.full_ref},
    }


def _build_gleaned_from_q(
    statement: str,
    correct_ref: ScriptureRef,
    other_refs: list,
    rng: random.Random,
) -> dict:
    """'The statement "..." can be gleaned from'

    Options are scripture references.
    """
    if len(other_refs) < 4:
        return None

    stem = f'The statement "{statement}" can be gleaned from'
    wrong = [r.full_ref for r in rng.sample(other_refs, k=4)]
    opts, ans = _shuffle_build([correct_ref.full_ref], wrong, rng)
    return {
        "question": stem, "options": opts, "answers": ans,
        "source": {"text": correct_ref.context_sentence, "reference": correct_ref.full_ref},
    }


def _build_according_to_q(
    source_title: str,
    topic: str,
    correct: list,
    wrong: list,
    rng: random.Random,
    negated: bool = False,
) -> dict:
    """'According to several authorities on [Book], the following are [not] [topic]'"""
    if len(correct) < 1 or len(wrong) < 3:
        return None

    neg = "not " if negated else ""
    stem = f"According to several authorities on the {source_title}, the following are {neg}{topic}"
    if negated:
        nt = rng.randint(2, 3)
        nf = 5 - nt
        tp, fp = wrong, correct
    else:
        nt = rng.randint(1, 3)
        nf = 5 - nt
        tp, fp = correct, wrong
    if len(tp) < nt or len(fp) < nf:
        return None
    opts, ans = _shuffle_build(rng.sample(tp, k=nt), rng.sample(fp, k=nf), rng)
    return {
        "question": stem, "options": opts, "answers": ans,
        "source": {"text": f"See {source_title}", "reference": source_title},
    }


# ── Pool generation ────────────────────────────────────────────────────────

def _difficulty_for(index: int, total: int) -> str:
    ratio = index / max(total, 1)
    if ratio < 0.33:
        return "easy"
    if ratio < 0.66:
        return "medium"
    return "hard"


def generate_question_pool(
    chapter,
    pool_size: int = None,
    seed: int = None,
    config: QuestionConfig = None,
) -> list:
    """Generate a scripture-based question pool for one chapter.

    Each question uses actual text from the book near the scripture reference
    as options — NOT abstract concepts.
    """
    cfg = config or QuestionConfig()
    target = pool_size or cfg.default_pool_size
    target = max(cfg.pool_min, min(cfg.pool_max, target))

    rng = random.Random(seed)

    refs = extract_scripture_refs(chapter.text)

    # ── Build per-ref phrase banks ──────────────────────────────────────
    ref_phrases = {}
    ref_teachings = {}
    for ref in refs:
        ref_phrases[ref.full_ref] = _extract_short_phrases(ref.nearby_text)
        ref_teachings[ref.full_ref] = _extract_teachings(ref.nearby_text)

    # All phrases from the entire chapter (for wrong answers)
    all_phrases = _extract_short_phrases(chapter.text)
    all_teachings = _extract_teachings(chapter.text)
    all_concepts = _extract_concepts(chapter.text)

    questions = []
    qid = 1

    def _add(q):
        nonlocal qid
        if q is None or len(questions) >= target:
            return False
        q["id"] = f"ch{chapter.chapter_id:03d}_q{qid:03d}"
        q["chapter_id"] = chapter.chapter_id
        q["difficulty"] = _difficulty_for(qid, target)
        questions.append(q)
        qid += 1
        return True

    rng.shuffle(refs)

    # ── Template distribution (weighted) ────────────────────────────────
    # 0 = quotation_can, 1 = quotation_cannot, 2 = biblical_basis,
    # 3 = biblical_basis_not, 4 = talks_about, 5 = scripture_found,
    # 6 = gleaned_from
    TEMPLATES = list(range(7))
    WEIGHTS = [3, 3, 2, 2, 2, 2, 2]  # favour quotation templates

    for ref in refs:
        if len(questions) >= target:
            break

        my_phrases = ref_phrases.get(ref.full_ref, [])
        my_teach = ref_teachings.get(ref.full_ref, [])
        other_phrases = [p for p in all_phrases if p not in my_phrases]
        other_teach = [t for t in all_teachings if t not in my_teach]
        other_refs = [r for r in refs if r.full_ref != ref.full_ref]

        t = rng.choices(TEMPLATES, weights=WEIGHTS, k=1)[0]

        if t == 0 and my_phrases:
            _add(_build_quotation_q(ref, my_phrases, other_phrases, rng, negated=False))
        elif t == 1 and my_phrases:
            _add(_build_quotation_q(ref, my_phrases, other_phrases, rng, negated=True))
        elif t == 2 and my_teach:
            _add(_build_biblical_basis_q(ref, my_teach, other_teach or other_phrases, rng))
        elif t == 3 and my_teach:
            _add(_build_biblical_basis_q(ref, my_teach, other_teach or other_phrases, rng, negated=True))
        elif t == 4 and my_phrases:
            _add(_build_talks_about_q(ref, my_phrases, other_phrases, rng))
        elif t == 5 and my_phrases and other_refs:
            _add(_build_scripture_found_q(rng.choice(my_phrases), ref, refs, rng))
        elif t == 6 and my_phrases and other_refs:
            stmt = rng.choice(my_phrases)
            _add(_build_gleaned_from_q(stmt, ref, other_refs, rng))

    # ── Fill remaining slots ────────────────────────────────────────────
    attempts = 0
    while len(questions) < target and refs and attempts < target * 6:
        attempts += 1
        ref = rng.choice(refs)

        my_phrases = ref_phrases.get(ref.full_ref, [])
        my_teach = ref_teachings.get(ref.full_ref, [])
        other_phrases = [p for p in all_phrases if p not in my_phrases]
        other_teach = [t for t in all_teachings if t not in my_teach]
        other_refs = [r for r in refs if r.full_ref != ref.full_ref]

        t = rng.choices(TEMPLATES, weights=WEIGHTS, k=1)[0]

        if t == 0 and my_phrases:
            _add(_build_quotation_q(ref, my_phrases, other_phrases, rng, negated=False))
        elif t == 1 and my_phrases:
            _add(_build_quotation_q(ref, my_phrases, other_phrases, rng, negated=True))
        elif t == 2 and my_teach:
            _add(_build_biblical_basis_q(ref, my_teach, other_teach or other_phrases, rng))
        elif t == 3 and my_teach:
            _add(_build_biblical_basis_q(ref, my_teach, other_teach or other_phrases, rng, negated=True))
        elif t == 4 and my_phrases:
            _add(_build_talks_about_q(ref, my_phrases, other_phrases, rng))
        elif t == 5 and my_phrases and other_refs:
            _add(_build_scripture_found_q(rng.choice(my_phrases), ref, refs, rng))
        elif t == 6 and my_phrases and other_refs:
            stmt = rng.choice(my_phrases)
            _add(_build_gleaned_from_q(stmt, ref, other_refs, rng))

    # ── Fallback for chapters with very few refs ────────────────────────
    if len(questions) < target and all_concepts:
        topics = [
            "things which a loyal assistant should do",
            "signs of disloyalty",
            "stages of rebellion",
            "key principles of loyalty",
            "important truths about faithfulness",
        ]
        while len(questions) < target:
            topic = rng.choice(topics)
            cn = rng.sample(all_teachings[:15], k=min(3, len(all_teachings))) if all_teachings else all_phrases[:3]
            cw = rng.sample(all_phrases[:20], k=min(4, len(all_phrases))) if all_phrases else ["N/A"] * 4
            _add(_build_according_to_q(
                chapter.title, topic, cn, cw, rng,
                negated=rng.choice([True, False]),
            ))

    return questions


def generate_all_chapter_questions(
    chapters: list,
    pool_size: int = None,
    seed: int = None,
) -> dict:
    """Generate question pools for all chapters."""
    master_rng = random.Random(seed)
    output = {}
    for chapter in chapters:
        ch_seed = master_rng.randint(1, 1_000_000)
        output[chapter.chapter_id] = generate_question_pool(
            chapter=chapter, pool_size=pool_size, seed=ch_seed,
        )
    return output
