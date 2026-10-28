"""The shelf: what to read, watch, take and pay for.

study_sources.json answers "what am I doing this morning". This answers "where
do I go to learn X". It is a catalogue, not a schedule — nothing here is ever
filed as a commitment or reminds you about anything, which is the whole reason
it can be long without being a burden.

Organised by what a thing *is* — a course, a newsletter, an exam — rather than
what it is about, because that is the axis you search on when you want one.
"""

from __future__ import annotations

import json
import os
from pathlib import Path
from typing import Any, Dict, List, Optional

from ..core.logging import get_logger

logger = get_logger("agents.library")


def _config_path() -> Path:
    override = os.environ.get("LIBRARY_PATH")
    if override:
        return Path(override)
    # backend/src/agents/library.py → backend/config/library.json
    return Path(__file__).resolve().parent.parent.parent / "config" / "library.json"


def load_config() -> Dict[str, Any]:
    """Never raises: a broken shelf must not take the page down with it."""
    try:
        return json.loads(_config_path().read_text())
    except FileNotFoundError:
        logger.warning("library_config_missing", path=str(_config_path()))
    except json.JSONDecodeError as exc:
        logger.error("library_config_invalid", error=str(exc))
    return {"enabled": False, "sections": []}


def _item(raw: Dict[str, Any]) -> Optional[Dict[str, Any]]:
    title = str(raw.get("title") or "").strip()
    url = str(raw.get("url") or "").strip()
    if not title or not url:
        return None
    return {
        "title": title,
        "url": url,
        "price": str(raw.get("price") or "").strip() or None,
        "note": str(raw.get("note") or "").strip() or None,
    }


def shelf() -> Dict[str, Any]:
    """{prices_verified, sections: [{key, label, blurb, count, groups}]}.

    Items missing a title or a url are dropped rather than rendered as an
    empty row — a catalogue with holes in it stops being trusted, and a
    half-written entry is easier to notice by its absence.
    """
    config = load_config()
    if not config.get("enabled", True):
        return {"enabled": False, "sections": [], "total": 0}

    sections: List[Dict[str, Any]] = []
    total = 0
    for raw_section in config.get("sections") or []:
        groups: List[Dict[str, Any]] = []
        for raw_group in raw_section.get("groups") or []:
            items = [i for i in (_item(x) for x in raw_group.get("items") or []) if i]
            if not items:
                continue
            groups.append(
                {
                    "key": str(raw_group.get("key") or ""),
                    "label": str(raw_group.get("label") or ""),
                    "note": str(raw_group.get("note") or "").strip() or None,
                    "items": items,
                }
            )
        if not groups:
            continue
        count = sum(len(g["items"]) for g in groups)
        total += count
        sections.append(
            {
                "key": str(raw_section.get("key") or ""),
                "label": str(raw_section.get("label") or ""),
                "blurb": str(raw_section.get("blurb") or "").strip() or None,
                "count": count,
                "groups": groups,
            }
        )

    return {
        "enabled": True,
        # Prices go stale. Showing when they were last checked is the
        # difference between a figure you can budget against and a rumour.
        "prices_verified": config.get("prices_verified"),
        "sections": sections,
        "total": total,
    }
