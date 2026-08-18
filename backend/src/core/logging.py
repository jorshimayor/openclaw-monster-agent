from __future__ import annotations

import logging
import os
import re
from typing import Any, Dict, Iterable, Union

import structlog
from structlog.typing import EventDict, WrappedLogger, Processor

from .config import get_settings


class EventRenamer:
    def __init__(self, new_key: str = "msg") -> None:
        self._new_key = new_key

    def __call__(
        self, logger: WrappedLogger, method_name: str, event_dict: EventDict
    ) -> EventDict:
        if "event" in event_dict:
            event_dict[self._new_key] = event_dict.pop("event")
        return event_dict


class SecretRedactionProcessor:
    _SECRET_PATTERNS = [
        re.compile(r"(?i)(api[_-]?key|token|secret|password)\s*[:=]\s*[A-Za-z0-9_\-]{8,}"),
        re.compile(r"(?i)(bearer|basic)\s+[A-Za-z0-9_\-\.=]{8,}"),
    ]
    _PLACEHOLDER = "[REDACTED]"

    def __init__(self) -> None:
        self._secret_values: set[str] = set()
        for key, value in os.environ.items():
            if value and len(value) >= 8:
                if any(
                    kw in key.lower()
                    for kw in (
                        "key",
                        "token",
                        "secret",
                        "password",
                        "credential",
                        "auth",
                    )
                ):
                    self._secret_values.add(value)

    def _redact_string(self, s: str) -> str:
        for secret in self._secret_values:
            if secret and secret in s:
                s = s.replace(secret, self._PLACEHOLDER)
        for pattern in self._SECRET_PATTERNS:
            s = pattern.sub(lambda m: m.group(0).split(":", 1)[0].split("=", 1)[0] + ": " + self._PLACEHOLDER, s)
        return s

    def _redact_value(self, value: Any) -> Any:
        if isinstance(value, str):
            return self._redact_string(value)
        if isinstance(value, dict):
            return {k: self._redact_value(v) for k, v in value.items()}
        if isinstance(value, (list, tuple, set)):
            return type(value)(self._redact_value(v) for v in value)
        return value

    def __call__(
        self, logger: WrappedLogger, method_name: str, event_dict: EventDict
    ) -> EventDict:
        return self._redact_value(event_dict)


class SafeAddLoggerName:
    """structlog processor that sets ``event_dict["logger"]`` from the logger name.

    Safe alternative to ``structlog.stdlib.add_logger_name`` which crashes when the
    underlying logger isn't a ``logging.Logger`` (e.g. ``structlog.PrintLogger`` used by
    PrintLoggerFactory). If the logger has no ``name`` attribute we fall back to the
    string passed as the ``name`` kwarg of ``get_logger`` via the *last* event-context
    lookup in BoundLogger. Finally we fall back to ``"app"`` — never crashes.
    """

    def __call__(
        self, logger: WrappedLogger, method_name: str, event_dict: EventDict
    ) -> EventDict:
        if "logger" not in event_dict or not event_dict["logger"]:
            logger_name = getattr(logger, "name", None)
            if not logger_name:
                logger_name = event_dict.get("_logger_name") or "app"
            event_dict["logger"] = logger_name
        return event_dict


def configure_logging() -> structlog.stdlib.BoundLogger:
    settings = get_settings()
    log_level = getattr(logging, settings.log_level.upper(), logging.INFO)

    root = logging.getLogger()
    root.setLevel(log_level)
    if not root.handlers:
        stream_handler = logging.StreamHandler()
        stream_handler.setLevel(log_level)
        stream_handler.setFormatter(logging.Formatter("%(message)s"))
        root.addHandler(stream_handler)

    processors: list[Processor] = [
        structlog.contextvars.merge_contextvars,
        SafeAddLoggerName(),
        structlog.processors.add_log_level,
        structlog.processors.TimeStamper(fmt="iso", utc=True, key="timestamp"),
        structlog.processors.format_exc_info,
        EventRenamer("msg"),
        SecretRedactionProcessor(),
        structlog.processors.JSONRenderer(),
    ]

    structlog.configure(
        processors=list(processors),
        wrapper_class=structlog.stdlib.BoundLogger,
        context_class=dict,
        logger_factory=structlog.stdlib.LoggerFactory(),
        cache_logger_on_first_use=True,
    )

    for h in root.handlers:
        if isinstance(h.formatter, structlog.stdlib.ProcessorFormatter):
            h.setFormatter(logging.Formatter("%(message)s"))
        if not isinstance(h.formatter, logging.Formatter) or not getattr(h.formatter, "_fmt", None):
            h.setFormatter(logging.Formatter("%(message)s"))

    return structlog.get_logger()


def get_logger(name: str | None = None) -> structlog.stdlib.BoundLogger:
    try:
        logger = structlog.get_logger(name) if name else structlog.get_logger()
    except Exception:
        try:
            logger = configure_logging()
        except Exception:
            raw_print_logger = structlog.wrap_logger(
                logging.getLogger(name or "app"),
                wrapper_class=structlog.stdlib.BoundLogger,
                processors=[structlog.dev.ConsoleRenderer()],
            )
            return raw_print_logger
    if not isinstance(logger, structlog.stdlib.BoundLogger):
        logger = configure_logging()
    if name and not getattr(getattr(logger, "_logger", logger), "name", None):
        logger = logger.bind(_logger_name=name)
    return logger
