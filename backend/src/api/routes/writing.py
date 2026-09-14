"""Check a draft against the editorial standard before it ships."""

from __future__ import annotations

from typing import Any, Dict, List, Optional

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel

from ...core.logging import get_logger
from ...writing.lint import check
from ...writing.rules import ADVISORY, RULES, Profile, rules_for

logger = get_logger("api.writing")
router = APIRouter(prefix="/api/writing", tags=["writing"])


class CheckRequest(BaseModel):
    text: str
    title: Optional[str] = None
    # article | outline | newsletter | tweet | video_script
    kind: str = "article"
    # explanatory (house style) | technical (RareSkills method)
    profile: str = Profile.EXPLANATORY


@router.get("/rules")
async def list_rules(profile: str = Profile.EXPLANATORY) -> Dict[str, Any]:
    """The standard itself — what is checked, and where each rule comes from."""
    return {
        "profile": profile,
        "rules": [
            {"key": r.key, "severity": r.severity, "title": r.title,
             "why": r.why, "source": r.source, "profile": r.profile}
            for r in rules_for(profile)
        ],
        "review_questions": ADVISORY,
    }


@router.post("/check")
async def check_draft(body: CheckRequest) -> Dict[str, Any]:
    if not body.text.strip():
        raise HTTPException(status_code=400, detail="text cannot be empty")
    if body.profile not in (Profile.EXPLANATORY, Profile.TECHNICAL):
        raise HTTPException(
            status_code=400,
            detail=f"profile must be {Profile.EXPLANATORY!r} or {Profile.TECHNICAL!r}",
        )
    result = check(body.text, body.title or "", profile=body.profile)
    result["kind"] = body.kind
    logger.info(
        "draft_checked", kind=body.kind, profile=body.profile, words=result["words"],
        passes=result["passes"], **result["counts"],
    )
    return result
