from __future__ import annotations

import asyncio
from typing import List, Optional, Tuple

from tenacity import AsyncRetrying, stop_after_attempt, wait_exponential

from ..core.config import Settings
from ..core.logging import get_logger
from ..core.types import KnowledgeCrystals
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

    async def _notion_worker(self) -> None:
        logger.info("notion_worker_started", queue_size=self._notion_queue.qsize())
        while True:
            try:
                crystal = await self._notion_queue.get()
            except asyncio.CancelledError:
                logger.info("notion_worker_cancelled")
                return
            except Exception as exc:
                logger.exception("notion_worker_queue_error", error=str(exc))
                continue
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

    async def add(self, crystal: KnowledgeCrystals) -> str:
        KnowledgeCrystals.model_validate(crystal.model_dump())
        self._crystals.append(crystal)
        crystal_id = str(crystal.id)

        if self._notion_enabled:
            if self._notion_worker_task is None or self._notion_worker_task.done():
                self._notion_worker_task = asyncio.create_task(self._notion_worker())
            await self._notion_queue.put(crystal)

        logger.info(
            "crystal_added",
            crystal_id=crystal_id,
            source_task_id=str(crystal.source_task_id),
            total_crystals=len(self._crystals),
            notion_enabled=self._notion_enabled,
        )
        return crystal_id

    def list(
        self,
        category: Optional[str] = None,
        limit: int = 50,
    ) -> List[KnowledgeCrystals]:
        if limit <= 0:
            return []
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
        if not text or not self._crystals:
            return []
        if top_k <= 0:
            return []

        query_emb = self.memory._embed_simple(text)
        scored: List[Tuple[float, KnowledgeCrystals]] = []
        for crystal in self._crystals:
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
