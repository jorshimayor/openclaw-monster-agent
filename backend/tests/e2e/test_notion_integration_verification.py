from __future__ import annotations

from typing import Any, Dict, List
from unittest.mock import AsyncMock, MagicMock, patch
from uuid import uuid4, UUID

import pytest
from pydantic import ValidationError

from src.core.config import Settings
from src.core.types import KnowledgeCrystals, Task, TaskStatus
from src.knowledge.memory import ExperienceMemory
from src.knowledge.store import CrystallizedKnowledgeStore
from src.orchestration import pipeline as pipeline_module
from src.orchestration import steps as pipeline_steps

pytestmark = pytest.mark.asyncio(loop_scope="session")


def _make_settings(**overrides) -> Settings:
    base = Settings.model_construct(
        nvidia_nim_api_key="",
        groq_api_key="",
        google_api_key="",
        github_token="",
        notion_token="",
        notion_db_id="",
        slack_token="",
        google_workspace_client_id="",
        google_workspace_client_secret="",
        hashnode_token="",
        hashnode_publication_id="",
    )
    for k, v in overrides.items():
        object.__setattr__(base, k, v)
    return base


def _make_crystal(**overrides) -> KnowledgeCrystals:
    data: Dict[str, Any] = {
        "id": uuid4(),
        "entities": ["Uniswap v4", "Solidity"],
        "strategies": ["Audit hooks before deployment"],
        "pitfalls": ["Missing reentrancy guard"],
        "frameworks": ["Foundry"],
        "source_task_id": uuid4(),
    }
    data.update(overrides)
    return KnowledgeCrystals(**data)


async def test_store_add_sets_notion_queue_when_token_set() -> None:
    settings = _make_settings(
        notion_token="notion-mock-token-abc123",
        notion_db_id="db-mock-id",
    )
    store = CrystallizedKnowledgeStore(settings, memory=ExperienceMemory())
    crystal = _make_crystal()

    await store.add(crystal)

    assert store._notion_enabled is True
    assert store._notion_queue.qsize() == 1, (
        "Expected crystal to be enqueued to notion queue when token is set"
    )


async def test_store_add_skips_queue_when_no_token() -> None:
    settings = _make_settings(notion_token="", notion_db_id="")
    store = CrystallizedKnowledgeStore(settings, memory=ExperienceMemory())
    crystal = _make_crystal()

    await store.add(crystal)

    assert store._notion_enabled is False
    assert store._notion_queue.qsize() == 0, (
        "Expected notion queue to remain empty when NOTION_TOKEN is blank"
    )


async def test_sync_to_notion_stub_returns_int() -> None:
    settings = _make_settings(notion_token="present-but-stubbed")
    store = CrystallizedKnowledgeStore(settings, memory=ExperienceMemory())
    crystal = _make_crystal()
    await store.add(crystal)

    result = await store.sync_to_notion()

    assert isinstance(result, int), (
        f"sync_to_notion() must return int (stub count), got {type(result).__name__}"
    )
    assert result == 0


async def test_step11_reflection_invokes_crystallizer_saves_store() -> None:
    from src.core.config import get_settings

    settings = get_settings()
    memory = ExperienceMemory()

    fake_task = Task(
        id=uuid4(),
        description="Blog about Uniswap v4 hook audit patterns + zk-SNARKs study plan",
        status=TaskStatus.RUNNING,
        outputs={},
    )

    fake_final_report = (
        "Blog drafted covering hook lifecycle, fee-on-transfer checks, and a 4-module zkSNARKs study plan."
    )

    expected_crystal = _make_crystal(source_task_id=fake_task.id)

    async def fake_extract(*args, **kwargs) -> KnowledgeCrystals:
        return expected_crystal

    # step11 reads store.extractor and calls .extract(final_output, task_id) —
    # inject the fake through the store constructor (the old patch targeted a
    # module attribute that doesn't exist and a method step11 never calls).
    fake_extractor = MagicMock()
    fake_extractor.extract = AsyncMock(side_effect=fake_extract)
    store = CrystallizedKnowledgeStore(settings, memory=memory, extractor=fake_extractor)

    async def fake_llm_generate(*args, **kwargs) -> Dict[str, Any]:
        return {
            "provider": "mock",
            "model": "mock-model",
            "response": "Reflection complete: 3 lessons identified.",
        }

    fake_llm = MagicMock()
    fake_llm.generate = AsyncMock(side_effect=fake_llm_generate)

    original_add = store.add
    add_calls: List[KnowledgeCrystals] = []

    async def spy_add(crystal: KnowledgeCrystals) -> str:
        add_calls.append(crystal)
        return await original_add(crystal)

    store.add = spy_add

    step_result, state = await pipeline_steps.step11_post_task_reflection(
        final_output=fake_final_report,
        task=fake_task,
        crystallizer_agent=None,
        llm=fake_llm,
        tools=None,
        store=store,
        memory=memory,
    )

    assert len(add_calls) >= 1 or len(await store.list()) >= 1, (
        "Step11 reflection did not save a crystal via store.add()"
    )

    crystals_after = await store.list()
    assert len(crystals_after) >= 1, (
        f"Expected 1+ crystal after step11, got {len(crystals_after)}"
    )


def test_knowledge_crystals_schema_validation() -> None:
    """The actual schema contract: `id` auto-generates when absent (it has a
    default_factory — the old test wrongly asserted it was required, and
    KeyError'd deleting a key it never set); `source_task_id` IS required."""
    valid_uuid = uuid4()
    source_uuid = uuid4()

    valid_payload: Dict[str, Any] = {
        "id": str(valid_uuid),
        "entities": ["Uniswap"],
        "strategies": [],
        "pitfalls": [],
        "frameworks": [],
        "source_task_id": str(source_uuid),
    }
    valid_crystal = KnowledgeCrystals.model_validate(valid_payload)
    assert valid_crystal.id == valid_uuid

    # id omitted → auto-generated, unique per crystal
    no_id_payload = {k: v for k, v in valid_payload.items() if k != "id"}
    c1 = KnowledgeCrystals.model_validate(no_id_payload)
    c2 = KnowledgeCrystals.model_validate(no_id_payload)
    assert c1.id and c2.id and c1.id != c2.id

    # source_task_id is the genuinely required field
    with pytest.raises(ValidationError):
        KnowledgeCrystals.model_validate(
            {k: v for k, v in valid_payload.items() if k != "source_task_id"}
        )


async def test_store_query_by_domain_returns_ordered() -> None:
    settings = _make_settings(notion_token="")
    memory = ExperienceMemory()
    store = CrystallizedKnowledgeStore(settings, memory=memory)

    web3_crystal = _make_crystal(
        id=uuid4(),
        entities=["Solidity", "Uniswap hook", "Ethereum", "DeFi"],
        strategies=["Before/after hook lifecycle", "Fee math"],
        pitfalls=["Reentrancy in custom hooks"],
        frameworks=["Foundry", "ERC-20"],
    )
    web2_crystal = _make_crystal(
        id=uuid4(),
        entities=["React", "Next.js", "TypeScript", "Tailwind"],
        strategies=["SSR hydration", "Client components"],
        pitfalls=["Memory leaks in useEffect"],
        frameworks=["Next.js", "Zustand"],
    )
    football_crystal = _make_crystal(
        id=uuid4(),
        entities=["Premier League", "formation 4-3-3", "pressing", "xG"],
        strategies=["High press triggers", "Full-back overlap"],
        pitfalls=["Counter-attack vulnerability"],
        frameworks=["Opta", "WyScout"],
    )

    for c in (web3_crystal, web2_crystal, football_crystal):
        await store.add(c)

    results = await store.query("Solidity hook audit patterns", top_k=3)

    assert isinstance(results, list)
    assert len(results) >= 3, f"Expected 3 scored results, got {len(results)}"

    first_crystal, first_score = results[0]
    first_entities_lower = " ".join(first_crystal.entities).lower()
    assert (
        "solidity" in first_entities_lower or "uniswap" in first_entities_lower
    ), (
        f"Expected top query result for 'Solidity hook' to be web3 crystal, "
        f"got entities={first_crystal.entities} score={first_score}"
    )

    scores = [score for _crystal, score in results]
    assert scores == sorted(scores, reverse=True), (
        f"Query results not ordered descending by score: {scores}"
    )
