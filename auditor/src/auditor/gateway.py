"""The provider-agnostic model layer.

Agent code calls `gateway.complete(stage=...)` and never names a provider. The
stage is looked up in model-policy.yaml, which supplies a primary model and an
ordered list of fallbacks. Swapping a provider is a config edit.

The fallback chain triggers on three things, not one:

  1. transport failure or a non-2xx from the gateway,
  2. a refusal or empty completion,
  3. **output that does not validate against the expected schema.**

The third is the one that matters. JSON-mode fidelity varies by provider, so a
model that returns confident malformed JSON is treated exactly like a model
that returned a 500 — the next one gets the call. Nothing downstream ever sees
free-form prose where a structure was expected.
"""

from __future__ import annotations

import json
import os
import re
from dataclasses import dataclass
from pathlib import Path
from typing import Any, TypeVar

import httpx
import yaml
from pydantic import BaseModel, ValidationError

from .budget import Budget

ROOT = Path(__file__).resolve().parents[2]
POLICY_FILE = ROOT / "config" / "model-policy.yaml"

T = TypeVar("T", bound=BaseModel)

_ENV_DEFAULT = re.compile(r"\$\{(\w+)(?::-(.*?))?\}")


def _expand(value: Any) -> Any:
    """${VAR} and ${VAR:-default} in the policy file."""
    if not isinstance(value, str):
        return value
    return _ENV_DEFAULT.sub(lambda m: os.environ.get(m.group(1), m.group(2) or ""), value)


class ModelsUnavailable(RuntimeError):
    """Every model for a stage failed. Never silently degrades to a guess."""


@dataclass
class StagePolicy:
    name: str
    primary: str
    fallbacks: list[str]
    temperature: float = 0.2

    @property
    def chain(self) -> list[str]:
        return [self.primary, *self.fallbacks]


class Gateway:
    def __init__(self, policy_file: Path | None = None, budget: Budget | None = None):
        raw = yaml.safe_load((policy_file or POLICY_FILE).read_text())
        gw = raw["gateway"]
        self.base_url = str(_expand(gw["base_url"])).rstrip("/")
        self.api_key = os.environ.get(gw.get("api_key_env", "AUDITOR_GATEWAY_KEY"), "")
        self.timeout = float(gw.get("timeout_seconds", 180))
        self.stages = {
            name: StagePolicy(
                name=name,
                primary=cfg["primary"],
                fallbacks=list(cfg.get("fallbacks") or []),
                temperature=float(cfg.get("temperature", 0.2)),
            )
            for name, cfg in raw["stages"].items()
        }
        self.panel: list[str] = list(raw.get("verifier_panel") or [])
        self.budget = budget or Budget()
        self.attempts: list[tuple[str, str, str]] = []  # (stage, model, outcome)

    # -- transport --------------------------------------------------------

    def _post(self, model: str, messages: list[dict], temperature: float, json_mode: bool) -> str:
        body: dict[str, Any] = {
            "model": model,
            "messages": messages,
            "temperature": temperature,
        }
        if json_mode:
            body["response_format"] = {"type": "json_object"}
        headers = {"Content-Type": "application/json"}
        if self.api_key:
            headers["Authorization"] = f"Bearer {self.api_key}"
        with httpx.Client(timeout=self.timeout) as client:
            response = client.post(
                f"{self.base_url}/chat/completions", json=body, headers=headers
            )
            response.raise_for_status()
            payload = response.json()
        choices = payload.get("choices") or []
        if not choices:
            raise ValueError("gateway returned no choices")
        content = (choices[0].get("message") or {}).get("content") or ""
        if not content.strip():
            raise ValueError("gateway returned an empty completion")
        return content

    # -- public API -------------------------------------------------------

    def complete(
        self,
        stage: str,
        messages: list[dict],
        *,
        schema: type[T] | None = None,
        temperature: float | None = None,
    ) -> T | str:
        """Run a stage. With `schema`, the result is a validated model instance.

        Tries every model in the chain. Raises ModelsUnavailable if all fail —
        a stage never returns a half-parsed guess.
        """
        policy = self.stages.get(stage)
        if policy is None:
            raise KeyError(f"no policy for stage {stage!r}; have {sorted(self.stages)}")

        problems: list[str] = []
        for model in policy.chain:
            self.budget.spend(f"{stage}:{model}")
            try:
                content = self._post(
                    model,
                    messages,
                    policy.temperature if temperature is None else temperature,
                    json_mode=schema is not None,
                )
            except Exception as exc:  # transport, HTTP, empty
                problems.append(f"{model}: {type(exc).__name__}: {exc}")
                self.attempts.append((stage, model, "transport"))
                continue

            if schema is None:
                self.attempts.append((stage, model, "ok"))
                return content

            try:
                parsed = schema.model_validate(_loads(content))
            except (ValidationError, ValueError) as exc:
                # The important case: a confident, malformed answer is a failure.
                problems.append(f"{model}: schema {type(exc).__name__}")
                self.attempts.append((stage, model, "schema"))
                continue

            self.attempts.append((stage, model, "ok"))
            return parsed

        raise ModelsUnavailable(
            f"every model for stage {stage!r} failed:\n  " + "\n  ".join(problems)
        )


def _loads(content: str) -> Any:
    """Tolerate a fenced block, but nothing looser than that."""
    text = content.strip()
    if text.startswith("```"):
        text = re.sub(r"^```(?:json)?\s*", "", text)
        text = re.sub(r"\s*```$", "", text)
    return json.loads(text)
