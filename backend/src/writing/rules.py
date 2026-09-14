"""The editorial standard, as data.

Every rule here traces to a line in the editorial guides — the style guide, the
structure and presentation guidelines, and the user-needs model. Nothing is
invented: where a guide gives a list, the list is reproduced; where it gives a
principle a machine cannot check, the rule lives in `ADVISORY` or in the human
document rather than pretending to be checkable.

The checks are deliberately deterministic. A model grading prose would produce
exactly the confident, unfalsifiable feedback the guides warn about, and this is
meant to catch the mechanical failures so a human can spend attention on the
structural ones.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import List, Optional


class Severity:
    BLOCK = "block"      # fails the standard
    WARN = "warn"        # almost always wrong; justify it or fix it
    NOTE = "note"        # worth a look, often fine


@dataclass
class Rule:
    key: str
    severity: str
    title: str
    why: str
    source: str


# ── word-level ───────────────────────────────────────────────────────────────

# "Words and Constructions to Avoid" — unsubstantiated corporate language.
MARKETING_WORDS = [
    "robust", "seamless", "cutting-edge", "cutting edge", "revolutionary",
    "game-changing", "game changing", "world-class", "world class",
    "next-generation", "next generation", "unparalleled", "best-in-class",
    "best in class", "state-of-the-art", "state of the art",
]

# "Direct Language" — auto-pilot qualifiers that add nothing.
FILLER_PHRASES = [
    "it is important to note", "it's important to note", "it is worth noting",
    "it's worth noting", "needless to say", "basically", "essentially",
    "in simple terms", "in other words", "at the end of the day",
    "when it comes to", "in today's world", "in the modern world",
]

# "Comparatives and Superlatives" — rarely objectively demonstrable.
SUPERLATIVES = [
    "fastest", "the best", "most powerful", "cheapest", "most secure",
    "easiest", "superior", "the leading", "industry-leading",
]

# "Absolute Language" — avoid unless consistently provable.
ABSOLUTES = [
    "always", "never", "completely", "entirely", "guaranteed", "impossible",
    "every single", "100%",
]

# "American English" — British spellings that slip in.
BRITISH_SPELLINGS = {
    "organisation": "organization", "organise": "organize",
    "optimise": "optimize", "optimisation": "optimization",
    "virtualisation": "virtualization", "analyse": "analyze",
    "analyses": "analyzes", "defence": "defense", "licence": "license",
    "centre": "center", "modelling": "modeling", "labelling": "labeling",
    "behaviour": "behavior", "colour": "color", "catalogue": "catalog",
    "initialise": "initialize", "serialise": "serialize",
    "recognise": "recognize", "utilise": "utilize",
}

# "The introduction ... should be introducing what will be discussed in the
# article core, but not what the article says."
ROADMAP_TELLS = [
    "in this article, we will", "in this article we will",
    "in this post, we will", "this article will cover",
    "this guide will cover", "we will discuss", "let's dive in",
    "let's get started", "without further ado",
]

# "The introduction should be focused and avoid cliches such as
# 'in an evolving/dynamic world.'"
CLICHE_OPENERS = [
    "in an evolving", "in a dynamic", "in today's fast-paced",
    "in the fast-paced", "in the ever-changing", "in the ever changing",
    "in an increasingly", "as technology evolves", "in the digital age",
]

# ── thresholds ───────────────────────────────────────────────────────────────

# "Three or four sentences per paragraph is a useful guideline, but clarity
# should determine paragraph length rather than an arbitrary word count."
MAX_PARAGRAPH_SENTENCES = 6
# "avoid long, complex sentences that contain too many ideas or clauses"
MAX_SENTENCE_WORDS = 45
# "if you notice yourself making your 3rd list in the article ... ask yourself
# if the list is necessary"
LIST_BUDGET_PER_1000_WORDS = 3
# A list built from a three-item sentence.
MIN_LIST_ITEM_WORDS = 3


RULES: List[Rule] = [
    Rule("marketing", Severity.BLOCK, "Unsubstantiated marketing language",
         "These claims are rarely defensible and readers are attuned to them.",
         "Style guide — Words and Constructions to Avoid"),
    Rule("filler", Severity.BLOCK, "Filler and auto-pilot qualifiers",
         "All information in the article is important by default.",
         "Style guide — Direct Language"),
    Rule("superlative", Severity.WARN, "Superlative claim",
         "Rarely objectively demonstrable; use distanced language instead.",
         "Style guide — Comparatives and Superlatives"),
    Rule("absolute", Severity.WARN, "Absolute language",
         "Avoid unless it can be consistently proven technically accurate.",
         "Style guide — Absolute Language"),
    Rule("british", Severity.WARN, "British spelling",
         "Articles use American English; do not mix variants in one article.",
         "Style guide — American English"),
    Rule("first_person", Severity.WARN, "First person",
         "Personal opinion must not be presented as an authoritative recommendation.",
         "Style guide — Use of First Person"),
    Rule("passive", Severity.NOTE, "Possible passive voice",
         "Prefer the active voice unless the actor is unknown or irrelevant.",
         "Style guide — Active Voice"),
    Rule("acronym", Severity.WARN, "Acronym used before it is expanded",
         "Write the term in full with the acronym in parentheses on first use.",
         "Style guide — Acronyms"),
    Rule("long_sentence", Severity.NOTE, "Long sentence",
         "Too many clauses forces a re-read, which is the main thing to avoid.",
         "Structure — Sentence Structure"),
    Rule("long_paragraph", Severity.NOTE, "Long paragraph",
         "Walls of text lose attention; paragraphs should scan comfortably.",
         "Structure — Paragraph Structure"),
    Rule("roadmap", Severity.BLOCK, "Introduction announces its own structure",
         "Imply the roadmap through context; stating it removes the reason to read on.",
         "Structure — Introduction"),
    Rule("cliche_opener", Severity.BLOCK, "Cliché opener",
         "The introduction should be focused and avoid this exact construction.",
         "User Needs — Understand"),
    Rule("table_context", Severity.WARN, "Table without introduction or takeaway",
         "Introduce what the table compares, then say what to conclude from it.",
         "Structure — Tables"),
    Rule("list_overuse", Severity.NOTE, "Lists are doing too much work",
         "Do not turn every three-item sentence into a list.",
         "Structure — Lists"),
    Rule("thin_list_item", Severity.NOTE, "List item is a fragment",
         "A three-item sentence does not need to become a list.",
         "Structure — Lists"),
    Rule("heading_not_question", Severity.NOTE, "Heading is a bare label",
         "Headings capture skim readers; prefer the question the reader is asking.",
         "Structure — Headings"),
    Rule("no_h2", Severity.BLOCK, "No sections",
         "Structure and headings are the most important part of capturing readers.",
         "Structure — Skim Readers"),
]

RULES_BY_KEY = {r.key: r for r in RULES}


# Judgements a linter cannot make. These are the review questions, not checks.
ADVISORY: List[str] = [
    "Does the first major section answer the question in the title, or is the "
    "answer buried below it?",
    "Does the introduction set up the landscape and give a reason to continue, "
    "rather than summarizing the answer?",
    "Does each section answer a distinct question, judged against the sections "
    "immediately before and after it?",
    "Does each section prepare the reader for the one that follows?",
    "Is any concept introduced before the reader has been given a reason to "
    "care about it?",
    "Are several unfamiliar terms introduced in the same paragraph?",
    "Would removing any section make the article less useful? If not, cut it.",
    "Read it aloud: does this sound like an expert explaining something clearly, "
    "or like someone proving they are an expert?",
]
