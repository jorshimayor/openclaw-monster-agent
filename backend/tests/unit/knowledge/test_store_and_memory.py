from __future__ import annotations

import pytest
from uuid import uuid4

from src.core.config import get_settings
from src.core.types import AgentRole, AgentResult, KnowledgeCrystals
from src.knowledge.memory import ExperienceMemory, TECH_VOCAB
from src.knowledge.store import CrystallizedKnowledgeStore
from src.knowledge.extractor import KnowledgeExtractor


def test_memory_embed_simple_shape():
    mem = ExperienceMemory()
    emb = mem._embed_simple("ethereum solidity react python")
    assert isinstance(emb, list)
    assert len(emb) == len(TECH_VOCAB)
    assert any(v > 0 for v in emb)


def test_memory_embed_simple_normalized():
    mem = ExperienceMemory()
    emb1 = mem._embed_simple("ethereum solidity")
    emb2 = mem._embed_simple("react python fastapi")
    import math

    norm1 = math.sqrt(sum(v * v for v in emb1))
    norm2 = math.sqrt(sum(v * v for v in emb2))
    assert abs(norm1 - 1.0) < 1e-6 or norm1 == 0.0
    assert abs(norm2 - 1.0) < 1e-6 or norm2 == 0.0


def test_memory_cosine_identical():
    mem = ExperienceMemory()
    a = mem._embed_simple("ethereum solidity smart contract uniswap defi")
    sim = mem._cosine(a, a)
    assert abs(sim - 1.0) < 1e-6


def test_memory_cosine_orthogonal_approx():
    mem = ExperienceMemory()
    a = mem._embed_simple("ethereum solidity defi uniswap erc20")
    b = mem._embed_simple("football premier league soccer transfer tactic")
    sim = mem._cosine(a, b)
    assert sim < 0.5


def test_memory_store_and_recall():
    mem = ExperienceMemory()
    mem.store(
        "Write a blog post about Uniswap v4 hooks and solidity smart contracts",
        [
            "Use before/after hook lifecycle for liquidity",
            "Avoid reentrancy in custom hooks",
            "Check fee-on-transfer interactions",
        ],
    )
    mem.store(
        "Premier League tactic analysis: high pressing formation 4-3-3",
        ["High press wins ball in final third", "Full-backs overlap wide"],
    )
    recalled = mem.recall(
        "Draft a blog post on Ethereum DeFi: Uniswap v4 solidity hook patterns",
        top_k=5,
        min_similarity=0.0,
    )
    assert len(recalled) > 0
    hook_related = any("hook" in r.lower() or "liquidity" in r.lower() for r in recalled)
    assert hook_related


def test_memory_recall_threshold():
    mem = ExperienceMemory()
    mem.store(
        "Unrelated: gardening tips for tomato plants",
        ["Water daily", "Full sun"],
    )
    recalled = mem.recall(
        "Ethereum solidity smart contract audit",
        top_k=5,
        min_similarity=0.8,
    )
    assert len(recalled) == 0


def test_store_add_and_list():
    settings = get_settings()
    store = CrystallizedKnowledgeStore(settings)
    task_id = uuid4()
    c1 = KnowledgeCrystals(
        entities=["Ethereum", "Solidity", "Uniswap"],
        strategies=["Use Check-Effects-Interactions pattern"],
        pitfalls=["Avoid reentrancy", "Beware of low-level calls"],
        frameworks=["ERC20", "ERC721"],
        source_task_id=task_id,
    )
    c2 = KnowledgeCrystals(
        entities=["React", "Next.js", "TypeScript"],
        strategies=["SSR for SEO pages"],
        pitfalls=["Avoid client-side waterfalls"],
        frameworks=["Tailwind", "Redux"],
        source_task_id=uuid4(),
    )
    import asyncio

    async def _run():
        id1 = await store.add(c1)
        id2 = await store.add(c2)
        assert id1 == str(c1.id)
        assert id2 == str(c2.id)
        all_items = await store.list(limit=50)
        assert len(all_items) == 2
        web3_items = await store.list(category="ethereum", limit=50)
        assert len(web3_items) >= 1
        web3_entities = [e.lower() for c in web3_items for e in c.entities]
        assert "ethereum" in web3_entities

    asyncio.run(_run())


def test_store_query_cosine_sorted():
    settings = get_settings()
    store = CrystallizedKnowledgeStore(settings)
    c_web3 = KnowledgeCrystals(
        entities=["Ethereum", "Solidity", "Uniswap", "DeFi", "ERC20"],
        strategies=["DeFi composability strategy"],
        pitfalls=["Reentrancy pitfalls"],
        frameworks=["ERC20 framework"],
        source_task_id=uuid4(),
    )
    c_football = KnowledgeCrystals(
        entities=["Football", "Premier League", "Tactic", "Formation", "Pressing"],
        strategies=["High press tactic strategy"],
        pitfalls=["Avoid leaving gaps at the back"],
        frameworks=["4-3-3 framework"],
        source_task_id=uuid4(),
    )
    import asyncio

    async def _run():
        await store.add(c_web3)
        await store.add(c_football)
        results = await store.query("ethereum solidity defi uniswap smart contract", top_k=10)
        assert len(results) == 2
        top_crystal, top_sim = results[0]
        bottom_crystal, bottom_sim = results[1]
        assert top_sim >= bottom_sim
        top_ents = [e.lower() for e in top_crystal.entities]
        assert "ethereum" in top_ents

        fb_results = await store.query("football premier league tactic pressing formation", top_k=10)
        assert fb_results[0][0].id == c_football.id

    asyncio.run(_run())


def test_store_sync_to_notion_stub():
    settings = get_settings()
    store = CrystallizedKnowledgeStore(settings)
    import asyncio

    async def _run():
        c = KnowledgeCrystals(
            entities=["A"],
            source_task_id=uuid4(),
        )
        await store.add(c)
        result = await store.sync_to_notion()
        assert isinstance(result, int)
        assert result == 0

    asyncio.run(_run())


def test_extractor_heuristics_entities():
    extractor = KnowledgeExtractor(llm=None)
    text = (
        "We deployed the Uniswap V4 Pool Manager using Solidity. "
        "Our HookMiner class integrates with the Ethereum EVM via Web3.js. "
        "Follow the ERC20 standard and use the HTTPS JSON-RPC endpoint."
    )
    import asyncio

    async def _run():
        crystals = await extractor.extract(text, str(uuid4()))
        assert len(crystals.entities) > 0
        low_ents = [e.lower() for e in crystals.entities]
        found = any("uniswap" in e.lower() for e in crystals.entities)
        return crystals

    crystals = asyncio.run(_run())
    assert len(crystals.entities) >= 1


def test_extractor_heuristics_pitfalls_and_strategies():
    extractor = KnowledgeExtractor(llm=None)
    text = (
        "The strategy we use is to always call the Checks-Effects-Interactions pattern. "
        "It is a best practice to validate inputs first. "
        "A common pitfall is forgetting reentrancy guards. "
        "Watch out for low-level call return values that are not checked. "
        "Avoid writing to storage inside loops to save gas."
    )
    import asyncio

    crystals = asyncio.run(extractor.extract(text, str(uuid4())))
    assert len(crystals.strategies) >= 1
    assert len(crystals.pitfalls) >= 1


def test_extractor_frameworks_heuristic():
    extractor = KnowledgeExtractor(llm=None)
    text = (
        "Our PipelineOrchestrator coordinates the data pipeline. "
        "The TransactionBuilder constructs calldata; the Executor runs it. "
        "Use the Router to forward requests to the Manager service."
    )
    import asyncio

    crystals = asyncio.run(extractor.extract(text, str(uuid4())))
    assert len(crystals.frameworks) >= 1
