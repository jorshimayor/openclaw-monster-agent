from __future__ import annotations

import asyncio
import time
from typing import Any, Dict, List, Optional
from uuid import UUID

from fastapi import APIRouter, HTTPException, Request
from pydantic import BaseModel, Field

from ...core.logging import get_logger
from ...core.types import KnowledgeCrystals

logger = get_logger(__name__)
router = APIRouter(prefix="/api/knowledge", tags=["knowledge"])


class KnowledgeCrystalResponse(BaseModel):
    id: UUID
    entities: List[str]
    strategies: List[str]
    pitfalls: List[str]
    frameworks: List[str]
    source_task_id: Optional[UUID]
    created_at: str

    @classmethod
    def from_model(cls, c: KnowledgeCrystals) -> "KnowledgeCrystalResponse":
        return cls(
            id=c.id,
            entities=list(c.entities),
            strategies=list(c.strategies),
            pitfalls=list(c.pitfalls),
            frameworks=list(c.frameworks),
            source_task_id=c.source_task_id,
            created_at=c.created_at.isoformat() if hasattr(c.created_at, "isoformat") else str(c.created_at),
        )


class KnowledgeQueryRequest(BaseModel):
    query: str
    top_k: int = Field(default=10, ge=1, le=50)
    category: Optional[str] = None


class KnowledgeQueryScoredResult(BaseModel):
    crystal: KnowledgeCrystalResponse
    score: float


class KnowledgeQueryResponse(BaseModel):
    query: str
    results: List[KnowledgeQueryScoredResult]
    took_ms: int


class KnowledgeSyncResponse(BaseModel):
    queued: int


class KnowledgeDeleteResponse(BaseModel):
    success: bool
    id: UUID


def _get_store(request: Request):
    store = getattr(request.app.state, "knowledge_store", None)
    if store is None:
        raise HTTPException(status_code=503, detail="Knowledge store not available")
    return store


@router.get("", response_model=List[KnowledgeCrystalResponse])
async def list_knowledge(
    request: Request,
    category: Optional[str] = None,
    skip: int = 0,
    limit: int = 50,
):
    store = _get_store(request)
    try:
        crystals = await store.list(category=category, limit=max(1, limit + skip))
        if skip > 0:
            crystals = crystals[skip:]
        crystals = crystals[:limit]
        logger.info(
            "knowledge_list_returned",
            count=len(crystals),
            category=category,
            limit=limit,
        )
        return [KnowledgeCrystalResponse.from_model(c) for c in crystals]
    except HTTPException:
        raise
    except Exception as exc:
        logger.exception("knowledge_list_failed", error=str(exc))
        raise HTTPException(status_code=500, detail=str(exc))


@router.post("/query", response_model=KnowledgeQueryResponse)
async def query_knowledge(
    request: Request,
    body: KnowledgeQueryRequest,
):
    store = _get_store(request)
    start = time.perf_counter()
    try:
        scored = await store.query(text=body.query, top_k=body.top_k)
        results: List[KnowledgeQueryScoredResult] = []
        for crystal, sim in scored:
            results.append(
                KnowledgeQueryScoredResult(
                    crystal=KnowledgeCrystalResponse.from_model(crystal),
                    score=float(sim),
                )
            )
        took_ms = int((time.perf_counter() - start) * 1000)
        logger.info(
            "knowledge_query_returned",
            query_len=len(body.query),
            top_k=body.top_k,
            results=len(results),
            took_ms=took_ms,
        )
        return KnowledgeQueryResponse(
            query=body.query,
            results=results,
            took_ms=took_ms,
        )
    except HTTPException:
        raise
    except Exception as exc:
        logger.exception("knowledge_query_failed", error=str(exc))
        raise HTTPException(status_code=500, detail=str(exc))


@router.get("/{id}", response_model=KnowledgeCrystalResponse)
async def get_knowledge(request: Request, id: UUID):
    store = _get_store(request)
    try:
        crystal = await store.get(str(id))
        if crystal is None:
            raise HTTPException(status_code=404, detail=f"Knowledge crystal not found: {id}")
        return KnowledgeCrystalResponse.from_model(crystal)
    except HTTPException:
        raise
    except Exception as exc:
        logger.exception("knowledge_get_failed", id=str(id), error=str(exc))
        raise HTTPException(status_code=500, detail=str(exc))


@router.delete("/{id}", response_model=KnowledgeDeleteResponse)
async def delete_knowledge(request: Request, id: UUID):
    store = _get_store(request)
    try:
        removed = await store.delete(str(id))
        if not removed:
            raise HTTPException(status_code=404, detail=f"Knowledge crystal not found: {id}")
        logger.info("knowledge_deleted", id=str(id))
        return KnowledgeDeleteResponse(success=True, id=id)
    except HTTPException:
        raise
    except Exception as exc:
        logger.exception("knowledge_delete_failed", id=str(id), error=str(exc))
        raise HTTPException(status_code=500, detail=str(exc))


@router.post("/sync", response_model=KnowledgeSyncResponse)
async def sync_knowledge(request: Request):
    store = _get_store(request)
    try:
        n_task = asyncio.create_task(store.sync_to_notion())
        n = len(getattr(store, "_crystals", []))
        logger.info("knowledge_sync_queued", n=n)
        return KnowledgeSyncResponse(queued=n)
    except HTTPException:
        raise
    except Exception as exc:
        logger.exception("knowledge_sync_failed", error=str(exc))
        raise HTTPException(status_code=500, detail=str(exc))
