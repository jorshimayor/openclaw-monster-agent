"""The grouped reading list.

Resource tabs are shaped inconsistently — "Course | Provider | Level" with no
link column, "Repo | Owner | Type | Link", "Paper | Year | Category | Link" —
so the parser infers columns instead of trusting a fixed schema.
"""

from __future__ import annotations

import pytest

from src.agents.resources import (
    ResourceCollector,
    cache_get,
    cache_put,
    clear_cache,
    find_resource_header,
    infer_columns,
    load_resource_config,
    parse_resource_rows,
)

GITHUB_TAB = [
    ["GITHUB RESOURCE COLLECTIONS"],
    ["Let's Code  |  lets-code.co.in"],
    ["Repo", "Owner", "Type", "What is inside it", "Best for", "Link"],
    ["system-design-primer", "Donne Martin", "Reference repo", "The canonical free guide", "Starting point", "https://github.com/donnemartin/system-design-primer"],
    ["awesome-system-design", "Ashish", "Curated index", "Concepts and patterns", "Revision", "https://github.com/ashishps1/awesome"],
]

BOOKS_TAB = [
    ["BOOKS, PAPERS & NEWSLETTERS"],
    ["Let's Code"],
    ["Title", "Author / Owner", "Type", "Level", "Free?", "Why it matters", "Link"],
    ["Designing Data-Intensive Applications", "Kleppmann", "Book", "Advanced", "Paid", "The single most important book", "https://dataintensive.net/"],
]

NO_LINK_COLUMN = [
    ["FREE COURSES"],
    ["Let's Code"],
    ["Course", "Provider", "Level", "Notes"],
    ["System Design Primer", "Donne Martin", "Beginner", "See https://github.com/donnemartin/system-design-primer"],
]


@pytest.fixture(autouse=True)
def _clear():
    clear_cache()
    yield
    clear_cache()


def test_the_header_is_the_first_row_that_is_several_columns_wide() -> None:
    """These tabs open with a one-cell banner and a one-cell byline."""
    idx, header = find_resource_header(GITHUB_TAB)
    assert idx == 2
    assert header[0] == "Repo"


def test_columns_are_inferred_from_headers() -> None:
    idx, header = find_resource_header(GITHUB_TAB)
    cols = infer_columns(header, GITHUB_TAB[idx + 1 :])
    assert header[cols["title"]] == "Repo"
    assert header[cols["link"]] == "Link"
    assert header[cols["note"]] == "What is inside it"


def test_why_it_matters_is_preferred_as_the_note() -> None:
    idx, header = find_resource_header(BOOKS_TAB)
    cols = infer_columns(header, BOOKS_TAB[idx + 1 :])
    assert header[cols["note"]] == "Why it matters"


def test_a_url_is_found_even_with_no_link_column() -> None:
    items = parse_resource_rows(NO_LINK_COLUMN)
    assert len(items) == 1
    assert items[0]["url"].startswith("https://github.com/donnemartin")


def test_pricing_columns_are_never_used_as_the_note() -> None:
    items = parse_resource_rows(BOOKS_TAB)
    assert items[0]["note"] == "The single most important book"
    assert "Paid" not in items[0]["note"]


def test_rows_parse_into_title_url_note() -> None:
    items = parse_resource_rows(GITHUB_TAB)
    assert [i["title"] for i in items] == ["system-design-primer", "awesome-system-design"]
    assert all(i["url"].startswith("https://github.com/") for i in items)


def test_an_empty_tab_yields_nothing_rather_than_raising() -> None:
    assert parse_resource_rows([]) == []
    assert parse_resource_rows([["just a banner"]]) == []


# ── collection ───────────────────────────────────────────────────────────────


class FakeCollector(ResourceCollector):
    def __init__(self, sheet_values=None, repos=None, fail_github=False):
        super().__init__()
        self.sheet_values = sheet_values if sheet_values is not None else GITHUB_TAB
        self.repos = repos or []
        self.fail_github = fail_github
        self.calls = 0

    async def _call(self, tool, args):
        self.calls += 1
        if tool == "github.search_repositories":
            if self.fail_github:
                return {"skipped": True, "reason": "github server not running"}
            return {"items": self.repos}
        return {"values": self.sheet_values}


REPOS = [
    {"full_name": "jorshimayor/chelsea_bot", "html_url": "https://github.com/jorshimayor/chelsea_bot",
     "description": "Match bot", "language": "Python", "stargazers_count": 3, "updated_at": "2026-09-01T00:00:00Z"},
    {"full_name": "jorshimayor/fieldtilt", "html_url": "https://github.com/jorshimayor/fieldtilt",
     "description": "Football data", "language": "TypeScript", "stargazers_count": 1, "updated_at": "2026-09-08T00:00:00Z"},
]


@pytest.mark.asyncio
async def test_github_repos_are_listed_most_recently_updated_first() -> None:
    group = await FakeCollector(repos=REPOS)._github_group(
        {"enabled": True, "query": "user:jorshimayor", "group": "Your repos"}
    )
    assert [i["title"] for i in group["items"]] == [
        "jorshimayor/fieldtilt",
        "jorshimayor/chelsea_bot",
    ]
    assert group["items"][0]["meta"]["language"] == "TypeScript"


@pytest.mark.asyncio
async def test_a_dead_github_server_degrades_to_an_empty_group_with_a_reason() -> None:
    """One broken source must not blank the whole reading list."""
    group = await FakeCollector(fail_github=True)._github_group(
        {"enabled": True, "query": "user:jorshimayor"}
    )
    assert group["items"] == []
    assert "not running" in group["error"]


@pytest.mark.asyncio
async def test_a_failing_sheet_tab_reports_itself_without_killing_the_rest() -> None:
    class HalfBroken(FakeCollector):
        async def _call(self, tool, args):
            if args.get("range", "").startswith("Broken"):
                return {"error": "no such range"}
            return {"values": GITHUB_TAB}

    c = HalfBroken()
    good = await c._sheet_group({"key": "ok", "group": "Fine", "sheet_id": "s", "range": "Good!A1:H10"})
    bad = await c._sheet_group({"key": "bad", "group": "Bad", "sheet_id": "s", "range": "Broken!A1:H10"})
    assert len(good["items"]) == 2 and good["error"] is None
    assert bad["items"] == [] and bad["error"]


def test_results_are_cached_between_calls() -> None:
    assert cache_get("resources") is None
    cache_put("resources", {"groups": [], "total": 0})
    assert cache_get("resources") == {"groups": [], "total": 0}
    clear_cache()
    assert cache_get("resources") is None


def test_the_shipped_resource_config_is_valid() -> None:
    config = load_resource_config()
    tabs = config["resource_tabs"]
    assert tabs, "no resource tabs configured"
    assert all(t.get("sheet_id") and t.get("range") and t.get("group") for t in tabs)
    assert len({t["key"] for t in tabs}) == len(tabs), "duplicate resource tab keys"
    assert config["github"]["query"]


# ── envelopes and bands: what the real sheets and servers actually return ────

def test_the_mcp_content_envelope_is_unwrapped() -> None:
    """MCP servers may answer {"content":[{"type":"text","text":"<json>"}]}.
    Reading .items off the envelope finds nothing — 78 repos rendered as an
    empty group until this was handled."""
    import json as _json

    from src.agents.resources import unwrap_mcp_payload

    env = {"content": [{"type": "text", "text": _json.dumps({"items": [{"full_name": "a/b"}]})}]}
    assert unwrap_mcp_payload(env)["items"] == [{"full_name": "a/b"}]
    assert unwrap_mcp_payload({"items": [1]})["items"] == [1]
    assert unwrap_mcp_payload({"result": {"values": [[1]]}})["values"] == [[1]]
    assert unwrap_mcp_payload({"content": [{"type": "text", "text": "not json"}]}) == {
        "content": [{"type": "text", "text": "not json"}]
    }


WATCHLIST = [
    ["Stock", "", "Sector", "Current Price"],
    ["INTERNATIONAL"],
    ["COMPANY NAME", "TICKER SYMBOL"],
    ["", "GOOGL", "Consumer Goods", "331.41"],
    ["", "NVDA", "Consumer Goods", "224.23"],
    ["", "PLTR", "Consumer Goods", "315.59"],
]


def test_the_title_is_the_first_populated_column_not_the_first_named_one() -> None:
    """This watchlist heads column B "Stock" and leaves it blank, with the
    ticker in C. Trusting the header dropped every row."""
    items = parse_resource_rows(WATCHLIST)
    assert [i["title"] for i in items] == ["GOOGL", "NVDA", "PLTR"]


def test_repeated_header_bands_are_not_entries() -> None:
    assert "TICKER SYMBOL" not in [i["title"] for i in parse_resource_rows(WATCHLIST)]


def test_one_cell_section_bands_are_not_entries() -> None:
    rows = [
        ["Stock", "", "Sector", "Price", "Cap"],
        ["DOMESTIC"],
        ["COMPANY NAME", "TICKER SYMBOL"],
        ["Nascon Allied", "NASCON", "Consumer Goods", "71.00", "620"],
    ]
    assert [i["title"] for i in parse_resource_rows(rows)] == ["Nascon Allied"]


def test_the_curated_chain_resources_are_present_and_linked() -> None:
    """These are the interview-prep shelf: every entry needs somewhere to go."""
    config = load_resource_config()
    curated = config["curated"]
    keys = {g["key"] for g in curated}
    assert {"chain-evm", "chain-solana", "chain-cosmos", "chain-infra"} <= keys

    for group in curated:
        assert group["items"], f"{group['key']} is empty"
        for item in group["items"]:
            assert item["title"], f"untitled entry in {group['key']}"
            assert item["url"].startswith("https://"), f"{item['title']} has no usable link"
            assert item["note"], f"{item['title']} has no note saying why it matters"


def test_curated_links_are_unique() -> None:
    config = load_resource_config()
    urls = [i["url"] for g in config["curated"] for i in g["items"]]
    assert len(urls) == len(set(urls)), "the same link appears twice"
