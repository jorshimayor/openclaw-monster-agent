from __future__ import annotations

import os
from pathlib import Path
from typing import Any, List, Dict, Optional
from functools import lru_cache

from pydantic import AnyHttpUrl, Field, AliasChoices, field_validator
from pydantic_settings import BaseSettings, SettingsConfigDict


def _env_file_paths() -> list[Path]:
    """Resolve .env paths in priority order.

    Priority (later overrides earlier):
      1. ``<backend_package>/../../.env`` — the ``backend/`` folder that contains
         this project's actual ``.env`` (the one the user edits). Resolved from
         this file's location so it works regardless of the process CWD.
      2. ``<cwd>/.env`` — process-local overrides (e.g. for tests).
    """
    here = Path(__file__).resolve().parent  # .../backend/src/core
    project_dot_env = here.parent.parent / ".env"  # .../backend/.env
    paths: list[Path] = [project_dot_env]
    cwd_env = Path.cwd() / ".env"
    try:
        if cwd_env.resolve() != project_dot_env.resolve():
            paths.append(cwd_env)
    except OSError:
        paths.append(cwd_env)
    return paths


class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        env_file=tuple(_env_file_paths()),
        env_file_encoding="utf-8",
        case_sensitive=False,
        extra="ignore",
    )

    nvidia_nim_api_key: str = Field(default="", validation_alias=AliasChoices("nvidia_nim_api_key", "NVIDIA_NIM_API_KEY"))
    nvidia_nim_base_url: str = Field(
        default="https://integrate.api.nvidia.com/v1",
        validation_alias=AliasChoices("nvidia_nim_base_url", "NVIDIA_NIM_BASE_URL"),
    )

    groq_api_key: str = Field(default="", validation_alias=AliasChoices("groq_api_key", "GROQ_API_KEY"))

    github_token: str = Field(default="", validation_alias=AliasChoices("github_token", "GITHUB_TOKEN"))

    notion_token: str = Field(default="", validation_alias=AliasChoices("notion_token", "NOTION_TOKEN"))
    notion_db_id: str = Field(default="", validation_alias=AliasChoices("notion_db_id", "NOTION_DB_ID"))

    slack_bot_token: str = Field(
        default="",
        validation_alias=AliasChoices("slack_bot_token", "SLACK_BOT_TOKEN", "SLACK_TOKEN"),
    )
    slack_user_token: str = Field(
        default="",
        validation_alias=AliasChoices("slack_user_token", "SLACK_USER_TOKEN"),
    )
    slack_channel: str = Field(
        default="#agent-updates",
        validation_alias=AliasChoices("slack_channel", "SLACK_CHANNEL"),
    )

    google_workspace_client_id: str = Field(
        default="",
        validation_alias=AliasChoices("google_workspace_client_id", "GOOGLE_WORKSPACE_CLIENT_ID"),
    )
    google_workspace_client_secret: str = Field(
        default="",
        validation_alias=AliasChoices("google_workspace_client_secret", "GOOGLE_WORKSPACE_CLIENT_SECRET"),
    )
    google_workspace_refresh_token: str = Field(
        default="",
        validation_alias=AliasChoices("google_workspace_refresh_token", "GOOGLE_WORKSPACE_REFRESH_TOKEN"),
    )
    google_workspace_subject_email: str = Field(
        default="",
        validation_alias=AliasChoices("google_workspace_subject_email", "GOOGLE_WORKSPACE_SUBJECT_EMAIL"),
    )

    database_url: str = Field(
        default="",
        validation_alias=AliasChoices("database_url", "DATABASE_URL"),
    )

    # ⚠️  RETIRED 2026-08-23: Hashnode now requires Pro for API access (content API discontinued on free tier).
    # Fields kept here for back-compat only; hashnode is REMOVED from McpServerManager.SUPPORTED_SERVERS
    # and will never be launched at runtime. To re-enable later: re-add "hashnode" to SUPPORTED_SERVERS +
    # restore hashnode spec entry in _build_server_specs() + re-run hashnode secret put commands.
    hashnode_token: str = Field(default="", validation_alias=AliasChoices("hashnode_token", "HASHNODE_TOKEN"))
    hashnode_publication_id: str = Field(
        default="",
        validation_alias=AliasChoices("hashnode_publication_id", "HASHNODE_PUBLICATION_ID"),
    )

    telegram_bot_token: str = Field(
        default="",
        validation_alias=AliasChoices("telegram_bot_token", "TELEGRAM_BOT_TOKEN"),
    )
    telegram_chat_id: str = Field(
        default="",
        validation_alias=AliasChoices("telegram_chat_id", "TELEGRAM_CHAT_ID"),
    )
    telegram_admin_ids: List[str] = Field(
        default_factory=list,
        validation_alias=AliasChoices("telegram_admin_ids", "TELEGRAM_ADMIN_IDS"),
    )

    @field_validator("telegram_chat_id", mode="before")
    @classmethod
    def _coerce_chat_id(cls, v: Any) -> str:
        # Cloudflare Container env vars / .env often paste numeric chat ids
        # like -100123456789 for groups or 399640868 for private DMs. Always
        # stringify (Telegram API accepts numeric strings for chat_id).
        if v is None:
            return ""
        if isinstance(v, (int, float)):
            # Use int() to strip float zeroes; preserve sign for group "-100…"
            return str(int(v))
        s = str(v).strip()
        if s.lower() in {"", "none", "null"}:
            return ""
        return s

    @field_validator("telegram_admin_ids", mode="before")
    @classmethod
    def _coerce_admin_ids(cls, v: Any) -> list:
        # Accept: 399640868 (raw int) | "399640868" (single string) |
        #         "399640868,123456789" (comma-sep) | ["399640868", 123] (mixed list)
        if v is None:
            return []
        if isinstance(v, (int, float)):
            return [str(int(v))]
        if isinstance(v, str):
            s = v.strip()
            if not s:
                return []
            parts = [p.strip() for p in s.split(",")]
            cleaned = []
            for p in parts:
                if not p:
                    continue
                # Accept numeric int-only strings as telegram ids (all digits, optionally leading '-' for groups)
                try:
                    cleaned.append(str(int(p)))
                except (TypeError, ValueError):
                    cleaned.append(p)
            return cleaned
        if isinstance(v, (list, tuple, set)):
            cleaned = []
            for item in v:
                if item is None:
                    continue
                if isinstance(item, (int, float)):
                    cleaned.append(str(int(item)))
                else:
                    s = str(item).strip()
                    if s:
                        cleaned.append(s)
            return cleaned
        # Fallback: stringify whatever weird value was passed
        return [str(v)]

    backend_cors_origins: List[AnyHttpUrl] = Field(
        default_factory=lambda: [
            AnyHttpUrl("http://localhost:3000"),
            AnyHttpUrl("http://localhost:8080"),
        ]
    )

    log_level: str = Field(default="INFO", validation_alias=AliasChoices("log_level", "LOG_LEVEL"))

    @field_validator("log_level")
    @classmethod
    def _normalize_log_level(cls, v: str) -> str:
        return (v or "INFO").upper()

    model_profiles: Dict[str, Dict[str, Any]] = Field(
        default_factory=lambda: {
            "nvidia/llama-3.1-70b-instruct": {
                "name": "meta/llama-3.1-70b-instruct",
                "provider": "nvidia_nim",
                "context_window": 131_072,
                "cost_per_1k_input": 0.0003,
                "cost_per_1k_output": 0.0008,
            },
            "nvidia/mistral-nemo-12b-instruct": {
                "name": "mistralai/mistral-nemo-12b-instruct",
                "provider": "nvidia_nim",
                "context_window": 128_000,
                "cost_per_1k_input": 0.00015,
                "cost_per_1k_output": 0.00015,
            },
            "nvidia/nemotron-super-49b": {
                "name": "nvidia/llama-3.3-nemotron-super-49b-v1.5",
                "provider": "nvidia_nim",
                "context_window": 131_072,
                "cost_per_1k_input": 0.0003,
                "cost_per_1k_output": 0.0008,
            },
            "groq/llama-3.1-8b-instant": {
                "name": "llama-3.1-8b-instant",
                "provider": "groq",
                "context_window": 131_072,
                "cost_per_1k_input": 0.0,
                "cost_per_1k_output": 0.0,
            },
            "groq/llama-3.3-70b-versatile": {
                "name": "llama-3.3-70b-versatile",
                "provider": "groq",
                "context_window": 131_072,
                "cost_per_1k_input": 0.00059,
                "cost_per_1k_output": 0.00079,
            },
            "groq/gpt-oss-120b": {
                "name": "openai/gpt-oss-120b",
                "provider": "groq",
                "context_window": 131_072,
                "cost_per_1k_input": 0.00015,
                "cost_per_1k_output": 0.00060,
            },
            "groq/gpt-oss-20b": {
                "name": "openai/gpt-oss-20b",
                "provider": "groq",
                "context_window": 131_072,
                "cost_per_1k_input": 0.000075,
                "cost_per_1k_output": 0.00030,
            },
        }
    )

    agent_roles: List[str] = Field(
        default_factory=lambda: [
            "PERSONAL_ASSISTANT",
            "ORCHESTRATOR",
            "CONTENT_WEB2",
            "CONTENT_WEB3",
            "FOOTBALL",
            "EDITOR",
            "SECURITY",
            "KNOWLEDGE",
            "STUDY",
        ]
    )

    llm_fallback_order: List[str] = Field(
        default_factory=lambda: ["nvidia_nim", "groq"]
    )

    @property
    def env_file_diagnostics(self) -> Dict[str, Any]:
        """Summary for debugging: which env files were considered + which tokens are set."""
        files = [str(p) + ("*" if p.exists() else " (missing)") for p in _env_file_paths()]
        def flag(v: str) -> str:
            if not v:
                return "<unset>"
            if len(v) <= 8:
                return "set"
            return f"set ({v[:4]}...{v[-4:]}, len={len(v)})"
        return {
            "env_files_considered": files,
            "keys": {
                "NVIDIA_NIM_API_KEY": flag(self.nvidia_nim_api_key),
                "GROQ_API_KEY": flag(self.groq_api_key),
                "GITHUB_TOKEN": flag(self.github_token),
                "NOTION_TOKEN": flag(self.notion_token),
                "SLACK_BOT_TOKEN": flag(self.slack_bot_token),
                "SLACK_USER_TOKEN": flag(self.slack_user_token),
                "GOOGLE_WORKSPACE_CLIENT_ID": flag(self.google_workspace_client_id),
                "GOOGLE_WORKSPACE_REFRESH_TOKEN": flag(self.google_workspace_refresh_token),
                "TELEGRAM_BOT_TOKEN": flag(self.telegram_bot_token),
                "TELEGRAM_CHAT_ID": flag(self.telegram_chat_id),
                "DATABASE_URL": flag(self.database_url),
            },
            "cwd": str(Path.cwd()),
        }


@lru_cache
def get_settings() -> Settings:
    return Settings()
