# LLM Fallback Chain · Provider Circuit Breakers

## Chain Order

Primary → Fallback 1 → Fallback 2 (both NVIDIA NIM + Groq, NO Google AI/Gemini):

```
NVIDIA NIM (DeepSeek-V4-Flash)
        │  5xx / 429 / timeout / cb.open
        ▼
  Groq LPU (Llama 3.3 70B Versatile)
        │  5xx / 429 / timeout / cb.open
        ▼
NVIDIA NIM (Nemotron-70B / Mistral-Nemo 12B — same provider, different model)
        │  all failed
        ▼
  LLMProviderError (bubble up to caller)
```

**Google AI / Gemini Removal Note** (2026-08-18):
Removed `google_gemini` provider entirely because billing/quota setup was not ready. The 2-provider chain still has deep redundancy inside each provider via the `AGENT_MODEL_MAP`:
- NVIDIA route → `deepseek-v4-flash` → `llama-3.1-nemotron-70b-instruct` → `mistral-nemo-12b-instruct`
- Groq route → `llama-3.3-70b-versatile` → `mixtral-8x7b-32768`

**How to re-add Gemini later**:
1. Uncomment/export `GOOGLE_API_KEY` in `.env`.
2. Add `google_gemini` key back to `settings.llm_fallback_order` / `LLM_FALLBACK_ORDER` env.
3. Add model entries to `MODEL_PROFILES` + `model_profiles` Settings dict in `config.py`.
4. Wire `GoogleGeminiProvider` import + `_providers["google_gemini"]` in `router.py`.

Model-per-agent preference (`AGENT_MODEL_MAP` in `backend/src/llm/models.py`) is tried first, but if the preferred model's provider is down, the router walks the fallback order across providers.

## Fallback Conditions

A call is considered **failed** (triggers a retry, then next provider) when any of:

| Condition                        | Where caught                               |
|----------------------------------|--------------------------------------------|
| HTTP `5xx` response              | Provider `generate()` → `LLMProviderError` |
| HTTP `429` Too Many Requests     | Provider `generate()` → `LLMProviderError` |
| Connection / network timeout     | Provider → `LLMProviderError`              |
| Provider circuit-breaker is OPEN | LLMRouter skips the provider immediately   |
| Empty / null `content` in reply  | Provider `generate()` → `LLMProviderError` |

## Per-Provider pybreaker Settings

Every provider has its own `pybreaker.CircuitBreaker`:

```python
# Defaults applied to each provider (nvidia_nim / groq)
pybreaker.CircuitBreaker(
    fail_max=5,          # open after 5 consecutive failures
    reset_timeout=30,    # half-open after 30 seconds (try one probe request)
    state_storage=pybreaker.CircuitMemoryStorage(),
)
```

States:
- **CLOSED** (normal): all traffic through.
- **OPEN** (after 5 failures): traffic immediately errors for 30s → router skips to next provider.
- **HALF_OPEN** (30s elapsed): 1 probe call allowed. On success → CLOSED. On failure → OPEN (another 30s).

## Per-Call tenacity Retry

Inside a single provider's `generate()`, before the breaker counts a failure, we try a few times with exponential jittered backoff:

```python
@retry(
    stop=stop_after_attempt(3),
    wait=wait_exponential_jitter(multiplier=1, min=0.25, max=4.0),
    retry=retry_if_exception_type(LLMProviderError),
)
async def generate(self, prompt: str, model: str, **kwargs) -> str:
    ...
```

So a single "provider attempt" from the router's point of view actually means up to **3 HTTP calls**, with waits ~0.25s → ~0.5s → ~1s (with jitter). Only if *all 3* fail does the breaker count a failure + router fall back.

## Worked Example: NVIDIA 429 Storm

1. 10 concurrent tasks arrive; all prefer NVIDIA.
2. Task 1 → NVIDIA → HTTP 429 → 3 retries (all 429) → raises `LLMProviderError`. Breaker: **failures=1**. Router fallbacks to Groq → success.
3. Task 2 → NVIDIA → 429 → retries fail. Breaker: **failures=2**. To Groq.
4. Tasks 3, 4, 5 → same pattern. Breaker reaches **failures=5 → STATE: OPEN**.
5. Tasks 6–10 arrive → LLMRouter sees NVIDIA breaker is OPEN → **skips NVIDIA immediately**, all traffic → Groq.
6. 30 seconds later → breaker **HALF_OPEN**. Next NVIDIA call is a probe.
   - If probe succeeds → breaker **CLOSED**, traffic resumes.
   - If probe still 429 → back to **OPEN** for another 30s.

## Unit Test Expectation

Test file pattern: `backend/tests/unit/llm/test_fallback_chain.py`

```python
import pytest
from unittest.mock import AsyncMock, patch

from src.llm.router import LLMRouter
from src.core.types import AgentRole


@pytest.mark.asyncio
async def test_fallback_nvidia_to_groq_on_429():
    router = LLMRouter()

    with patch.object(router._providers["nvidia_nim"], "generate",
                      new_callable=AsyncMock,
                      side_effect=LLMProviderError("429 Rate Limited")), \
         patch.object(router._providers["groq"], "generate",
                      new_callable=AsyncMock,
                      return_value="groq response") as groq_mock:
        result = await router.generate("say hi", AgentRole.ORCHESTRATOR)

    groq_mock.assert_awaited_once()
    assert result["provider"] == "groq"
    assert result["response"] == "groq response"


@pytest.mark.asyncio
async def test_breaker_opens_after_5_failures_then_traffic_routes_groq():
    import pybreaker
    router = LLMRouter()
    nvidia = router._providers["nvidia_nim"]
    # Force breaker into OPEN state (simulating 5 prior failures)
    nvidia._breaker.open()

    with patch.object(router._providers["nvidia_nim"], "generate",
                      new_callable=AsyncMock) as nv_mock, \
         patch.object(router._providers["groq"], "generate",
                      new_callable=AsyncMock,
                      return_value="fallback-ok") as gq_mock:

        await router.generate("hello", AgentRole.CONTENT_WEB2)

    nv_mock.assert_not_awaited()   # breaker open → skipped
    gq_mock.assert_awaited_once()  # groq took the call


@pytest.mark.asyncio
async def test_all_providers_fail_raises():
    router = LLMRouter()
    for p in router._providers.values():
        with patch.object(p, "generate", new_callable=AsyncMock,
                          side_effect=LLMProviderError("dead")):
            pass
    # Patch all two with side_effect
    with patch.multiple(router._providers,
                        nvidia_nim=AsyncMock(generate=AsyncMock(
                            side_effect=LLMProviderError("nvidia dead"))),
                        groq=AsyncMock(generate=AsyncMock(
                            side_effect=LLMProviderError("groq dead")))):
        with pytest.raises(LLMProviderError) as excinfo:
            await router.generate("hello", AgentRole.ORCHESTRATOR)

    assert "All LLM providers failed" in str(excinfo.value)
```

Expected `pytest` output: `3 passed`.
