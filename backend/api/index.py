"""Vercel Python Serverless Function handler — wraps the FastAPI app via Mangum.

Run as Vercel Function (runtime @vercel/python):
  - Deployed from backend/ directory as Vercel project root
  - Vercel serves this via `backend/api/index.py` convention
  - Handler uses Mangum ASGI → Lambda/Vercel-event adapter
"""
from __future__ import annotations

import asyncio
import os
import sys
import pathlib
from typing import Any, Dict

_BACKEND_ROOT = pathlib.Path(__file__).resolve().parent.parent
_SRC_DIR = _BACKEND_ROOT / "src"
if str(_BACKEND_ROOT) not in sys.path:
    sys.path.insert(0, str(_BACKEND_ROOT))
if str(_SRC_DIR) not in sys.path:
    sys.path.insert(0, str(_SRC_DIR))

try:
    from dotenv import load_dotenv
    _env_path = _BACKEND_ROOT / ".env"
    if _env_path.exists():
        load_dotenv(str(_env_path))
except Exception:
    pass

from mangum import Mangum
from src.api.main import app as _fastapi_app

_handler = Mangum(_fastapi_app, lifespan="off")


def handler(event: Dict[str, Any], context: Any) -> Dict[str, Any]:
    """Vercel Python entry-point — compatible with @vercel/python runtime.

    @vercel/python passes an AWS Lambda-style event (APIGateway v2 proxy) with
    keys: ``rawPath``, ``rawQueryString``, ``headers``, ``requestContext``,
    ``body``, ``isBase64Encoded``, ``cookies``.

    Mangum handles the ASGI ↔ Lambda translation. We just forward the call.
    """
    # Force asyncio event loop — Vercel Lambda sometimes has no loop by default
    try:
        asyncio.get_event_loop_policy().get_event_loop()
    except Exception:
        try:
            asyncio.set_event_loop(asyncio.new_event_loop())
        except Exception:
            pass

    # Vercel sometimes injects env vars later than module import —
    # refresh settings on every invocation (pydantic-settings caches via lru_cache,
    # so users can clear by setting reimport; acceptable).
    return _handler(event, context)
