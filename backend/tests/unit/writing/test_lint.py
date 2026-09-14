"""The editorial linter.

Two things matter more than coverage: every rule must trace to a line in the
style guides, and a clean draft must produce no findings. A linter that cries
wolf gets switched off, and then nothing is checked at all.
"""

from __future__ import annotations

import pytest

from src.writing.lint import check
from src.writing.rules import ADVISORY, RULES, Severity

# Written to the house style: landscape-setting introduction, question headings,
# terms explained in a subordinate clause on first use, active voice.
CLEAN = """# How Does a Hypervisor Allocate Resources?

As organizations scaled workloads onto shared virtual infrastructure, questions
about predictable performance became harder to ignore. Contention between tenants
on one physical host can surface as latency that no amount of application tuning
will remove.

## What Does a Hypervisor Actually Allocate?

A hypervisor, which creates and manages virtual machines on a single physical
host, divides three resources: processor time, memory, and bandwidth. Each uses a
different mechanism, and each fails differently under pressure.

Processor time is the most visible. The hypervisor schedules virtual processors
onto physical cores, and when demand exceeds supply, some machines wait. That wait
appears inside the guest as steal time.

## How Does Memory Allocation Differ From Processor Scheduling?

Memory cannot be time-sliced the way processor cycles can. A page belongs to one
guest at a time, so a host that has promised more memory than it holds must
reclaim pages from somewhere.
"""


def test_a_clean_draft_passes_with_no_findings() -> None:
    result = check(CLEAN, "How Does a Hypervisor Allocate Resources?")
    assert result["passes"] is True
    assert result["findings"] == [], [f["rule"] for f in result["findings"]]


@pytest.mark.parametrize(
    "rule,text",
    [
        ("marketing", "## A\n\nThis robust and seamless platform is cutting-edge."),
        ("filler", "## A\n\nIt is important to note that the server restarts."),
        ("superlative", "## A\n\nThis is the best option for most teams."),
        ("absolute", "## A\n\nThe server never fails under load."),
        ("british", "## A\n\nOptimise the organisation's licence handling."),
        ("first_person", "## A\n\nI recommend setting up a firewall first."),
        ("passive", "## A\n\nResources are allocated to each guest by the hypervisor."),
        ("roadmap", "## A\n\nIn this article, we will discuss three options."),
        ("cliche_opener", "## A\n\nIn today's fast-paced world, uptime matters."),
    ],
)
def test_each_rule_fires_on_its_own_violation(rule: str, text: str) -> None:
    fired = {f["rule"] for f in check(text)["findings"]}
    assert rule in fired, f"{rule} did not fire; got {fired}"


def test_a_block_level_finding_fails_the_standard() -> None:
    assert check("## A\n\nA revolutionary, game-changing platform.")["passes"] is False
    assert check(CLEAN)["passes"] is True


def test_code_blocks_are_never_linted() -> None:
    """`optimise` inside a snippet is somebody else's API, not a spelling slip."""
    text = CLEAN + "\n\n```python\ndef optimise(colour):  # I always return None\n    pass\n```\n"
    result = check(text)
    assert result["findings"] == [], [f["rule"] for f in result["findings"]]


def test_inline_code_is_not_linted() -> None:
    text = CLEAN + "\n\nCall `analyse()` to start.\n"
    assert not any(f["rule"] == "british" for f in check(text)["findings"])


def test_an_acronym_is_flagged_only_before_it_is_expanded() -> None:
    bad = "## A\n\nA VDS gives dedicated resources. Virtual dedicated server (VDS) costs more."
    assert any(f["rule"] == "acronym" for f in check(bad)["findings"])

    good = "## A\n\nA virtual dedicated server (VDS) gives dedicated resources. The VDS costs more."
    assert not any(f["rule"] == "acronym" for f in check(good)["findings"])


def test_common_technical_acronyms_are_not_flagged() -> None:
    """Expanding API and CPU every time reads as noise, not rigour."""
    text = CLEAN + "\n\nThe API reports CPU and RAM usage over HTTP as JSON.\n"
    assert not any(f["rule"] == "acronym" for f in check(text)["findings"])


def test_a_bare_label_heading_is_flagged_but_a_question_is_not() -> None:
    assert any(f["rule"] == "heading_not_question"
               for f in check("## Resource Allocation\n\nText here.")["findings"])
    assert not any(f["rule"] == "heading_not_question"
                   for f in check("## How Does It Allocate Resources?\n\nText.")["findings"])


def test_a_table_needs_prose_on_both_sides() -> None:
    bare = "## Compare\n\n| A | B |\n|---|---|\n| 1 | 2 |\n\n## Next Section\n\nText."
    assert any(f["rule"] == "table_context" for f in check(bare)["findings"])

    framed = (
        "## Compare\n\nThe two differ in three ways, set out below.\n\n"
        "| A | B |\n|---|---|\n| 1 | 2 |\n\n"
        "The second column is what changes under load.\n"
    )
    assert not any(f["rule"] == "table_context" for f in check(framed)["findings"])


def test_an_article_with_no_sections_fails() -> None:
    result = check("Just one long paragraph with no headings at all.")
    assert result["passes"] is False
    assert any(f["rule"] == "no_h2" for f in result["findings"])


def test_findings_carry_their_source_so_they_can_be_checked() -> None:
    """Every finding cites the guideline it came from — a rule you cannot trace
    is one you will argue with instead of fixing."""
    for finding in check("## A\n\nA robust and seamless solution.")["findings"]:
        assert finding["source"], finding
        assert finding["why"], finding


def test_every_rule_declares_a_source_and_severity() -> None:
    valid = {Severity.BLOCK, Severity.WARN, Severity.NOTE}
    for rule in RULES:
        assert rule.severity in valid, rule
        assert rule.source, rule
        assert rule.why, rule


def test_review_questions_are_returned_for_the_judgement_calls() -> None:
    """The linter deliberately does not grade structure — it asks."""
    result = check(CLEAN)
    assert result["review_questions"] == ADVISORY
    assert any("buried" in q for q in result["review_questions"])


# ── the technical profile (RareSkills method) ────────────────────────────────

from src.writing.rules import Profile, TECHNICAL_ADVISORY  # noqa: E402

# Past TECHNICAL_DEPTH_WORDS, which is where the method expects a piece to
# declare its assumptions and carry working code.
LONG_PROSE = "\n\n".join(
    ["Each paragraph explains part of the mechanism in ordinary prose without "
     "showing any of it running or measuring anything at all."] * 60
)


def test_a_performance_claim_without_a_measurement_fails() -> None:
    """Their articles put the number next to the claim: "4860 gas vs 2758 gas"."""
    text = "## How Does Packing Work?\n\nPacking is more efficient and saves gas."
    result = check(text, profile=Profile.TECHNICAL)
    assert result["passes"] is False
    assert any(f["rule"] == "unproven_claim" for f in result["findings"])


def test_a_measurement_in_the_same_paragraph_discharges_the_claim() -> None:
    text = (
        "## How Does Packing Work?\n\n"
        "Packing is more efficient: 22,790 gas against 26,145 gas for separate slots."
    )
    assert not any(
        f["rule"] == "unproven_claim"
        for f in check(text, profile=Profile.TECHNICAL)["findings"]
    )


def test_performance_claims_are_not_checked_in_the_explanatory_profile() -> None:
    """The rule is RareSkills', not the house style's — it must not leak."""
    text = "## How Does Packing Work?\n\nPacking is more efficient and saves gas."
    assert not any(
        f["rule"] == "unproven_claim" for f in check(text)["findings"]
    )


def test_a_long_technical_piece_must_declare_its_prerequisites() -> None:
    text = f"# Storage\n\n## What Is a Slot?\n\n{LONG_PROSE}\n\nRead Part 2 next."
    fired = {f["rule"] for f in check(text, profile=Profile.TECHNICAL)["findings"]}
    assert "no_prerequisites" in fired

    with_prereq = text.replace(
        "## What Is a Slot?",
        "This assumes you understand how the EVM addresses storage.\n\n## What Is a Slot?",
    )
    fired2 = {f["rule"] for f in check(with_prereq, profile=Profile.TECHNICAL)["findings"]}
    assert "no_prerequisites" not in fired2


def test_a_mechanism_explained_only_in_prose_is_flagged() -> None:
    """A mechanism article with no runnable code is a summary, and the reader
    came for the mechanism."""
    text = f"# Storage\n\n## What Is a Slot?\n\n{LONG_PROSE}\n\nRead Part 2 next."
    assert any(
        f["rule"] == "thin_on_code"
        for f in check(text, profile=Profile.TECHNICAL)["findings"]
    )


def test_a_technical_piece_should_point_somewhere_next() -> None:
    text = f"# Storage\n\nThis assumes you know the EVM.\n\n## What Is a Slot?\n\n{LONG_PROSE}"
    assert any(
        f["rule"] == "no_forward_path"
        for f in check(text, profile=Profile.TECHNICAL)["findings"]
    )


def test_stating_the_answer_up_front_is_allowed_in_the_technical_profile() -> None:
    """The two houses genuinely disagree here, and the disagreement is kept
    rather than reconciled: RareSkills opens by defining scope, because for a
    reader who came for the mechanism the definition is a signpost, not the
    payoff."""
    text = "## What Is Gas?\n\nIn this article, we will cover three optimizations."
    assert not any(
        f["rule"] == "roadmap" for f in check(text, profile=Profile.TECHNICAL)["findings"]
    )
    assert any(f["rule"] == "roadmap" for f in check(text)["findings"])


def test_the_house_rules_still_apply_in_the_technical_profile() -> None:
    """Profiles change what is added and exempted, not everything."""
    text = "## A\n\nThis robust and seamless approach is revolutionary."
    fired = {f["rule"] for f in check(text, profile=Profile.TECHNICAL)["findings"]}
    assert "marketing" in fired


def test_the_technical_profile_adds_its_own_review_questions() -> None:
    result = check(CLEAN, profile=Profile.TECHNICAL)
    assert all(q in result["review_questions"] for q in TECHNICAL_ADVISORY)
    assert any("reproduce every result" in q for q in result["review_questions"])
