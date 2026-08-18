from __future__ import annotations

from typing import Any, Dict

from .nvidia_nim import BaseLLMProvider, LLMProviderError


class GroqProvider(BaseLLMProvider):
    provider_name: str = "groq"
    _BASE_URL = "https://api.groq.com/openai/v1/chat/completions"

    async def generate(self, prompt: str, model: str, **kwargs: Any) -> str:
        if not self.settings.groq_api_key:
            raise LLMProviderError("groq: GROQ_API_KEY not configured")

        headers = self._headers(self.settings.groq_api_key)
        payload = {
            "model": model,
            "messages": [{"role": "user", "content": prompt}],
            "temperature": kwargs.get("temperature", 0.7),
            "max_tokens": kwargs.get("max_tokens", 4096),
            "top_p": kwargs.get("top_p", 0.95),
            "stream": False,
        }

        def extract(data: Dict[str, Any]) -> str:
            choices = data.get("choices") or []
            if not choices:
                raise LLMProviderError("groq: empty choices in response")
            message = choices[0].get("message", {})
            content = message.get("content", "")
            if content is None:
                return ""
            return str(content)

        return await self._post_with_retry(self._BASE_URL, headers, payload, extract)
