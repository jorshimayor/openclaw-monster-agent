from __future__ import annotations

import httpx
import pytest
import respx

from src.core.types import AgentRole
from src.llm.router import LLMRouter
from src.llm.providers.nvidia_nim import LLMProviderError


NVIDIA_URL = "https://integrate.api.nvidia.com/v1/chat/completions"
GROQ_URL = "https://api.groq.com/openai/v1/chat/completions"
GEMINI_URL = "https://generativelanguage.googleapis.com/v1/models/gemini-2.0-flash-lite:generateContent"


@pytest.mark.asyncio
async def test_generate_success_nvidia():
    with respx.mock as mock_http:
        mock_http.post(NVIDIA_URL).mock(
            return_value=httpx.Response(
                200,
                json={
                    "choices": [
                        {"message": {"role": "assistant", "content": "nvidia-llm-response"}}
                    ]
                },
            )
        )

        router = LLMRouter()
        router._fallback_order = ["nvidia_nim", "groq", "google_gemini"]

        result = await router.generate("Hello world", AgentRole.ORCHESTRATOR)

        assert result["provider"] == "nvidia_nim"
        assert "model" in result
        assert result["response"] == "nvidia-llm-response"
        assert mock_http.post(NVIDIA_URL).called
        assert mock_http.post(GROQ_URL).call_count == 0
        assert mock_http.post(GEMINI_URL).call_count == 0


@pytest.mark.asyncio
async def test_fallback_on_nvidia_failure_to_groq():
    with respx.mock as mock_http:
        mock_http.post(NVIDIA_URL).mock(
            return_value=httpx.Response(500, json={"error": "Internal Server Error"})
        )
        mock_http.post(GROQ_URL).mock(
            return_value=httpx.Response(
                200,
                json={
                    "choices": [
                        {"message": {"role": "assistant", "content": "groq-response"}}
                    ]
                },
            )
        )

        router = LLMRouter()
        router._fallback_order = ["nvidia_nim", "groq", "google_gemini"]

        for provider in router._providers.values():
            provider.max_retries = 1

        result = await router.generate("Please fallback test", AgentRole.EDITOR)

        assert result["provider"] == "groq"
        assert result["response"] == "groq-response"
        assert mock_http.post(NVIDIA_URL).call_count >= 1
        assert mock_http.post(GROQ_URL).call_count >= 1


@pytest.mark.asyncio
async def test_all_providers_fail_raises():
    with respx.mock as mock_http:
        mock_http.post(NVIDIA_URL).mock(return_value=httpx.Response(500, json={}))
        mock_http.post(GROQ_URL).mock(return_value=httpx.Response(503, json={}))
        mock_http.post(GEMINI_URL).mock(return_value=httpx.Response(500, json={}))

        router = LLMRouter()
        router._fallback_order = ["nvidia_nim", "groq", "google_gemini"]

        for provider in router._providers.values():
            provider.max_retries = 1

        with pytest.raises(LLMProviderError) as exc:
            await router.generate("Will fail", AgentRole.SECURITY)

        message = str(exc.value)
        assert "All LLM providers failed" in message or "exhausted" in message.lower()
        assert mock_http.post(NVIDIA_URL).call_count >= 1
