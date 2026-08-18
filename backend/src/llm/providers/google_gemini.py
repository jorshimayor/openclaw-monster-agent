from __future__ import annotations

from typing import Any, Dict

from .nvidia_nim import BaseLLMProvider, LLMProviderError


class GoogleGeminiProvider(BaseLLMProvider):
    provider_name: str = "google_gemini"
    _BASE_URL = "https://generativelanguage.googleapis.com/v1/models"

    async def generate(self, prompt: str, model: str, **kwargs: Any) -> str:
        api_key = getattr(self.settings, "google_api_key", "")
        if not api_key:
            raise LLMProviderError("google_gemini: GOOGLE_API_KEY not configured (removed — re-enable in config.py / settings + router to use)")

        url = f"{self._BASE_URL}/{model}:generateContent?key={api_key}"
        headers: Dict[str, str] = {
            "Content-Type": "application/json",
            "Accept": "application/json",
        }
        payload = {
            "contents": [
                {
                    "parts": [{"text": prompt}],
                    "role": "user",
                }
            ],
            "generationConfig": {
                "temperature": kwargs.get("temperature", 0.7),
                "maxOutputTokens": kwargs.get("max_tokens", 4096),
                "topP": kwargs.get("top_p", 0.95),
            },
        }

        def extract(data: Dict[str, Any]) -> str:
            candidates = data.get("candidates") or []
            if not candidates:
                raise LLMProviderError(
                    f"google_gemini: no candidates in response. keys={list(data.keys())}"
                )
            content = candidates[0].get("content", {})
            parts = content.get("parts") or []
            if not parts:
                raise LLMProviderError("google_gemini: empty parts in response")
            text_parts = [str(p.get("text", "")) for p in parts if p.get("text")]
            return "\n".join(text_parts)

        return await self._post_with_retry(url, headers, payload, extract)
