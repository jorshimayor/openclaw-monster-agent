"""One grouped reading list, pulled from where the material actually lives.

The study hub used to render a hardcoded array in the page. It went stale the
moment a sheet changed and knew nothing about the repos you actually work in.
This collects the same view from live sources:

  sheets — the resource tabs of your study kits (Books & Docs, GitHub
           Resources, Research Papers, Tools & Frameworks, …), one group per tab
  github — your own repos, so what you have built sits beside what you are
           reading
  curated — a static list in the config for things that live in neither

Resource tabs are shaped loosely and inconsistently — "Course | Provider |
Level", "Repo | Owner | Type | Link", "Paper | Year | Category | Link" — so
columns are inferred rather than declared: the first column is the title, the
link is whichever column holds URLs, and the note is the column that explains
why the thing matters.

Results are cached briefly: this is a page-load path fanning out to a dozen
network calls, and the underlying sheets change on the order of weeks.
"""

from __future__ import annotations

import json
import re
import time
from typing import Any, Dict, List, Optional, Tuple

from ..core.logging import get_logger
from .schedule_sync import _norm_header
from .study_sync import _config_path, _cell

logger = get_logger("agents.resources")

CACHE_TTL_SECONDS = 900

_URL_RE = re.compile(r"https?://[^\s,)]+", re.I)

_LINK_HEADERS = ("link", "url", "website", "href", "source", "repo link", "linkurl")
# Headers whose column explains why the item is worth your time.
_NOTE_HEADERS = (
    "whyitmatters", "whatisinsideit", "bestfor", "whenyouwoulduseit", "whatitdoes",
    "note", "notes", "description", "whatitis", "comment", "why",
)
_SKIP_HEADERS = ("free", "cost", "certificate", "freetier", "paid")

# Column labels that appear again mid-sheet as a sub-header band ("COMPANY NAME
# | TICKER SYMBOL" sitting above the tickers). They are never real entries.
_BAND_LABELS = {
    "companyname", "tickersymbol", "ticker", "symbol", "name", "title", "link",
    "url", "stock", "repo", "course", "paper", "tool", "item", "project",
    "description", "sector", "notes", "note", "owner", "provider", "type",
}


def unwrap_mcp_payload(result: Dict[str, Any]) -> Dict[str, Any]:
    """Get at the actual payload, whichever envelope the server used.

    MCP servers may answer with the content envelope —
    {"content":[{"type":"text","text":"<json string>"}]} — rather than the
    decoded object. Reading `result["items"]` off the envelope silently finds
    nothing, which is how 78 repos rendered as an empty group.
    """
    if not isinstance(result, dict):
        return {}
    content = result.get("content")
    if isinstance(content, list):
        for part in content:
            if isinstance(part, dict) and part.get("type") == "text":
                try:
                    decoded = json.loads(part.get("text") or "")
                except Exception:
                    continue
                if isinstance(decoded, dict):
                    return decoded
                if isinstance(decoded, list):
                    return {"items": decoded}
    if isinstance(result.get("result"), dict):
        return result["result"]
    return result


def _cache() -> Dict[str, Tuple[float, Any]]:
    if not hasattr(_cache, "_store"):
        _cache._store = {}  # type: ignore[attr-defined]
    return _cache._store  # type: ignore[attr-defined]


def cache_get(key: str) -> Optional[Any]:
    hit = _cache().get(key)
    if hit and (time.time() - hit[0]) < CACHE_TTL_SECONDS:
        return hit[1]
    return None


def cache_put(key: str, value: Any) -> None:
    _cache()[key] = (time.time(), value)


def clear_cache() -> None:
    _cache().clear()


def find_resource_header(values: List[List[Any]], search_rows: int = 8) -> Tuple[int, List[Any]]:
    """First row with at least three filled cells.

    These tabs open with a banner and a byline, each a single cell; the header
    is the first row that is actually several columns wide.
    """
    for idx, row in enumerate(values[:search_rows]):
        if sum(1 for c in row if str(c or "").strip()) >= 3:
            return idx, row
    return 0, (values[0] if values else [])


def infer_columns(header: List[Any], rows: List[List[Any]]) -> Dict[str, Optional[int]]:
    """{title, link, note} column indexes, inferred from headers then data."""
    title_idx: Optional[int] = None
    link_idx: Optional[int] = None
    note_idx: Optional[int] = None

    for idx, raw in enumerate(header):
        norm = _norm_header(raw)
        if not norm:
            continue
        if link_idx is None and norm in _LINK_HEADERS:
            link_idx = idx
        if note_idx is None and norm in _NOTE_HEADERS:
            note_idx = idx

    # The title is the leftmost column that is actually populated — not simply
    # the first named one. A watchlist can head column B "Stock" and leave it
    # blank, with the ticker in C; taking the header at face value drops every
    # row that has a ticker but no company name.
    sample = rows[:20]
    width = max([len(header)] + [len(r) for r in sample]) if sample else len(header)
    best_filled = 0
    for idx in range(width):
        if idx == link_idx:
            continue
        filled = sum(1 for r in sample if _cell(r, idx))
        # Strictly greater keeps the leftmost column on a tie, so an ordinary
        # sheet still titles on its first column.
        if filled > best_filled:
            title_idx, best_filled = idx, filled
    if title_idx is None:
        title_idx = next((i for i, h in enumerate(header) if _norm_header(h)), None)

    # No Link column? Find the column whose cells are actually URLs.
    if link_idx is None:
        for idx in range(max((len(r) for r in rows[:10]), default=0)):
            hits = sum(1 for r in rows[:10] if _URL_RE.search(_cell(r, idx)))
            if hits >= 2:
                link_idx = idx
                break

    # No explanatory column? Take the widest prose column that isn't the title
    # or the link, skipping pricing/admin columns.
    if note_idx is None:
        best, best_len = None, 0
        for idx in range(max((len(r) for r in rows[:10]), default=0)):
            if idx in (title_idx, link_idx):
                continue
            if _norm_header(header[idx] if idx < len(header) else "") in _SKIP_HEADERS:
                continue
            avg = sum(len(_cell(r, idx)) for r in rows[:10]) / max(1, len(rows[:10]))
            if avg > best_len:
                best, best_len = idx, avg
        if best_len >= 20:
            note_idx = best

    return {"title": title_idx, "link": link_idx, "note": note_idx}


def parse_resource_rows(values: List[List[Any]], limit: int = 200) -> List[Dict[str, str]]:
    """Sheet values → [{title, url, note}]. Never raises."""
    if not values:
        return []
    header_idx, header = find_resource_header(values)
    rows = values[header_idx + 1 :]
    cols = infer_columns(header, rows)
    if cols["title"] is None:
        return []

    # A section band ("DOMESTIC", "INTERNATIONAL") is a lone cell in a sheet
    # whose real rows are several columns wide.
    typical_width = max(
        (sum(1 for c in r if str(c or "").strip()) for r in rows[:20]), default=0
    )

    out: List[Dict[str, str]] = []
    for row in rows:
        filled = sum(1 for c in row if str(c or "").strip())
        if typical_width >= 3 and filled <= 1:
            continue
        title = _cell(row, cols["title"])
        if not title or title == _cell(header, cols["title"]):
            continue
        if _norm_header(title) in _BAND_LABELS:
            continue  # a repeated header band, not an entry
        raw_link = _cell(row, cols["link"]) if cols["link"] is not None else ""
        match = _URL_RE.search(raw_link) or _URL_RE.search(" ".join(str(c) for c in row))
        out.append(
            {
                "title": title[:200],
                "url": match.group(0).rstrip(".,);") if match else "",
                "note": (_cell(row, cols["note"]) if cols["note"] is not None else "")[:240],
            }
        )
        if len(out) >= limit:
            break
    return out


def load_resource_config() -> Dict[str, Any]:
    import json

    try:
        data = json.loads(_config_path().read_text())
    except Exception as exc:
        logger.warning("resource_config_unreadable", error=str(exc))
        return {}
    return {
        "resource_tabs": data.get("resource_tabs", []),
        "github": data.get("github", {}),
        "curated": data.get("curated", []),
    }


class ResourceCollector:
    def __init__(self) -> None:
        self._log = logger

    def _pa(self) -> Any:
        from .bus import get_event_bus

        return get_event_bus()._pa

    async def _call(self, tool: str, args: Dict[str, Any]) -> Dict[str, Any]:
        pa = self._pa()
        if pa is None:
            return {"error": "personal assistant not attached"}
        return await pa._call_mcp(tool, args)

    async def _sheet_group(self, spec: Dict[str, Any]) -> Dict[str, Any]:
        result = await self._call(
            "google_workspace.read_sheet",
            {"sheet_id": spec["sheet_id"], "range": spec["range"]},
        )
        if result.get("error") or result.get("skipped"):
            return {
                "key": spec.get("key", spec["range"]),
                "name": spec.get("group", spec["range"]),
                "source": "sheet",
                "items": [],
                "error": str(result.get("error") or result.get("reason")),
            }
        values = result.get("values") or unwrap_mcp_payload(result).get("values") or []
        return {
            "key": spec.get("key", spec["range"]),
            "name": spec.get("group", spec["range"]),
            "source": "sheet",
            "items": parse_resource_rows(values),
            "error": None,
        }

    async def _github_group(self, spec: Dict[str, Any]) -> Dict[str, Any]:
        """Your own repos, beside the reading list."""
        query = spec.get("query") or ""
        if not query:
            return {"key": "github", "name": "Your repos", "source": "github", "items": [], "error": None}
        result = await self._call(
            "github.search_repositories",
            {"query": query, "perPage": int(spec.get("limit", 30))},
        )
        if result.get("error") or result.get("skipped"):
            return {
                "key": "github",
                "name": spec.get("group", "Your repos"),
                "source": "github",
                "items": [],
                "error": str(result.get("error") or result.get("reason")),
            }
        payload = unwrap_mcp_payload(result)
        repos = payload.get("items") or payload.get("repositories") or []
        items = []
        for r in repos:
            if not isinstance(r, dict):
                continue
            items.append(
                {
                    "title": str(r.get("full_name") or r.get("name") or "")[:200],
                    "url": str(r.get("html_url") or ""),
                    "note": str(r.get("description") or "")[:240],
                    "meta": {
                        "language": r.get("language"),
                        "stars": r.get("stargazers_count"),
                        "updated": r.get("updated_at"),
                    },
                }
            )
        items.sort(key=lambda i: str(i.get("meta", {}).get("updated") or ""), reverse=True)
        return {
            "key": "github",
            "name": spec.get("group", "Your repos"),
            "source": "github",
            "items": items,
            "error": None,
        }

    async def collect(self, refresh: bool = False) -> Dict[str, Any]:
        if not refresh:
            cached = cache_get("resources")
            if cached is not None:
                return {**cached, "cached": True}

        config = load_resource_config()
        groups: List[Dict[str, Any]] = []

        for spec in config.get("resource_tabs", []):
            if not spec.get("enabled", True) or not spec.get("sheet_id"):
                continue
            try:
                groups.append(await self._sheet_group(spec))
            except Exception as exc:
                self._log.warning("resource_tab_failed", key=spec.get("key"), error=str(exc))

        gh = config.get("github") or {}
        if gh.get("enabled"):
            try:
                groups.append(await self._github_group(gh))
            except Exception as exc:
                self._log.warning("resource_github_failed", error=str(exc))

        for group in config.get("curated", []):
            groups.append(
                {
                    "key": group.get("key", group.get("group", "curated")),
                    "name": group.get("group", "Curated"),
                    "source": "curated",
                    "items": group.get("items", []),
                    "error": None,
                }
            )

        payload = {
            "groups": groups,
            "total": sum(len(g["items"]) for g in groups),
            "failed": [g["key"] for g in groups if g.get("error")],
            "cached": False,
        }
        cache_put("resources", payload)
        logger.info(
            "resources_collected",
            groups=len(groups),
            total=payload["total"],
            failed=payload["failed"],
        )
        return payload


_collector: Optional[ResourceCollector] = None


def get_resource_collector() -> ResourceCollector:
    global _collector
    if _collector is None:
        _collector = ResourceCollector()
    return _collector
