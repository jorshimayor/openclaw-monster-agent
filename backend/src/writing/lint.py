"""Check a draft against the editorial standard.

Deterministic on purpose. A model grading prose produces exactly the confident,
unfalsifiable feedback the style guide warns about, and a linter that can be
argued with is worse than no linter. Every finding here points at a specific
span and a specific rule, so it can be confirmed or dismissed in seconds.

The judgement calls — is the answer buried, does each section earn its place —
are returned as review questions, not verdicts.
"""

from __future__ import annotations

import re
from dataclasses import asdict, dataclass
from typing import Any, Dict, List, Optional, Tuple

from .rules import (
    ABSOLUTES, ADVISORY, BRITISH_SPELLINGS, CLICHE_OPENERS, FILLER_PHRASES,
    LIST_BUDGET_PER_1000_WORDS, MARKETING_WORDS, MAX_PARAGRAPH_SENTENCES,
    MAX_SENTENCE_WORDS, MIN_LIST_ITEM_WORDS, ROADMAP_TELLS, RULES_BY_KEY,
    SUPERLATIVES, Severity,
)

_CODE_FENCE = re.compile(r"```.*?```", re.S)
_INLINE_CODE = re.compile(r"`[^`]*`")
_URL = re.compile(r"https?://\S+")
_SENTENCE_SPLIT = re.compile(r"(?<=[.!?])\s+(?=[A-Z(\"'])")
_HEADING = re.compile(r"^(#{1,6})\s+(.*)$")
_LIST_ITEM = re.compile(r"^\s*(?:[-*+]|\d+[.)])\s+(.+)$")
_TABLE_ROW = re.compile(r"^\s*\|.*\|\s*$")
# "is/are/was/were <past participle> by" — the construction the guide names.
# "resources are allocated to each tenant by the hypervisor" — the agent phrase
# is rarely adjacent to the participle, so allow a short object in between.
_PASSIVE = re.compile(
    r"\b(?:is|are|was|were|been|being)\s+(?:\w+ly\s+)?\w+(?:ed|en)\b"
    r"(?:\s+\w+){0,5}?\s+by\b",
    re.I,
)
_ACRONYM = re.compile(r"\b([A-Z]{2,6})\b")
_ACRONYM_DEFINED = re.compile(r"\(([A-Z]{2,6})\)")
_FIRST_PERSON = re.compile(r"(?<![\w'])(I|I'm|I've|I'll|my|me)(?![\w'])")

# Acronyms so embedded in technical prose that expanding them reads as noise.
_ACRONYM_ALLOWLIST = {
    "API", "CPU", "GPU", "RAM", "URL", "HTTP", "HTTPS", "JSON", "YAML", "HTML",
    "CSS", "SQL", "SSH", "TLS", "SSL", "DNS", "IP", "TCP", "UDP", "OS", "CLI",
    "UI", "UX", "ID", "IDE", "PDF", "CSV", "AI", "ML", "FAQ", "USB", "PC",
    "SDK", "REST", "CRUD", "JWT", "RPC", "EVM", "NFT", "DAO", "TVL", "PR",
}


@dataclass
class Finding:
    rule: str
    severity: str
    title: str
    why: str
    source: str
    line: int
    excerpt: str
    suggestion: str = ""


def _strip_code(text: str) -> str:
    """Blank out code so rules never fire inside it, keeping line numbers."""
    def blank(m: re.Match) -> str:
        return re.sub(r"[^\n]", " ", m.group(0))

    return _INLINE_CODE.sub(blank, _CODE_FENCE.sub(blank, text))


def _prose_lines(text: str) -> List[Tuple[int, str]]:
    """(line number, text) for lines that are prose — not headings, code,
    tables or URLs."""
    out = []
    for i, line in enumerate(_strip_code(text).splitlines(), 1):
        if _HEADING.match(line) or _TABLE_ROW.match(line):
            continue
        cleaned = _URL.sub(" ", line)
        if cleaned.strip():
            out.append((i, cleaned))
    return out


def _find_phrases(
    text: str, phrases: List[str], rule_key: str, suggestion: str = ""
) -> List[Finding]:
    rule = RULES_BY_KEY[rule_key]
    findings: List[Finding] = []
    for line_no, line in _prose_lines(text):
        lowered = line.lower()
        for phrase in phrases:
            for m in re.finditer(rf"(?<!\w){re.escape(phrase)}(?!\w)", lowered):
                findings.append(Finding(
                    rule=rule.key, severity=rule.severity, title=rule.title,
                    why=rule.why, source=rule.source, line=line_no,
                    excerpt=line.strip()[max(0, m.start() - 40): m.end() + 40].strip(),
                    suggestion=suggestion or f"Remove or replace “{phrase}”.",
                ))
    return findings


def _check_british(text: str) -> List[Finding]:
    rule = RULES_BY_KEY["british"]
    out = []
    for line_no, line in _prose_lines(text):
        for british, american in BRITISH_SPELLINGS.items():
            if re.search(rf"\b{british}\b", line, re.I):
                out.append(Finding(
                    rule.key, rule.severity, rule.title, rule.why, rule.source,
                    line_no, line.strip()[:120], f"Use “{american}”.",
                ))
    return out


def _check_first_person(text: str) -> List[Finding]:
    rule = RULES_BY_KEY["first_person"]
    out = []
    for line_no, line in _prose_lines(text):
        m = _FIRST_PERSON.search(line)
        if m:
            out.append(Finding(
                rule.key, rule.severity, rule.title, rule.why, rule.source,
                line_no, line.strip()[:120],
                "Rephrase impersonally, or attribute it: “it is generally "
                "recommended to…”.",
            ))
    return out


def _check_passive(text: str) -> List[Finding]:
    rule = RULES_BY_KEY["passive"]
    out = []
    for line_no, line in _prose_lines(text):
        for m in _PASSIVE.finditer(line):
            out.append(Finding(
                rule.key, rule.severity, rule.title, rule.why, rule.source,
                line_no, line.strip()[:120],
                "Name the actor first: “the hypervisor allocates…”.",
            ))
    return out


def _check_acronyms(text: str) -> List[Finding]:
    """An acronym used before its expansion appears.

    Compared on character offsets, not line numbers: a use and its expansion
    frequently sit in the same sentence, and line numbers cannot order those.
    """
    rule = RULES_BY_KEY["acronym"]
    stripped = _strip_code(text)

    defined_at: Dict[str, int] = {}
    for m in _ACRONYM_DEFINED.finditer(stripped):
        defined_at.setdefault(m.group(1), m.start())

    # Offsets of lines that are prose, so headings and tables are skipped.
    prose_spans: List[Tuple[int, int, int]] = []  # (start, end, line_no)
    offset = 0
    for line_no, line in enumerate(stripped.splitlines(keepends=True), 1):
        bare = line.rstrip("\n")
        if bare.strip() and not _HEADING.match(bare) and not _TABLE_ROW.match(bare):
            prose_spans.append((offset, offset + len(bare), line_no))
        offset += len(line)

    out, reported = [], set()
    for start, end, line_no in prose_spans:
        segment = stripped[start:end]
        for m in _ACRONYM.finditer(segment):
            token = m.group(1)
            if token in _ACRONYM_ALLOWLIST or token in reported:
                continue
            absolute = start + m.start()
            if absolute > 0 and stripped[absolute - 1] == "(":
                continue  # this occurrence IS the expansion
            first_defined = defined_at.get(token)
            if first_defined is None or first_defined > absolute:
                reported.add(token)
                out.append(Finding(
                    rule.key, rule.severity, rule.title, rule.why, rule.source,
                    line_no, segment.strip()[:120],
                    f"Write it in full on first use: “virtual dedicated server "
                    f"({token})”, not “{token} (virtual dedicated server)”.",
                ))
    return out


def _paragraphs(text: str) -> List[Tuple[int, str]]:
    """(starting line, paragraph text) for prose blocks."""
    stripped = _strip_code(text)
    out, buf, start = [], [], 0
    for i, line in enumerate(stripped.splitlines(), 1):
        if not line.strip() or _HEADING.match(line) or _LIST_ITEM.match(line) or _TABLE_ROW.match(line):
            if buf:
                out.append((start, " ".join(buf)))
                buf = []
            continue
        if not buf:
            start = i
        buf.append(line.strip())
    if buf:
        out.append((start, " ".join(buf)))
    return out


def _check_length(text: str) -> List[Finding]:
    out = []
    sent_rule = RULES_BY_KEY["long_sentence"]
    para_rule = RULES_BY_KEY["long_paragraph"]
    for line_no, para in _paragraphs(text):
        sentences = [s for s in _SENTENCE_SPLIT.split(para) if s.strip()]
        if len(sentences) > MAX_PARAGRAPH_SENTENCES:
            out.append(Finding(
                para_rule.key, para_rule.severity, para_rule.title, para_rule.why,
                para_rule.source, line_no, para[:120],
                f"{len(sentences)} sentences — split it; three or four is the guideline.",
            ))
        for s in sentences:
            words = len(s.split())
            if words > MAX_SENTENCE_WORDS:
                out.append(Finding(
                    sent_rule.key, sent_rule.severity, sent_rule.title,
                    sent_rule.why, sent_rule.source, line_no, s.strip()[:140],
                    f"{words} words — split it or cut a clause.",
                ))
    return out


def _check_structure(text: str) -> List[Finding]:
    """Headings, tables and lists."""
    out: List[Finding] = []
    lines = _strip_code(text).splitlines()

    headings = [(i, m.group(1), m.group(2).strip())
                for i, line in enumerate(lines, 1)
                if (m := _HEADING.match(line))]
    h2s = [(i, t) for i, level, t in headings if len(level) == 2]

    if not h2s:
        r = RULES_BY_KEY["no_h2"]
        out.append(Finding(r.key, r.severity, r.title, r.why, r.source, 1,
                           "(no ## sections found)",
                           "Structure carries skim readers; add sections."))

    # A heading of one or two bare nouns is a label, not a question.
    label_rule = RULES_BY_KEY["heading_not_question"]
    for line_no, title in h2s:
        words = title.split()
        if len(words) <= 2 and not title.endswith("?"):
            out.append(Finding(
                label_rule.key, label_rule.severity, label_rule.title,
                label_rule.why, label_rule.source, line_no, title,
                'Prefer the reader\'s question: "How Does X Allocate Resources?" '
                'over "Resource Allocation".',
            ))

    # Tables need prose either side of them.
    table_rule = RULES_BY_KEY["table_context"]
    in_table = False
    for i, line in enumerate(lines, 1):
        is_row = bool(_TABLE_ROW.match(line))
        if is_row and not in_table:
            in_table = True
            before = [l for l in lines[max(0, i - 4):i - 1] if l.strip()]
            has_intro = any(
                not _TABLE_ROW.match(l) and not _HEADING.match(l) for l in before
            )
            after = [l for l in lines[i:i + 30] if l.strip()]
            tail = [l for l in after if not _TABLE_ROW.match(l)]
            has_takeaway = bool(tail) and not _HEADING.match(tail[0])
            if not has_intro or not has_takeaway:
                out.append(Finding(
                    table_rule.key, table_rule.severity, table_rule.title,
                    table_rule.why, table_rule.source, i, line.strip()[:100],
                    "Introduce what the table compares, then say what to take "
                    "from it. A bare table pulls the reader out of the article.",
                ))
        elif not is_row:
            in_table = False

    # Lists: budget, and items that are sentence fragments.
    words_total = len(re.findall(r"\w+", _strip_code(text)))
    list_blocks, prev_was_item = 0, False
    thin_rule = RULES_BY_KEY["thin_list_item"]
    for i, line in enumerate(lines, 1):
        m = _LIST_ITEM.match(line)
        if m:
            if not prev_was_item:
                list_blocks += 1
            prev_was_item = True
            if len(m.group(1).split()) < MIN_LIST_ITEM_WORDS:
                out.append(Finding(
                    thin_rule.key, thin_rule.severity, thin_rule.title,
                    thin_rule.why, thin_rule.source, i, m.group(1)[:80],
                    "A three-item sentence does not need to become a list.",
                ))
        else:
            prev_was_item = False

    budget = max(1, round(words_total / 1000 * LIST_BUDGET_PER_1000_WORDS))
    if list_blocks > budget:
        r = RULES_BY_KEY["list_overuse"]
        out.append(Finding(
            r.key, r.severity, r.title, r.why, r.source, 1,
            f"{list_blocks} lists in {words_total} words",
            f"About {budget} would suit this length. Ask whether each list adds "
            f"value or is a presentational habit.",
        ))
    return out


def check(text: str, title: str = "") -> Dict[str, Any]:
    """Lint a draft. Returns findings, counts, and the review questions."""
    findings: List[Finding] = []
    findings += _find_phrases(text, MARKETING_WORDS, "marketing",
                              "Describe the specific capability instead.")
    findings += _find_phrases(text, FILLER_PHRASES, "filler")
    findings += _find_phrases(text, SUPERLATIVES, "superlative",
                              "Soften it: “generally considered to be…”.")
    findings += _find_phrases(text, ABSOLUTES, "absolute",
                              "Use a modal: can, may, should.")
    findings += _find_phrases(text, ROADMAP_TELLS, "roadmap",
                              "Imply the structure through context instead.")
    findings += _find_phrases(text, CLICHE_OPENERS, "cliche_opener",
                              "Open on the actual problem, not the era.")
    findings += _check_british(text)
    findings += _check_first_person(text)
    findings += _check_passive(text)
    findings += _check_acronyms(text)
    findings += _check_length(text)
    findings += _check_structure(text)

    findings.sort(key=lambda f: (f.line, f.rule))
    counts = {s: sum(1 for f in findings if f.severity == s)
              for s in (Severity.BLOCK, Severity.WARN, Severity.NOTE)}
    words = len(re.findall(r"\w+", _strip_code(text)))

    return {
        "title": title,
        "words": words,
        "passes": counts[Severity.BLOCK] == 0,
        "counts": counts,
        "findings": [asdict(f) for f in findings],
        "review_questions": ADVISORY,
    }
