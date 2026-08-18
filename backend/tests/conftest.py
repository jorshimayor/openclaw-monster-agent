from __future__ import annotations

from typing import Any, AsyncGenerator, Dict, Generator
from unittest.mock import AsyncMock, MagicMock
from uuid import uuid4

import pytest

from src.core.types import AgentRole, Task, TaskStatus
from src.llm.router import LLMRouter
from src.llm.providers.nvidia_nim import LLMProviderError


class MockLLMProvider:
    def __init__(self, name: str, fail: bool = False, response: str = "mocked response") -> None:
        self.provider_name = name
        self.fail = fail
        self.response = response
        self.breaker = MagicMock()
        self.breaker.call_async = AsyncMock(side_effect=self._breaker_effect)
        self.settings = MagicMock()
        self.max_retries = 1
        self._post_with_retry = AsyncMock(side_effect=self._generate_effect)

    async def _breaker_effect(self, fn, *args, **kwargs):
        return await fn(*args, **kwargs)

    async def _generate_effect(self, *args, **kwargs):
        if self.fail:
            raise LLMProviderError(f"{self.provider_name}: forced failure")
        return self.response

    async def generate(self, prompt: str, model: str, **kwargs: Any) -> str:
        if self.fail:
            raise LLMProviderError(f"{self.provider_name}: forced failure")
        return self.response


@pytest.fixture
def mock_llm_router(monkeypatch: pytest.MonkeyPatch) -> LLMRouter:
    router = LLMRouter()

    nvidia = MockLLMProvider("nvidia_nim", fail=False, response="nvidia says hi")
    groq = MockLLMProvider("groq", fail=False, response="groq says hi")
    gemini = MockLLMProvider("google_gemini", fail=False, response="gemini says hi")

    router._providers = {
        "nvidia_nim": nvidia,
        "groq": groq,
        "google_gemini": gemini,
    }
    return router


@pytest.fixture
def mock_llm_router_nvidia_fail(monkeypatch: pytest.MonkeyPatch) -> LLMRouter:
    router = LLMRouter()

    nvidia = MockLLMProvider("nvidia_nim", fail=True)
    groq = MockLLMProvider("groq", fail=False, response="groq fallback success")
    gemini = MockLLMProvider("google_gemini", fail=False, response="gemini fallback")

    router._providers = {
        "nvidia_nim": nvidia,
        "groq": groq,
        "google_gemini": gemini,
    }
    return router


@pytest.fixture
def mock_llm_router_all_fail(monkeypatch: pytest.MonkeyPatch) -> LLMRouter:
    router = LLMRouter()

    nvidia = MockLLMProvider("nvidia_nim", fail=True)
    groq = MockLLMProvider("groq", fail=True)
    gemini = MockLLMProvider("google_gemini", fail=True)

    router._providers = {
        "nvidia_nim": nvidia,
        "groq": groq,
        "google_gemini": gemini,
    }
    return router


@pytest.fixture
def sample_task() -> Task:
    return Task(
        id=uuid4(),
        description="Write a beginner-friendly blog post about Uniswap v4 hooks referencing my codebase.",
        status=TaskStatus.PENDING,
        step=None,
        outputs={},
    )
