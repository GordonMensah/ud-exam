"""Question generation logic for scripture-focused exam-style questions.

Generates questions matching the UO-SAT exam format:
- "[Scripture ref] is the biblical basis of"
- "[Scripture ref] talks about"
- "The following quotations can be found in [Scripture ref]"
- "The following quotations cannot be found in [Scripture ref]"
- "The statement '...' can be gleaned from"
- "According to [source], the following are [concept]"
"""

from __future__ import annotations

import random
import re
from dataclasses import dataclass
from typing import Any

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


def extract_scripture_refs(text: str) -> list:
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


def _extract_key_phrases(text: str) -> list:
    phrases = []
    for m in _QUOTED_TEXT_RE.finditer(text):
        phrases.append(m.group(1).strip())
    for sent in _SENTENCE_SPLIT_RE.split(text):
        sent = sent.strip()
        if 30 < len(sent) < 200 and not _SCRIPTURE_RE.search(sent):
            phrases.append(sent)
    return phrases


def _extract_concepts(text: str) -> list:
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


def _extract_names(text: str) -> list:
    name_re = re.compile(r"\b([A-Z][a-z]{2,}(?:\s+[A-Z][a-z]{2,})?)\b")
    exclude = {
        "The", "This", "That", "These", "Those", "There", "Here", "Where",
        "When", "What", "Which", "Who", "How", "Why", "Because", "Therefore",
        "However", "Also", "Many", "Some", "Other", "Another", "Every",
        "According", "Chapter", "Verse", "Bible", "Scripture",
    }
    names = []
    for m in name_re.finditer(text):
        n = m.group(1)
        if n not in exclude and n not in names:
            names.append(n)
    return names


# ── Question template builders ─────────────────────────────────────────────

def _shuffle_build(
    true_items: list, false_items: list, rng: random.Random
) -> tuple:
    labels = ["a", "b", "c", "d", "e"]
    items = [(t, True) for t in true_items] + [(f, False) for f in false_items]
    rng.shuffle(items)
    options = {labels[i]: items[i][0] for i in range(5)}
    answers = {labels[i]: items[i][1] for i in range(5)}
    return options, answers


def _build_biblical_basis_q(
    ref: ScriptureRef, correct: list, wrong: list,
    rng: random.Random, negated: bool = False,
) -> dict:
    if not correct or len(wrong) < 3:
        return None
    stem = f"{ref.full_ref} is {'not ' if negated else ''}the biblical basis of"
    if negated:
        nt, nf = rng.randint(2, 4), 0
        nf = 5 - nt
        tp, fp = wrong, correct
    else:
        nt = rng.randint(1, 2)
        nf = 5 - nt
        tp, fp = correct, wrong
    if len(tp) < nt or len(fp) < nf:
        return None
    opts, ans = _shuffle_build(rng.sample(tp, k=nt), rng.sample(fp, k=nf), rng)
    return {"question": stem, "options": opts, "answers": ans,
            "source": {"text": ref.context_sentence, "reference": ref.full_ref}}


def _build_talks_about_q(
    ref: ScriptureRef, correct: list, wrong: list, rng: random.Random,
) -> dict:
    if not correct or len(wrong) < 3:
        return None
    stem = f"{ref.full_ref} talks about"
    nt = rng.randint(1, 2)
    nf = 5 - nt
    if len(correct) < nt or len(wrong) < nf:
        return None
    opts, ans = _shuffle_build(rng.sample(correct, k=nt), rng.sample(wrong, k=nf), rng)
    return {"question": stem, "options": opts, "answers": ans,
            "source": {"text": ref.context_sentence, "reference": ref.full_ref}}


def _build_quotation_q(
    ref: ScriptureRef, correct: list, wrong: list,
    rng: random.Random, negated: bool = False,
) -> dict:
    if not correct or len(wrong) < 3:
        return None
    if negated:
        stem = f"The following quotations cannot be found in {ref.full_ref}"
        nt, nf = rng.randint(2, 4), 0
        nf = 5 - nt
        tp, fp = wrong, correct
    else:
        stem = f"The following quotations can be found in {ref.full_ref}"
        nt = rng.randint(1, 2)
        nf = 5 - nt
        tp, fp = correct, wrong
    if len(tp) < nt or len(fp) < nf:
        return None
    opts, ans = _shuffle_build(rng.sample(tp, k=nt), rng.sample(fp, k=nf), rng)
    return {"question": stem, "options": opts, "answers": ans,
            "source": {"text": ref.context_sentence, "reference": ref.full_ref}}


def _build_gleaned_from_q(
    statement: str, correct_ref: ScriptureRef, other_refs: list, rng: random.Random,
) -> dict:
    if len(other_refs) < 4:
        return None
    stem = f'The statement "{statement}" can be gleaned from'
    wrong = [r.full_ref for r in rng.sample(other_refs, k=4)]
    opts, ans = _shuffle_build([correct_ref.full_ref], wrong, rng)
    return {"question": stem, "options": opts, "answers": ans,
            "source": {"text": correct_ref.context_sentence, "reference": correct_ref.full_ref}}


def _build_scripture_found_q(
    quote: str, correct_ref: ScriptureRef, all_refs: list, rng: random.Random,
) -> dict:
    other = [r for r in all_refs if r.full_ref != correct_ref.full_ref]
    if len(other) < 4:
        return None
    stem = f'The scripture "{quote}" can be found in'
    same_bk = [r for r in other if r.book == correct_ref.book]
    diff_bk = [r for r in other if r.book != correct_ref.book]
    pool = same_bk + diff_bk
    picked = rng.sample(pool, k=min(4, len(pool)))
    while len(picked) < 4:
        picked.append(rng.choice(other))
    wrong = [r.full_ref for r in picked[:4]]
    opts, ans = _shuffle_build([correct_ref.full_ref], wrong, rng)
    return {"question": stem, "options": opts, "answers": ans,
            "source": {"text": quote, "reference": correct_ref.full_ref}}


def _build_according_to_q(
    source_title: str, topic: str, correct: list, wrong: list,
    rng: random.Random, negated: bool = False,
) -> dict:
    if len(correct) < 1 or len(wrong) < 3:
        return None
    neg = "not " if negated else ""
    stem = f"According to {source_title}, the following are {neg}{topic}"
    if negated:
        nt, nf = rng.randint(2, 4), 0
        nf = 5 - nt
        tp, fp = wrong, correct
    else:
        nt = rng.randint(1, 3)
        nf = 5 - nt
        tp, fp = correct, wrong
    if len(tp) < nt or len(fp) < nf:
        return None
    opts, ans = _shuffle_build(rng.sample(tp, k=nt), rng.sample(fp, k=nf), rng)
    return {"question": stem, "options": opts, "answers": ans,
            "source": {"text": f"See {source_title}", "reference": source_title}}


# ── Pool generation ────────────────────────────────────────────────────────

def _difficulty_for(index: int, total: int) -> str:
    ratio = index / max(total, 1)
    if ratio < 0.33:
        return "easy"
    if ratio < 0.66:
        return "medium"
    return "hard"


def generate_question_pool(
    chapter: Chapter,
    pool_size: int = None,
    seed: int = None,
    config: QuestionConfig = None,
) -> list:
    """Generate a scripture-based question pool for one chapter."""
    cfg = config or QuestionConfig()
    target = pool_size or cfg.default_pool_size
    target = max(cfg.pool_min, min(cfg.pool_max, target))

    rng = random.Random(seed)

    refs = extract_scripture_refs(chapter.text)
    all_quotes = _extract_key_phrases(chapter.text)
    all_concepts = _extract_concepts(chapter.text)
    all_names = _extract_names(chapter.text)

    ref_concepts = {}
    ref_quotes = {}
    for ref in refs:
        ref_concepts[ref.full_ref] = _extract_concepts(ref.nearby_text)
        ref_quotes[ref.full_ref] = _extract_key_phrases(ref.nearby_text)

    flat_concepts = list({c for cs in ref_concepts.values() for c in cs})
    flat_quotes = list({q for qs in ref_quotes.values() for q in qs})
    sentences = [s.strip() for s in _SENTENCE_SPLIT_RE.split(chapter.text) if 20 < len(s.strip()) < 150]

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

    for ref in refs:
        if len(questions) >= target:
            break
        mc = ref_concepts.get(ref.full_ref, [])
        mq = ref_quotes.get(ref.full_ref, [])
        oc = [c for c in flat_concepts if c not in mc]
        oq = [q for q in flat_quotes if q not in mq]
        oref = [r for r in refs if r.full_ref != ref.full_ref]

        t = rng.randint(0, 6)
        if t == 0 and mc:
            _add(_build_biblical_basis_q(ref, mc, oc or sentences[:10], rng))
        elif t == 1 and mc:
            _add(_build_biblical_basis_q(ref, mc, oc or sentences[:10], rng, negated=True))
        elif t == 2 and mc:
            _add(_build_talks_about_q(ref, mc, oc or sentences[:10], rng))
        elif t == 3 and mq:
            _add(_build_quotation_q(ref, mq, oq or sentences[:10], rng))
        elif t == 4 and mq:
            _add(_build_quotation_q(ref, mq, oq or sentences[:10], rng, negated=True))
        elif t == 5 and mq and oref:
            _add(_build_scripture_found_q(rng.choice(mq), ref, refs, rng))
        elif t == 6 and (mq or mc) and oref:
            stmt = rng.choice(mq) if mq else rng.choice(mc)
            _add(_build_gleaned_from_q(stmt, ref, oref, rng))

    attempts = 0
    while len(questions) < target and refs and attempts < target * 4:
        attempts += 1
        ref = rng.choice(refs)
        mc = ref_concepts.get(ref.full_ref, [])
        mq = ref_quotes.get(ref.full_ref, [])
        oc = [c for c in flat_concepts if c not in mc]
        oq = [q for q in flat_quotes if q not in mq]
        oref = [r for r in refs if r.full_ref != ref.full_ref]

        t = rng.randint(0, 6)
        if t <= 1 and mc:
            _add(_build_biblical_basis_q(ref, mc, oc or sentences[:10], rng, negated=t == 1))
        elif t == 2 and mc:
            _add(_build_talks_about_q(ref, mc, oc or sentences[:10], rng))
        elif t <= 4 and mq:
            _add(_build_quotation_q(ref, mq, oq or sentences[:10], rng, negated=t == 4))
        elif t == 5 and mq:
            _add(_build_scripture_found_q(rng.choice(mq), ref, refs, rng))
        elif t == 6 and (mq or mc) and oref:
            stmt = rng.choice(mq) if mq else rng.choice(mc)
            _add(_build_gleaned_from_q(stmt, ref, oref, rng))

    # Fallback for chapters with few scripture refs
    if len(questions) < target and all_names:
        topics = ["reasons why loyalty is important", "signs of disloyalty",
                  "stages of rebellion", "key principles", "important truths"]
        while len(questions) < target:
            topic = rng.choice(topics)
            cn = rng.sample(all_names, k=min(3, len(all_names)))
            cw = rng.sample(sentences[:20], k=min(4, len(sentences))) if sentences else ["N/A"] * 4
            _add(_build_according_to_q(chapter.title, topic, cn, cw, rng, negated=rng.choice([True, False])))

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
