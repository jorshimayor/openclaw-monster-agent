from __future__ import annotations

from abc import ABC, abstractmethod
from typing import Any, Dict, Optional

import httpx
from tenacity import (
    AsyncRetrying,
    retry_if_exception_type,
    stop_after_attempt,
    wait_exponential_jitter,
    RetryError,
)
import pybreaker

from ...core.config import get_settings
from ...core.logging import get_logger

logger = get_logger(__name__)


def _build_wait_backoff():
    """Build a tenacity ``wait`` strategy for exponential jitter backoff.

    Tenacity changed the parameter names between versions:
      * Old API (scaffold):  ``wait_exponential_jitter(min=1, max=10, jitter=1)``
      * New API (installed): ``wait_exponential_jitter(wait_min=1, wait_max=10, jitter=1)``
    We probe the signature and fall back to a sensible default ``wait_random_exponential``
    if the installed version accepts neither naming convention.
    """
    import inspect

    sig = inspect.signature(wait_exponential_jitter)
    params = set(sig.parameters.keys())
    if "wait_min" in params and "wait_max" in params:
        return wait_exponential_jitter(wait_min=1, wait_max=10, jitter=1)
    if "min" in params and "max" in params:
        return wait_exponential_jitter(min=1, max=10, jitter=1)
    try:
        from tenacity import wait_random_exponential
        return wait_random_exponential(min=1, max=10)
    except Exception:
        from tenacity import wait_exponential
        return wait_exponential(multiplier=1, min=1, max=10)


class SimpleCircuitBreaker:
    """Tiny stateful circuit breaker (no third-party API deps).

    Behaves like a stripped-down pybreaker: ``closed`` → ``open`` after
    ``fail_max`` consecutive failures, then back to ``half-open`` after
    ``reset_timeout_s``. ``record_success()`` moves open/half-open → closed.
    """

    STATE_CLOSED = "closed"
    STATE_OPEN = "open"
    STATE_HALF_OPEN = "half_open"

    def __init__(self, fail_max: int = 10, reset_timeout_s: float = 15.0) -> None:
        self.fail_max = max(1, int(fail_max))
        self.reset_timeout_s = max(0.0, float(reset_timeout_s))
        self._failures = 0
        self._state = self.STATE_CLOSED
        self._opened_at: float | None = None

    @property
    def current_state(self) -> str:
        return self.state

    @property
    def state(self) -> str:
        self._maybe_transition_to_half_open()
        return self._state

    @property
    def is_open(self) -> bool:
        return self.state == self.STATE_OPEN

    def _maybe_transition_to_half_open(self) -> None:
        if self._state == self.STATE_OPEN and self._opened_at is not None:
            import time as _time

            if _time.monotonic() - self._opened_at >= self.reset_timeout_s:
                self._state = self.STATE_HALF_OPEN
                self._opened_at = None
                self._failures = 0

    def record_success(self) -> None:
        self._failures = 0
        self._state = self.STATE_CLOSED
        self._opened_at = None

    def record_failure(self) -> None:
        self._failures += 1
        if self._failures >= self.fail_max or self._state == self.STATE_HALF_OPEN:
            import time as _time

            self._state = self.STATE_OPEN
            self._opened_at = _time.monotonic()


class LLMProviderError(Exception):
    pass


class LLMProviderTimeout(LLMProviderError):
    pass


class LLMProviderAuth(LLMProviderError):
    pass


class BaseLLMProvider(ABC):
    provider_name: str = "base"
    max_retries: int = 3

    def __init__(self, timeout: float = 60.0) -> None:
        self.settings = get_settings()
        self.timeout = timeout
        self.breaker = SimpleCircuitBreaker(
            fail_max=5,
            reset_timeout_s=30,
        )

    @abstractmethod
    async def generate(self, prompt: str, model: str, **kwargs: Any) -> str:
        ...

    def _headers(self, auth_key: str) -> Dict[str, str]:
        return {
            "Authorization": f"Bearer {auth_key}",
            "Content-Type": "application/json",
            "Accept": "application/json",
        }

    async def _call_with_breaker(self, coro_fn, *args, **kwargs):
        """Run a coroutine under ``self.breaker`` (``SimpleCircuitBreaker``).

        Only penalizes the breaker for INFRASTRUCTURE failures:
          - 5xx server errors, timeouts, network errors, breaker-when-open
        Never penalizes for 4xx client errors (wrong model name / decommissioned /
        wrong API key) because those reflect user/config mistakes, not provider
        reliability — incorrectly opening the breaker on a 400 blocks all other
        perfectly-good models on the SAME provider for 15+ seconds.
        """
        if self.breaker.is_open:
            logger.warning(
                "circuit_breaker_open",
                provider=self.provider_name,
            )
            raise LLMProviderError(f"Circuit breaker open for {self.provider_name}")
        try:
            result = await coro_fn(*args, **kwargs)
        except (LLMProviderTimeout, LLMProviderAuth) as exc:
            # 408/504 timeout counts as infra issue; 401/403 auth also counts
            # (it's per-provider level, not per-model)
            self.breaker.record_failure()
            raise
        except LLMProviderError as exc:
            msg = str(exc) or ""
            # Treat as breaker-penalizing ONLY if it's a 5xx / server-error
            if (": server error (" in msg) or (": exhausted " in msg and " retries" in msg):
                self.breaker.record_failure()
            raise
        except (httpx.HTTPError, httpx.TimeoutException) as exc:
            # httpx-level transport errors (connection refused, DNS, etc.)
            self.breaker.record_failure()
            raise LLMProviderError(f"{self.provider_name}: transport error: {exc}") from exc
        except Exception as exc:
            # Any other unexpected error is treated as infra failure
            self.breaker.record_failure()
            raise
        self.breaker.record_success()
        return result

    async def _post_with_retry(
        self,
        url: str,
        headers: Dict[str, str],
        payload: Dict[str, Any],
        extract_fn,
    ) -> str:
        try:
            wait_fn = _build_wait_backoff()
            async for attempt in AsyncRetrying(
                reraise=True,
                stop=stop_after_attempt(self.max_retries),
                wait=wait_fn,
                retry=retry_if_exception_type(
                    (httpx.HTTPError, LLMProviderError, httpx.TimeoutException)
                ),
            ):
                with attempt:
                    result = await self._call_with_breaker(
                        self._post_once, url, headers, payload, extract_fn
                    )
                    return result
        except RetryError as e:
            raise LLMProviderError(
                f"{self.provider_name}: exhausted {self.max_retries} retries"
            ) from e

    async def _post_once(
        self,
        url: str,
        headers: Dict[str, str],
        payload: Dict[str, Any],
        extract_fn,
    ) -> str:
        async with httpx.AsyncClient(timeout=self.timeout) as client:
            response = await client.post(url, headers=headers, json=payload)
            if response.status_code == 401 or response.status_code == 403:
                raise LLMProviderAuth(
                    f"{self.provider_name}: auth failed ({response.status_code})"
                )
            if response.status_code == 408 or response.status_code == 504:
                raise LLMProviderTimeout(
                    f"{self.provider_name}: timeout ({response.status_code})"
                )
            if response.status_code >= 500:
                raise LLMProviderError(
                    f"{self.provider_name}: server error ({response.status_code})"
                )
            if response.status_code >= 400:
                raise LLMProviderError(
                    f"{self.provider_name}: client error ({response.status_code}): {response.text[:500]}"
                )
            data = response.json()
            return extract_fn(data)


class NvidiaNIMProvider(BaseLLMProvider):
    provider_name: str = "nvidia_nim"

    async def generate(self, prompt: str, model: str, **kwargs: Any) -> str:
        if not self.settings.nvidia_nim_api_key:
            raise LLMProviderError("nvidia_nim: NVIDIA_NIM_API_KEY not configured")

        url = f"{self.settings.nvidia_nim_base_url.rstrip('/')}/chat/completions"
        headers = self._headers(self.settings.nvidia_nim_api_key)
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
                raise LLMProviderError("nvidia_nim: empty choices in response")
            message = choices[0].get("message", {})
            content = message.get("content", "")
            if content is None:
                return ""
            return str(content)

        return await self._post_with_retry(url, headers, payload, extract)
