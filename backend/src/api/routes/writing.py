"""Check a draft against the editorial standard before it ships."""

from __future__ import annotations

from typing import Any, Dict, List, Optional

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel

from ...core.logging import get_logger
from ...writing.lint import check
from ...writing.rules import ADVISORY, RULES

logger = get_logger("api.writing")
router = APIRouter(prefix="/api/writing", tags=["writing"])


class CheckRequest(BaseModel):
    text: str
    title: Optional[str] = None
    # article | outline | newsletter | tweet | video_script
    kind: str = "article"


@router.get("/rules")
async def list_rules() -> Dict[str, Any]:
    """The standard itself — what is checked, and where each rule comes from."""
    return {
        "rules": [
            {"key": r.key, "severity": r.severity, "title": r.title,
             "why": r.why, "source": r.source}
            for r in RULES
        ],
        "review_questions": ADVISORY,
    }


@router.post("/check")
async def check_draft(body: CheckRequest) -> Dict[str, Any]:
    if not body.text.strip():
        raise HTTPException(status_code=400, detail="text cannot be empty")
    result = check(body.text, body.title or "")
    result["kind"] = body.kind
    logger.info(
        "draft_checked", kind=body.kind, words=result["words"],
        passes=result["passes"], **result["counts"],
    )
    return result
