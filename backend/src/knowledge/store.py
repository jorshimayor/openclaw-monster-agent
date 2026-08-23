from __future__ import annotations

import asyncio
from typing import List, Optional, Tuple

from sqlalchemy import select, or_, func
from sqlalchemy.ext.asyncio import AsyncSession

from tenacity import AsyncRetrying, stop_after_attempt, wait_exponential

from ..core.config import Settings
from ..core.db import get_session, is_db_available
from ..core.logging import get_logger
from ..core.types import KnowledgeCrystals
from ..models.knowledge import KnowledgeCrystalDB
from .memory import ExperienceMemory
from .extractor import KnowledgeExtractor

logger = get_logger(__name__)


class CrystallizedKnowledgeStore:
    def __init__(
        self,
        settings: Settings,
        memory: Optional[ExperienceMemory] = None,
        extractor: Optional[KnowledgeExtractor] = None,
    ) -> None:
        self.settings = settings
        self.memory = memory if memory is not None else ExperienceMemory()
        self.extractor = extractor
        self._crystals: List[KnowledgeCrystals] = []
        self._notion_enabled = bool(settings.notion_token)
        self._notion_queue: "asyncio.Queue[KnowledgeCrystals]" = asyncio.Queue()
        self._notion_worker_task: Optional[asyncio.Task] = None
        self._db_enabled = False

    async def bootstrap(self) -> None:
        self._db_enabled = is_db_available()
        if self._db_enabled:
            try:
                loaded = await self._load_all_from_db(limit=500)
                self._crystals = loaded
                logger.info(
                    "knowledge_store_bootstrapped_from_db",
                    loaded_count=len(self._crystals),
                )
                return
            except Exception as exc:
                logger.warning(
                    "knowledge_store_db_bootstrap_failed_fallback_to_memory",
                    error=str(exc),
                )
                self._db_enabled = False
        self._crystals = []

    async def _load_all_from_db(self, limit: int = 500) -> List[KnowledgeCrystals]:
        async with get_session() as session:
            session: AsyncSession
            stmt = (
                select(KnowledgeCrystalDB)
                .order_by(KnowledgeCrystalDB.created_at.desc())
                .limit(limit)
            )
            result = await session.execute(stmt)
            rows = result.scalars().all()
        return [row.to_domain() for row in rows]

    async def _notion_worker(self) -> None:
        logger.info("notion_worker_started", queue_size=self._notion_queue.qsize())
        while True:
            try:
                crystal = await self._notion_queue.get()
            except asyncio.CancelledError:
                logger.info("notion_worker_cancelled")
                return
            except Exception as exc:
                # A failing get() is unrecoverable (e.g. the owning event loop
                # was closed); retrying would busy-loop the thread forever.
                logger.exception("notion_worker_queue_error", error=str(exc))
                return
            try:
                async for attempt in AsyncRetrying(
                    stop=stop_after_attempt(3),
                    wait=wait_exponential(multiplier=0.5, min=0.3, max=5.0),
                    reraise=False,
                ):
                    with attempt:
                        await self._write_single_to_notion(crystal)
            except Exception as exc:
                logger.warning(
                    "notion_write_failed_after_retries",
                    crystal_id=str(crystal.id),
                    error=str(exc),
                )
            finally:
                self._notion_queue.task_done()

    async def _write_single_to_notion(self, crystal: KnowledgeCrystals) -> None:
        logger.debug(
            "notion_write_stub",
            crystal_id=str(crystal.id),
            entities=len(crystal.entities),
        )
        return None

    async def _persist_to_db(self, crystal: KnowledgeCrystals) -> None:
        if not self._db_enabled:
            return
        row = KnowledgeCrystalDB.from_domain(crystal)
        async with get_session() as session:
            session: AsyncSession
            existing = await session.get(KnowledgeCrystalDB, crystal.id)
            if existing is None:
                session.add(row)
            else:
                existing.entities = row.entities
                existing.strategies = row.strategies
                existing.pitfalls = row.pitfalls
                existing.frameworks = row.frameworks
                existing.summary = row.summary
                existing.category = row.category
                existing.raw_extras = row.raw_extras

    async def add(self, crystal: KnowledgeCrystals) -> str:
        KnowledgeCrystals.model_validate(crystal.model_dump())
        self._crystals.append(crystal)
        crystal_id = str(crystal.id)

        if self._db_enabled:
            try:
                await self._persist_to_db(crystal)
            except Exception as exc:
                logger.warning(
                    "knowledge_crystal_db_persist_failed",
                    crystal_id=crystal_id,
                    error=str(exc),
                )

        if self._notion_enabled:
            if self._notion_worker_task is None or self._notion_worker_task.done():
                self._notion_worker_task = asyncio.create_task(self._notion_worker())
            await self._notion_queue.put(crystal)

        try:
            from ..agents.bus import get_event_bus

            bus = get_event_bus()
            bus.emit_knowledge_crystal(
                crystal.id,
                crystal.summary or (crystal.entities[0] if crystal.entities else "New crystal"),
                task_id=crystal.source_task_id,
            )
        except Exception as exc:
            logger.warning(
                "knowledge_crystal_bus_emit_failed",
                crystal_id=crystal_id,
                error=str(exc),
            )

        logger.info(
            "crystal_added",
            crystal_id=crystal_id,
            source_task_id=str(crystal.source_task_id),
            total_crystals=len(self._crystals),
            notion_enabled=self._notion_enabled,
            db_enabled=self._db_enabled,
        )
        return crystal_id

    async def list(
        self,
        category: Optional[str] = None,
        limit: int = 50,
    ) -> List[KnowledgeCrystals]:
        if limit <= 0:
            return []
        if self._db_enabled:
            try:
                async with get_session() as session:
                    session: AsyncSession
                    stmt = select(KnowledgeCrystalDB)
                    if category:
                        cat_lower = category.lower()
                        pattern = f"%{cat_lower}%"
                        stmt = stmt.where(
                            or_(
                                func.lower(KnowledgeCrystalDB.category).like(pattern),
                                func.array_to_string(KnowledgeCrystalDB.entities, '|').ilike(pattern),
                                func.array_to_string(KnowledgeCrystalDB.strategies, '|').ilike(pattern),
                                func.array_to_string(KnowledgeCrystalDB.pitfalls, '|').ilike(pattern),
                                func.array_to_string(KnowledgeCrystalDB.frameworks, '|').ilike(pattern),
                            )
                        )
                    stmt = stmt.order_by(KnowledgeCrystalDB.created_at.desc()).limit(limit)
                    result = await session.execute(stmt)
                    rows = result.scalars().all()
                    return [row.to_domain() for row in rows]
            except Exception as exc:
                logger.warning("knowledge_list_db_failed_fallback", error=str(exc))
        crystals = self._crystals
        if category:
            cat_lower = category.lower()
            filtered: List[KnowledgeCrystals] = []
            for c in crystals:
                haystack = " ".join(
                    c.entities + c.strategies + c.pitfalls + c.frameworks
                ).lower()
                if cat_lower in haystack:
                    filtered.append(c)
            crystals = filtered
        crystals_sorted = sorted(
            crystals, key=lambda c: c.created_at, reverse=True
        )
        return crystals_sorted[:limit]

    def _crystal_content(self, crystal: KnowledgeCrystals) -> str:
        parts: List[str] = []
        parts.extend(crystal.entities)
        parts.extend(crystal.strategies)
        parts.extend(crystal.pitfalls)
        parts.extend(crystal.frameworks)
        return " ".join(parts)

    async def query(
        self,
        text: str,
        top_k: int = 10,
    ) -> List[Tuple[KnowledgeCrystals, float]]:
        if not text:
            return []
        crystals = await self.list(limit=max(200, top_k * 10))
        if not crystals:
            return []
        if top_k <= 0:
            return []
        query_emb = self.memory._embed_simple(text)
        scored: List[Tuple[float, KnowledgeCrystals]] = []
        for crystal in crystals:
            content = self._crystal_content(crystal)
            content_emb = self.memory._embed_simple(content)
            sim = self.memory._cosine(query_emb, content_emb)
            scored.append((sim, crystal))
        scored.sort(key=lambda t: t[0], reverse=True)
        top = scored[:top_k]
        return [(crystal, sim) for sim, crystal in top]

    async def sync_to_notion(self) -> int:
        count = len(self._crystals)
        logger.info(
            "notion_sync_stub",
            would_sync_count=count,
            enabled=self._notion_enabled,
        )
        return 0

    async def delete(self, crystal_id: str) -> bool:
        removed = False
        kept: List[KnowledgeCrystals] = []
        for c in self._crystals:
            if str(c.id) == crystal_id:
                removed = True
            else:
                kept.append(c)
        self._crystals = kept
        if self._db_enabled:
            try:
                async with get_session() as session:
                    session: AsyncSession
                    from uuid import UUID as _UUID
                    row = await session.get(KnowledgeCrystalDB, _UUID(crystal_id))
                    if row is not None:
                        await session.delete(row)
                        removed = True
            except Exception as exc:
                logger.warning("knowledge_delete_db_failed", error=str(exc))
        if removed:
            logger.info("knowledge_crystal_deleted", crystal_id=crystal_id)
        return removed

    async def get(self, crystal_id: str) -> Optional[KnowledgeCrystals]:
        if self._db_enabled:
            try:
                async with get_session() as session:
                    session: AsyncSession
                    from uuid import UUID as _UUID
                    row = await session.get(KnowledgeCrystalDB, _UUID(crystal_id))
                    if row is not None:
                        return row.to_domain()
            except Exception as exc:
                logger.warning("knowledge_get_db_failed", error=str(exc))
        for c in self._crystals:
            if str(c.id) == crystal_id:
                return c
        return None
