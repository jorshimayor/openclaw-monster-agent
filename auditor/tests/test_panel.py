from auditor.agents.panel import survives
from auditor.schemas import Verdict


def v(refuted: bool) -> Verdict:
    return Verdict(model="m", refuted=refuted, reasoning="r")


def test_majority_refute_kills_the_finding():
    assert not survives([v(True), v(True), v(False)])


def test_minority_refute_survives():
    assert survives([v(True), v(False), v(False)])


def test_a_tie_kills_it():
    assert not survives([v(True), v(False)])


def test_an_empty_panel_is_not_a_pass():
    """If every panel model failed, that is no consensus — not consensus to ship."""
    assert not survives([])
