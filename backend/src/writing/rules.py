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


class Profile:
    """Which house you are writing in.

    EXPLANATORY is the Cherry Servers model: a reader who may be new, arriving
    from search, who must be convinced the page is worth their time. Stating the
    answer in the introduction loses them, because the answer *is* the article.

    TECHNICAL is the RareSkills model: a reader who came deliberately for a
    mechanism. Sentence one states the scope — "Gas optimization in Ethereum is
    re-writing Solidity code to accomplish the same business logic while
    consuming fewer gas units" — and costs nothing, because the definition was
    never the value. The value is the sixty code blocks below it.

    The rules that differ between them are marked per profile rather than
    reconciled, because they are not reconcilable: they serve different readers.
    """

    EXPLANATORY = "explanatory"
    TECHNICAL = "technical"
    # Jeffrey Scholz (@Jeyffre), who is also the founder of RareSkills — the two
    # standards asked for turn out to be one person. The short-form voice is the
    # article epistemics compressed: name a claim, quote its number, ask whether
    # it survives. First person is the default here, not a failure.
    SHORT_FORM = "short_form"


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
    # None = both profiles.
    profile: Optional[str] = None


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

# ── technical profile (RareSkills method) ────────────────────────────────────

# Claims about speed, cost or efficiency. In the RareSkills articles these never
# appear without a measurement beside them: "4860 gas vs 2758 gas",
# "saves 2,102 gas". A performance claim with no number is the thing their
# method most conspicuously does not do.
PERFORMANCE_CLAIMS = [
    "faster", "slower", "cheaper", "more expensive", "more efficient",
    "less efficient", "saves gas", "gas savings", "more performant",
    "better performance", "worse performance", "optimized", "speeds up",
    "reduces cost", "lower cost", "overhead",
]

# A number, a unit, or a measurement anywhere nearby discharges the claim.
MEASUREMENT_PATTERN = r"(\d[\d,._]*\s*(?:gas|wei|gwei|ms|µs|us|ns|s\b|bytes?|kb|mb|%|x\b)|\b\d{3,}\b|\d+\s*vs\.?\s*\d+)"

# Phrases that state what the reader must already know. Every long RareSkills
# piece has one: "you'll need to understand how the EVM works".
PREREQUISITE_TELLS = [
    "prerequisite", "you'll need to", "you will need to", "this assumes",
    "assumes you", "familiar with", "before reading", "should already",
    "builds on", "requires knowledge", "if you are new to", "if you're new to",
]

# Length past which a technical piece is expected to declare its assumptions
# and carry working code rather than description.
TECHNICAL_DEPTH_WORDS = 1200
# Their articles run 3,500-11,000 words with 20-60 code blocks. One block per
# 400 words is a floor, not a target.
WORDS_PER_CODE_BLOCK = 400

# ── short form (@Jeyffre) ────────────────────────────────────────────────────

# Size and intensity words standing in for a measurement. His openers carry the
# number instead — "5 minutes", "10^25 years", "$3,000" — and his criticism of
# others is precisely that a vague word "glosses over a lot of constraints".
VAGUE_QUANTIFIERS = [
    "a lot of", "tons of", "huge", "massive", "enormous", "insane", "crazy",
    "mind-blowing", "unbelievable", "incredibly", "extremely", "super",
    "way better", "way faster", "so much better", "10x better",
]

# "there are only three possible reasons: 1) … 2) …" — he states a count and
# then delivers it. A stated count that the post does not fill is the one
# mechanical failure this structure is prone to.
EXHAUSTIVE_CLAIM = (
    r"\b(?:only\s+)?(one|two|three|four|five|six|seven|\d+)\s+"
    r"(?:possible\s+|main\s+|key\s+)?"
    r"(reasons?|ways?|options?|things?|causes?|factors?|steps?|kinds?|types?)\b"
)
_NUMBER_WORDS = {
    "one": 1, "two": 2, "three": 3, "four": 4,
    "five": 5, "six": 6, "seven": 7,
}

# Openers that announce a topic instead of making a claim.
#
# An earlier version of this rule demanded a figure in the first line, derived
# from a single thread. A wider sample refutes it: "Your ability to grind is not
# what separates you from your peers", "If you can't explain things well, people
# are going to assume you are a slop cannon" — no numbers, and both are strong
# openers. What they share is a proposition that could be wrong. What fails is
# an opener with no truth value at all.
TOPIC_ANNOUNCEMENTS = [
    "some thoughts on", "a few thoughts on", "here are my thoughts",
    "let's talk about", "lets talk about", "let's discuss", "a thread about",
    "a thread on", "i wanted to share", "here's what i learned about",
    "quick thread on", "in this thread", "today i want to talk",
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

    # ── technical profile ──
    Rule("unproven_claim", Severity.BLOCK, "Performance claim with no measurement",
         "RareSkills articles put the number next to the claim: “4860 gas vs 2758 "
         "gas”. A claim about speed or cost with nothing to check is an assertion.",
         "RareSkills method — claims are demonstrated, not asserted",
         Profile.TECHNICAL),
    Rule("no_prerequisites", Severity.WARN, "No stated prerequisites",
         "Every long RareSkills piece says what you must already know — "
         "“you'll need to understand how the EVM works”. It sets the contract "
         "with the reader before they invest the time.",
         "RareSkills method — explicit audience", Profile.TECHNICAL),
    Rule("thin_on_code", Severity.WARN, "Mechanism described but not shown",
         "Their articles carry 20-60 runnable blocks. A mechanism explained "
         "only in prose is a summary, and the reader came for the mechanism.",
         "RareSkills method — show the thing working", Profile.TECHNICAL),
    # ── short form ──
    Rule("vague_quantifier", Severity.BLOCK, "Size word doing a number's job",
         "His whole objection to a claim is that a vague word “glosses over a "
         "lot of physical constraints”. Put the figure in, or drop the claim.",
         "@Jeyffre — the number carries the claim", Profile.SHORT_FORM),
    Rule("topic_opener", Severity.WARN, "Opener announces a topic instead of making a claim",
         "Every one of his openers is a proposition that could be wrong — "
         "“Your ability to grind is not what separates you from your peers.” "
         "“Some thoughts on X” has no truth value and nothing to disagree with.",
         "@Jeyffre — the first line is a claim", Profile.SHORT_FORM),
    Rule("unfilled_count", Severity.WARN, "Stated a count, did not deliver it",
         "“there are only three possible reasons” is a promise, and the post is "
         "then read for three. Delivering two reads as a draft.",
         "@Jeyffre — exhaustive enumeration", Profile.SHORT_FORM),
    Rule("unbacked_superlative", Severity.NOTE, "Superlative with nothing behind it",
         "He does write “the best writers” — and the very next line says what "
         "makes it true: “People understand our articles exactly the way we "
         "intend them to.” The claim is fine; the unbacked claim is not.",
         "@Jeyffre — a strong claim is followed by its reason",
         Profile.SHORT_FORM),
    Rule("undisclosed_stake", Severity.WARN, "Promotes something without disclosing the stake",
         "He states it outright — “I'm the founder of @RareSkills_io” — which is "
         "what lets him recommend it at all.",
         "@Jeyffre — disclosed interest", Profile.SHORT_FORM),

    Rule("no_forward_path", Severity.NOTE, "Ends without a next step",
         "They close on the next article or the deeper resource, never on a "
         "restatement of what was just read.",
         "RareSkills method — forward reference", Profile.TECHNICAL),
]

RULES_BY_KEY = {r.key: r for r in RULES}

# Rules that do not apply in the technical profile, and why.
PROFILE_EXEMPT = {
    Profile.TECHNICAL: {
        # RareSkills opens by defining scope in sentence one. That is correct
        # for a reader who came for the mechanism: the definition is a signpost,
        # not the payoff.
        "roadmap",
    },
    Profile.SHORT_FORM: {
        # "I read Google's paper so you don't have to" — first person is the
        # form, and the ban on it is an article rule about false authority.
        "first_person",
        # He writes "RareSkills has the best writers" and then immediately says
        # what makes it true. The blanket warning is replaced by
        # `unbacked_superlative`, which is the claim he actually avoids.
        "superlative",
        # "I will break it down.🧵" is his actual practice. My earlier guidance
        # said never announce a thread; the exemplar says otherwise, and the
        # exemplar wins.
        "roadmap",
        # A post is not an article; sections and tables do not apply.
        "no_h2", "heading_not_question", "table_context", "list_overuse",
        "thin_list_item", "long_paragraph",
    },
}


def rules_for(profile: str) -> List[Rule]:
    exempt = PROFILE_EXEMPT.get(profile, set())
    return [
        r for r in RULES
        if r.key not in exempt and (r.profile is None or r.profile == profile)
    ]


# Judgements a linter cannot make. These are the review questions, not checks.
SHORT_FORM_ADVISORY: List[str] = [
    "Does the post state the wrong answer first and then refine it? "
    "(“Your ability to grind is not what separates you… grinding is necessary "
    "but not sufficient… grinding with uncertain and delayed payoffs is.”)",
    "Are counter-examples named — “In India, Singapore, and China” — rather "
    "than gestured at?",
    "If you claim a list is exhaustive, is it? And is each item genuinely "
    "distinct from the others?",
    "Is the logical vocabulary exact — necessary, sufficient, prerequisite — "
    "or approximate?",
    "Does the first line name a specific claim, with its number, rather than a "
    "topic?",
    "Is the question the post exists to answer actually asked, or only implied?",
    "Would each post stand on its own if quoted without the rest?",
    "Where you disagree with someone, are you arguing with a specific word or "
    "figure of theirs, or with a summary of their position?",
    "If you are recommending something you profit from, have you said so?",
    "Is there a number, a snippet or a screenshot where an adjective is doing "
    "the work?",
]


TECHNICAL_ADVISORY: List[str] = [
    "Is every claim about behaviour demonstrated — runnable code, a gas number, "
    "an opcode trace, a diagram — or asserted in prose?",
    "Does explanation come before the code it explains, every time?",
    "Does complexity build: the simple case, then the real one, then the "
    "counterintuitive one?",
    "Where a technique does not always work, does the article say so and tell "
    "the reader to measure, rather than softening the language?",
    "Are the footguns shown happening in an example, rather than warned about "
    "in the abstract?",
    "Could a reader reproduce every result in this article from what is on the "
    "page?",
]


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
