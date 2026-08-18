from __future__ import annotations

from typing import Any, Dict, List, Optional, Tuple

from ..core.config import get_settings
from ..core.logging import get_logger
from ..core.types import AgentRole
from .models import AGENT_MODEL_MAP, MODEL_PROFILES, ModelProfile
from .providers.nvidia_nim import NvidiaNIMProvider, LLMProviderError
from .providers.groq import GroqProvider

logger = get_logger(__name__)


class LLMRouter:
    def __init__(self) -> None:
        self.settings = get_settings()
        self._providers: Dict[str, Any] = {
            "nvidia_nim": NvidiaNIMProvider(),
            "groq": GroqProvider(),
        }
        self._fallback_order: List[str] = [
            p for p in self.settings.llm_fallback_order if p in self._providers
        ]

    def _models_for_role(self, agent_role: AgentRole) -> List[str]:
        models = AGENT_MODEL_MAP.get(agent_role)
        if not models:
            return list(MODEL_PROFILES.keys())
        return list(models)

    def _resolve_model(self, model_key: str) -> Tuple[ModelProfile, Any]:
        profile = MODEL_PROFILES.get(model_key)
        if profile is None:
            raise LLMProviderError(f"Unknown model key: {model_key}")
        provider = self._providers.get(profile.provider)
        if provider is None:
            raise LLMProviderError(
                f"Provider '{profile.provider}' not available for model '{model_key}'"
            )
        return profile, provider

    async def generate(
        self,
        prompt: str,
        agent_role: AgentRole,
        model_override: Optional[str] = None,
        **kwargs: Any,
    ) -> Dict[str, Any]:
        if not prompt:
            raise ValueError("LLMRouter.generate: prompt cannot be empty")

        raw_models: List[str] = (
            [model_override] if model_override else self._models_for_role(agent_role)
        )

        resolved: List[Tuple[str, str, ModelProfile, Any]] = []
        resolve_errors: List[str] = []
        seen: set[tuple[str, str]] = set()
        for provider_name in self._fallback_order:
            provider = self._providers.get(provider_name)
            if provider is None:
                resolve_errors.append(f"[fallback/{provider_name}] not in providers map")
                continue
            for model_key in raw_models:
                try:
                    profile = MODEL_PROFILES.get(model_key)
                except Exception as e:  # pragma: no cover - defensive
                    resolve_errors.append(f"[{model_key}] profile lookup: {e}")
                    continue
                if profile is None:
                    resolve_errors.append(f"[{model_key}] unknown model key")
                    continue
                if profile.provider != provider_name:
                    continue
                key = (provider_name, model_key)
                if key in seen:
                    continue
                seen.add(key)
                resolved.append((provider_name, model_key, profile, provider))

        if not resolved:
            msg = (
                f"No viable (provider, model) pairs. Fallback providers={self._fallback_order}, "
                f"candidates={raw_models}. "
                f"Resolve errors: {' | '.join(resolve_errors) if resolve_errors else 'none'}"
            )
            logger.error("llm_no_viable_pairs", fallback=self._fallback_order, models=raw_models)
            raise LLMProviderError(msg)

        last_error: Optional[Exception] = None
        errors: List[str] = []
        attempts_tried: List[str] = []

        for provider_name, model_key, profile, provider in resolved:
            attempts_tried.append(f"{provider_name}:{model_key}")
            try:
                logger.info(
                    "llm_generate_start",
                    provider=provider_name,
                    model=profile.name,
                    role=agent_role,
                    prompt_chars=len(prompt),
                )
                output = await provider.generate(prompt, profile.name, **kwargs)
                logger.info(
                    "llm_generate_success",
                    provider=provider_name,
                    model=profile.name,
                    output_chars=len(output),
                )
                return {
                    "provider": provider_name,
                    "model": model_key,
                    "model_name": profile.name,
                    "response": output,
                }
            except LLMProviderError as e:
                errors.append(f"[{provider_name}/{model_key}] {e}")
                last_error = e
                logger.warning(
                    "llm_provider_switch",
                    from_provider=provider_name,
                    model=profile.name,
                    reason=str(e)[:200],
                )
                continue

        error_msg = (
            f"All LLM providers failed. Tried: {', '.join(attempts_tried)}. "
            f"Errors: {' | '.join(errors + resolve_errors) if errors + resolve_errors else 'none'}"
        )
        logger.error("llm_all_providers_failed", errors=errors, resolve_errors=resolve_errors)
        raise LLMProviderError(error_msg) from last_error
