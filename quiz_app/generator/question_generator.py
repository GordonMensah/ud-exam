"""Question generation matching the UO-SAT exam format exactly.

Templates (derived from actual UO-SAT screenshots):
─────────────────────────────────────────────────────────────────────────────
T1  "[Ref] talks about"                → options = short topic phrases (3-12 words)
T2  "[Ref] does not talk about"        → same style, negated
T3  "[Ref] is the biblical basis of"   → options = teaching/doctrine statements from book
T4  "[Ref] is not the biblical basis of" → same, negated
T5  "The following quotations can be found in [Ref]"
                                        → options = short KJV-style verse quotes
T6  "The following quotations cannot be found in [Ref]"
                                        → same, negated
T7  'The scripture "…" can be found in'
                                        → options = scripture references (tricky similar ones)
T8  'The scripture "…" cannot be found in'
                                        → same, negated
T9  'The statement "…" can be gleaned from'
                                        → options = scripture references
T10 "According to several authorities on the Doctrine of …,
     the following are [topic]"        → options = patterned list items
T11 "According to …, the following are not [topic]"
                                        → same, negated
"""

from __future__ import annotations

import random
import re
from dataclasses import dataclass
from typing import Optional

from .epub_parser import Chapter

# ── Scripture reference regex ──────────────────────────────────────────────

_BOOK_NAMES = (
    # English
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
    # Portuguese
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

_QUOTED_TEXT_RE = re.compile(r'["\u201c\u201d]([^"\u201c\u201d]{8,150})["\u201c\u201d]')
_SENTENCE_RE = re.compile(r"(?<=[.!?])\s+")

LABELS = ["a", "b", "c", "d", "e"]


# ── Data classes ───────────────────────────────────────────────────────────

@dataclass
class ScriptureRef:
    book: str
    chapter: int
    verse_start: int
    verse_end: int
    full_ref: str
    context_sentence: str
    nearby_text: str          # ~400 chars window around the ref


@dataclass
class QuestionConfig:
    pool_min: int = 10
    pool_max: int = 20
    default_pool_size: int = 15


# ── Utility helpers ────────────────────────────────────────────────────────

def _normalize_ref(book: str, ch: int, vs: int, ve: int) -> str:
    r = f"{book} {ch}:{vs}"
    if ve and ve != vs:
        r += f"-{ve}"
    return r


def _window(text: str, start: int, end: int, w: int = 400) -> str:
    return text[max(0, start - w): min(len(text), end + w)].strip()


def _sentence_at(text: str, start: int, end: int) -> str:
    s = text.rfind(".", 0, start)
    s = s + 1 if s != -1 else 0
    e = text.find(".", end)
    e = e + 1 if e != -1 else len(text)
    return text[s:e].strip()


# ── Extraction functions ───────────────────────────────────────────────────

def extract_scripture_refs(text: str) -> list:
    refs, seen = [], set()
    for m in _SCRIPTURE_RE.finditer(text):
        book, ch = m.group(1).strip(), int(m.group(2))
        vs = int(m.group(3))
        ve = int(m.group(4)) if m.group(4) else vs
        full = _normalize_ref(book, ch, vs, ve)
        if full in seen:
            continue
        seen.add(full)
        refs.append(ScriptureRef(
            book=book, chapter=ch, verse_start=vs, verse_end=ve,
            full_ref=full,
            context_sentence=_sentence_at(text, m.start(), m.end()),
            nearby_text=_window(text, m.start(), m.end()),
        ))
    return refs


def _extract_short_topics(text: str) -> list:
    """Extract SHORT topic descriptions (3-12 words) suitable for
    "talks about" / "does not talk about" options.

    Examples: "Idol worshippers", "A witch not being suffered to live",
    "Divisions in the church", "Walking by faith and not by sight".
    """
    topics = []

    # Gerund phrases: "teaching against disloyalty", "walking by faith"
    for m in re.finditer(
        r"\b([A-Z][a-z]+ing\s+(?:against|about|for|with|by|in|on|to|of|the|a)\s+"
        r"[a-z].{3,50}?)(?:[.,;:!?]|\s+and\s+|\s+but\s+|\s+or\s+|$)",
        text,
    ):
        t = m.group(1).strip().rstrip(".,;:!?")
        wc = len(t.split())
        if 3 <= wc <= 12:
            topics.append(t)

    # Noun phrases starting with articles: "The need to examine oneself"
    for m in re.finditer(
        r"\b((?:The|A|An)\s+[a-z].{5,55}?)(?:[.,;:!?]|$)", text,
    ):
        t = m.group(1).strip().rstrip(".,;:!?")
        wc = len(t.split())
        if 3 <= wc <= 12 and not _SCRIPTURE_RE.search(t):
            topics.append(t)

    # Short clauses from sentences (split on period, take <=12 word ones)
    for sent in _SENTENCE_RE.split(text):
        sent = sent.strip()
        if not sent or _SCRIPTURE_RE.search(sent):
            continue
        wc = len(sent.split())
        if 3 <= wc <= 12:
            topics.append(sent)
        # Also try sub-clauses
        for part in re.split(r"[,;]\s+", sent):
            part = part.strip().rstrip(".,;:!?")
            wc = len(part.split())
            if 3 <= wc <= 10 and not _SCRIPTURE_RE.search(part):
                topics.append(part)

    return _dedup(topics)


def _extract_verse_quotes(text: str) -> list:
    """Extract short KJV-style quotations suitable for
    "The following quotations can/cannot be found in [Ref]".

    Examples: "Thou hast been in Eden", "he that gathereth not",
    "The Lord forbid that I should stretch forth mine hand".
    """
    quotes = []

    # Actual quoted text
    for m in _QUOTED_TEXT_RE.finditer(text):
        q = m.group(1).strip()
        wc = len(q.split())
        if 4 <= wc <= 20:
            quotes.append(q)

    # KJV-style phrases (thee/thou/hath/shalt/doth etc.)
    kjv_pattern = (
        r"(?:(?:thou|thee|thy|ye|hath|doth|shalt|wilt|art|"
        r"saith|sayeth|cometh|goeth|maketh|taketh|giveth|"
        r"doeth|keepeth|loveth|knoweth|seeketh|walketh|"
        r"bringeth|casteth|setteth)\s+.{5,60}?"
        r"|.{5,30}?\s+(?:thereof|therein|thereon|wherefore|"
        r"whereby|henceforth|hitherto|forthwith))"
    )
    for m in re.finditer(kjv_pattern, text, re.IGNORECASE):
        q = m.group(0).strip().rstrip(".,;:!?")
        wc = len(q.split())
        if 4 <= wc <= 18:
            quotes.append(q)

    # Capitalized sentence starters that look like verse quotes
    for m in re.finditer(
        r"(?:^|\.\s+)([A-Z][a-z]+\s+(?:that|who|which|is|was|shall|"
        r"will|hast|art)\s+.{8,60}?)(?:\.|,|;|$)",
        text, re.MULTILINE,
    ):
        q = m.group(1).strip().rstrip(".,;:!?")
        wc = len(q.split())
        if 4 <= wc <= 16 and not _SCRIPTURE_RE.search(q):
            quotes.append(q)

    return _dedup(quotes)


def _extract_teachings(text: str) -> list:
    """Extract teaching/doctrine statements for
    "is the biblical basis of" options.

    Examples: "A person who approves of someone who makes wrong decisions
    is potentially disloyal", "The execution stage of disloyalty",
    "A godly resignation".
    """
    teachings = []

    # Doctrine-style: "The X stage of Y", "The sign of Y"
    for m in re.finditer(
        r"((?:the|a|an)\s+(?:sign|stage|mark|characteristic|quality|"
        r"trait|principle|key|spirit|danger|fruit|test|proof|evidence|"
        r"indicator|pattern|type|form|kind|nature|result|consequence|"
        r"reason|cause|effect|root|basis|foundation)\s+"
        r"(?:of|for|behind|in)\s+.{5,60}?)(?:\.|,|;|$)",
        text, re.IGNORECASE,
    ):
        t = m.group(1).strip().rstrip(".,;:!?")
        if 4 <= len(t.split()) <= 15:
            teachings.append(t)

    # "A person who X is potentially disloyal" / "A loyal person does X"
    for m in re.finditer(
        r"(a\s+(?:person|leader|pastor|minister|assistant|man|woman|"
        r"loyal\s+\w+|disloyal\s+\w+|faithful\s+\w+|unfaithful\s+\w+)"
        r"\s+(?:who|that|which)\s+.{10,80}?)(?:\.|;|$)",
        text, re.IGNORECASE,
    ):
        t = m.group(1).strip().rstrip(".,;:!?")
        if 5 <= len(t.split()) <= 20:
            teachings.append(t)

    # Short doctrinal phrases: "Understanding the schemes of the enemy"
    for m in re.finditer(
        r"([A-Z][a-z]+ing\s+(?:the|a|an|your|his|her|our|their)\s+"
        r".{5,50}?)(?:\.|,|;|$)",
        text,
    ):
        t = m.group(1).strip().rstrip(".,;:!?")
        if 3 <= len(t.split()) <= 12:
            teachings.append(t)

    return _dedup(teachings)


def _extract_patterned_lists(text: str) -> dict:
    """Extract items that follow a repeated pattern — used for
    "According to..." questions.

    Examples: {"The key of": ["eliminating strange fires",
              "teaching against disloyalty", "unquenchable fire"]}
    """
    groups = {}

    # "The key of X"
    for m in re.finditer(r"(?:the\s+key\s+of\s+)(.{5,50}?)(?:\.|,|;|$)", text, re.IGNORECASE):
        groups.setdefault("The key of", []).append(m.group(1).strip().rstrip(".,;"))

    # "The stage of X" / "The X stage"
    for m in re.finditer(r"(?:the\s+\w+\s+stage\s+of\s+)(.{5,50}?)(?:\.|,|;|$)", text, re.IGNORECASE):
        groups.setdefault("stages of disloyalty", []).append(m.group(0).strip().rstrip(".,;"))
    for m in re.finditer(r"(the\s+\w+\s+stage)(?:\.|,|;|\s+of)", text, re.IGNORECASE):
        groups.setdefault("stages of disloyalty", []).append(m.group(1).strip())

    # "The sign of X"
    for m in re.finditer(r"(the\s+sign\s+of\s+.{5,50}?)(?:\.|,|;|$)", text, re.IGNORECASE):
        groups.setdefault("signs of disloyalty", []).append(m.group(1).strip().rstrip(".,;"))

    # Deduplicate each group
    for k in groups:
        groups[k] = _dedup(groups[k])

    return {k: v for k, v in groups.items() if len(v) >= 3}


def _extract_names(text: str) -> list:
    """Extract biblical / character names for name-based questions.
    Examples: Zadok, Ahithophel, Absalom, Judas.
    """
    # Common biblical names pattern
    name_re = re.compile(r"\b([A-Z][a-z]{2,12}(?:el|ah|as|am|om|im|us|os|ek|ob|ud|ai|ei|oi)?)\b")
    exclude = {
        "The", "This", "That", "These", "Those", "There", "Here", "Where",
        "When", "What", "Which", "Who", "How", "Why", "Because", "Therefore",
        "However", "Also", "Many", "Some", "Other", "Another", "Every",
        "According", "Chapter", "Verse", "Bible", "Scripture", "Christian",
        "God", "Lord", "Jesus", "Christ", "Holy", "Spirit", "Church",
        "Lesson", "Section", "Part", "Note", "King", "Queen",
        "But", "And", "For", "Not", "All", "His", "Her", "Our",
        "They", "Them", "Will", "Can", "May", "Let", "See", "Now",
        "Then", "Than", "Has", "Had", "Was", "Were", "Are", "Been",
        "Being", "Have", "Does", "Did", "May", "Each", "Few",
    }
    names = []
    for m in name_re.finditer(text):
        n = m.group(1)
        if n not in exclude and n not in names and len(n) >= 3:
            names.append(n)
    return names


def _dedup(items: list) -> list:
    """Deduplicate a list while preserving order."""
    seen = set()
    out = []
    for item in items:
        low = item.lower().strip()
        if low not in seen and len(low) > 2:
            seen.add(low)
            out.append(item)
    return out


# ── Question builders ──────────────────────────────────────────────────────

def _shuffle_build(true_items: list, false_items: list, rng: random.Random):
    """Build (options, answers) dicts from true/false item lists."""
    items = [(t, True) for t in true_items] + [(f, False) for f in false_items]
    rng.shuffle(items)
    options = {LABELS[i]: items[i][0] for i in range(5)}
    answers = {LABELS[i]: items[i][1] for i in range(5)}
    return options, answers


def _q(stem: str, opts, ans, ref: ScriptureRef):
    return {
        "question": stem, "options": opts, "answers": ans,
        "source": {"text": ref.context_sentence, "reference": ref.full_ref},
    }


# T1/T2: "[Ref] talks about" / "[Ref] does not talk about"
def _build_talks_about(ref, correct, wrong, rng, negated=False):
    if len(correct) < 1 or len(wrong) < 3:
        return None
    verb = "does not talk about" if negated else "talks about"
    stem = f"{ref.full_ref} {verb}"
    if negated:
        nt, nf = rng.randint(2, 3), 0
        nf = 5 - nt
        tp, fp = wrong, correct
    else:
        nt = rng.randint(2, 3)
        nf = 5 - nt
        tp, fp = correct, wrong
    if len(tp) < nt or len(fp) < nf:
        return None
    opts, ans = _shuffle_build(rng.sample(tp, k=nt), rng.sample(fp, k=nf), rng)
    return _q(stem, opts, ans, ref)


# T3/T4: "[Ref] is [not] the biblical basis of"
def _build_biblical_basis(ref, correct, wrong, rng, negated=False):
    if len(correct) < 1 or len(wrong) < 3:
        return None
    neg = "not " if negated else ""
    stem = f"{ref.full_ref} is {neg}the biblical basis of"
    if negated:
        nt = rng.randint(2, 3)
        nf = 5 - nt
        tp, fp = wrong, correct
    else:
        nt = rng.randint(1, 2)
        nf = 5 - nt
        tp, fp = correct, wrong
    if len(tp) < nt or len(fp) < nf:
        return None
    opts, ans = _shuffle_build(rng.sample(tp, k=nt), rng.sample(fp, k=nf), rng)
    return _q(stem, opts, ans, ref)


# T5/T6: "The following quotations can[not] be found in [Ref]"
def _build_quotation(ref, correct, wrong, rng, negated=False):
    if len(correct) < 2 or len(wrong) < 2:
        return None
    verb = "cannot" if negated else "can"
    stem = f"The following quotations {verb} be found in {ref.full_ref}"
    if negated:
        nt = rng.randint(2, 3)
        nf = 5 - nt
        tp, fp = wrong, correct
    else:
        nt = rng.randint(2, 3)
        nf = 5 - nt
        tp, fp = correct, wrong
    if len(tp) < nt or len(fp) < nf:
        return None
    opts, ans = _shuffle_build(rng.sample(tp, k=nt), rng.sample(fp, k=nf), rng)
    return _q(stem, opts, ans, ref)


# T7/T8: 'The scripture "…" can[not] be found in' → options are refs
def _build_scripture_found(quote, correct_ref, all_refs, rng, negated=False):
    other = [r for r in all_refs if r.full_ref != correct_ref.full_ref]
    if len(other) < 4:
        return None

    verb = "cannot" if negated else "can"
    stem = f'The scripture "{quote}" {verb} be found in'

    # Prefer same-book refs for trickiness
    same = [r for r in other if r.book == correct_ref.book]
    diff = [r for r in other if r.book != correct_ref.book]
    pool = same + diff
    picked = rng.sample(pool, k=min(4, len(pool)))
    while len(picked) < 4:
        picked.append(rng.choice(other))

    wrong = [r.full_ref for r in picked[:4]]
    opts, ans = _shuffle_build([correct_ref.full_ref], wrong, rng)
    return _q(stem, opts, ans, correct_ref)


# T9: 'The statement "…" can be gleaned from' → options are refs
def _build_gleaned_from(statement, correct_ref, other_refs, rng):
    if len(other_refs) < 4:
        return None
    stem = f'The statement "{statement}" can be gleaned from'
    wrong = [r.full_ref for r in rng.sample(other_refs, k=4)]
    opts, ans = _shuffle_build([correct_ref.full_ref], wrong, rng)
    return _q(stem, opts, ans, correct_ref)


# T10/T11: "According to several authorities on the Doctrine of …,
#            the following are [not] [topic]"
def _build_according_to(book_title, topic, correct, wrong, rng, negated=False, ref=None):
    if len(correct) < 1 or len(wrong) < 3:
        return None
    neg = "not " if negated else ""
    stem = (
        f"According to several authorities on the Doctrine of "
        f"{book_title}, the following are {neg}{topic}"
    )
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
    source_ref = ref or ScriptureRef("", 0, 0, 0, book_title, book_title, "")
    return _q(stem, opts, ans, source_ref)


# ── Pool generation ────────────────────────────────────────────────────────

def _difficulty_for(idx: int, total: int) -> str:
    r = idx / max(total, 1)
    return "easy" if r < 0.33 else "medium" if r < 0.66 else "hard"


def generate_question_pool(
    chapter,
    pool_size: int = None,
    seed: int = None,
    config: QuestionConfig = None,
) -> list:
    """Generate a UO-SAT-style question pool for one chapter."""
    cfg = config or QuestionConfig()
    target = pool_size or cfg.default_pool_size
    target = max(cfg.pool_min, min(cfg.pool_max, target))
    rng = random.Random(seed)

    refs = extract_scripture_refs(chapter.text)
    book_title = "Loyalty and Disloyalty"  # default

    # ── per-ref extraction ─────────────────────────────────────────────
    ref_topics = {}    # short topic descriptions
    ref_quotes = {}    # KJV-style verse quotes
    ref_teachings = {} # doctrine/teaching statements

    for ref in refs:
        ref_topics[ref.full_ref] = _extract_short_topics(ref.nearby_text)
        ref_quotes[ref.full_ref] = _extract_verse_quotes(ref.nearby_text)
        ref_teachings[ref.full_ref] = _extract_teachings(ref.nearby_text)

    # Chapter-wide pools (for wrong answers)
    all_topics = _extract_short_topics(chapter.text)
    all_quotes = _extract_verse_quotes(chapter.text)
    all_teachings = _extract_teachings(chapter.text)
    patterned = _extract_patterned_lists(chapter.text)
    all_names = _extract_names(chapter.text)

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

    # Template weights: [T1, T2, T3, T4, T5, T6, T7, T8, T9, T10, T11]
    WEIGHTS = [3, 2, 2, 2, 3, 3, 2, 1, 2, 2, 1]

    def _try_template(ref):
        my_topics = ref_topics.get(ref.full_ref, [])
        my_quotes = ref_quotes.get(ref.full_ref, [])
        my_teach = ref_teachings.get(ref.full_ref, [])
        ot = [t for t in all_topics if t not in my_topics]
        oq = [q for q in all_quotes if q not in my_quotes]
        ote = [t for t in all_teachings if t not in my_teach]
        other_refs = [r for r in refs if r.full_ref != ref.full_ref]

        t = rng.choices(range(11), weights=WEIGHTS, k=1)[0]

        if t == 0 and my_topics:          # talks about
            return _build_talks_about(ref, my_topics, ot, rng)
        if t == 1 and my_topics:          # does not talk about
            return _build_talks_about(ref, my_topics, ot, rng, negated=True)
        if t == 2 and my_teach:           # biblical basis of
            return _build_biblical_basis(ref, my_teach, ote or ot, rng)
        if t == 3 and my_teach:           # not the biblical basis of
            return _build_biblical_basis(ref, my_teach, ote or ot, rng, negated=True)
        if t == 4 and my_quotes:          # quotations can be found
            return _build_quotation(ref, my_quotes, oq or ot, rng)
        if t == 5 and my_quotes:          # quotations cannot be found
            return _build_quotation(ref, my_quotes, oq or ot, rng, negated=True)
        if t == 6 and my_quotes and other_refs:   # scripture can be found in
            return _build_scripture_found(rng.choice(my_quotes), ref, refs, rng)
        if t == 7 and my_quotes and other_refs:   # scripture cannot be found in
            return _build_scripture_found(rng.choice(my_quotes), ref, refs, rng, negated=True)
        if t == 8 and (my_topics or my_teach) and other_refs:  # gleaned from
            stmt = rng.choice(my_topics or my_teach)
            return _build_gleaned_from(stmt, ref, other_refs, rng)
        if t == 9 and patterned:          # according to
            group_name = rng.choice(list(patterned.keys()))
            items = patterned[group_name]
            wrong_pool = [i for grp in patterned.values() for i in grp if i not in items]
            if not wrong_pool:
                wrong_pool = ot[:10] or all_topics[:10]
            return _build_according_to(book_title, group_name, items, wrong_pool, rng, ref=ref)
        if t == 10 and patterned:         # according to (negated)
            group_name = rng.choice(list(patterned.keys()))
            items = patterned[group_name]
            wrong_pool = [i for grp in patterned.values() for i in grp if i not in items]
            if not wrong_pool:
                wrong_pool = ot[:10] or all_topics[:10]
            return _build_according_to(book_title, group_name, items, wrong_pool, rng, negated=True, ref=ref)
        return None

    # ── First pass: one question per ref ───────────────────────────────
    for ref in refs:
        if len(questions) >= target:
            break
        _add(_try_template(ref))

    # ── Fill remaining ─────────────────────────────────────────────────
    attempts = 0
    while len(questions) < target and refs and attempts < target * 8:
        attempts += 1
        ref = rng.choice(refs)
        _add(_try_template(ref))

    # ── Fallback if still short ────────────────────────────────────────
    if len(questions) < target and (all_teachings or all_topics):
        topics = [
            "things which a loyal assistant should do",
            "signs of disloyalty",
            "reasons why loyalty is important",
            "key principles of loyalty",
            "rebels who ended up at the eighth stage of disloyalty",
        ]
        dummy_ref = ScriptureRef("", 0, 0, 0, book_title, book_title, "")
        while len(questions) < target:
            topic = rng.choice(topics)
            pool_c = all_teachings or all_topics
            pool_w = all_topics or all_teachings
            cn = rng.sample(pool_c[:15], k=min(3, len(pool_c)))
            cw = rng.sample(pool_w[:20], k=min(4, len(pool_w)))
            _add(_build_according_to(
                book_title, topic, cn, cw, rng,
                negated=rng.choice([True, False]), ref=dummy_ref,
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
