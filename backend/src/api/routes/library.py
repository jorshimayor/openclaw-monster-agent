"""The shelf, read-only.

Catalogue rather than schedule: nothing here is tracked, chased or filed. It
is served whole because it is small and entirely static — paging a list you
read by scanning would cost a round trip to save nothing.
"""

from __future__ import annotations

from typing import Any, Dict

from fastapi import APIRouter

from ...agents.library import shelf

router = APIRouter(prefix="/api/library", tags=["library"])


@router.get("")
async def get_library() -> Dict[str, Any]:
    return shelf()
