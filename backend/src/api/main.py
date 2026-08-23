from __future__ import annotations

from contextlib import asynccontextmanager
from typing import Any, Dict, List

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel

from ..core.config import get_settings
from ..core.db import create_all_tables, dispose_db, init_db, is_db_available


def _is_db_available_safe() -> bool:
    try:
        return is_db_available()
    except Exception:
        return False
from ..core.logging import configure_logging, get_logger
from ..knowledge.memory import ExperienceMemory
from ..knowledge.store import CrystallizedKnowledgeStore
from ..llm.router import LLMRouter
from ..mcp.manager import McpServerManager
from ..orchestration.pipeline import PipelineExecutor

from .routes.tasks import router as tasks_router
from .routes.agents import router as agents_router
from .routes.mcp import router as mcp_router
from .routes.knowledge import router as knowledge_router


class LLMTestRequest(BaseModel):
    prompt: str


_app_state: Dict[str, Any] = {}


@asynccontextmanager
async def lifespan(app: FastAPI):
    configure_logging()
    logger = get_logger("api.main")
    settings = get_settings()
    try:
        llm_router = LLMRouter()
    except Exception as e:
        logger.warning("llm_router_init_failed", error=str(e))
        llm_router = None
    try:
        mcp_manager = McpServerManager(settings)
        await mcp_manager.start_all()
    except Exception as e:
        logger.warning("mcp_manager_init_failed", error=str(e))
        mcp_manager = None
    try:
        from ..agents.bus import get_event_bus

        loop = asyncio.get_running_loop()
        bus = get_event_bus()
        bus.start(mcp_manager=mcp_manager, loop=loop)
    except Exception as e:
        logger.warning("agent_event_bus_init_failed", error=str(e))
        bus = None
    try:
        knowledge_memory = ExperienceMemory()
    except Exception as e:
        logger.warning("knowledge_memory_init_failed", error=str(e))
        knowledge_memory = ExperienceMemory()
    db_ok = False
    try:
        db_ok = init_db(settings.database_url)
        if db_ok:
            try:
                await create_all_tables()
            except Exception as e:
                logger.warning("db_create_tables_failed", error=str(e))
    except Exception as e:
        logger.warning("db_init_failed", error=str(e))
        db_ok = False
    try:
        knowledge_store = CrystallizedKnowledgeStore(
            settings,
            memory=knowledge_memory,
            extractor=None,
        )
        if db_ok:
            try:
                await knowledge_store.bootstrap()
            except Exception as e:
                logger.warning("knowledge_store_bootstrap_failed", error=str(e))
    except Exception as e:
        logger.warning("knowledge_store_init_failed", error=str(e))
        knowledge_store = CrystallizedKnowledgeStore(settings)
    try:
        pipeline_executor = PipelineExecutor(
            settings,
            llm=llm_router,
            manager=mcp_manager,
            store=knowledge_store,
            memory=knowledge_memory,
        )
    except Exception as e:
        logger.warning("pipeline_executor_init_failed", error=str(e))
        pipeline_executor = None
    _app_state["settings"] = settings
    _app_state["llm_router"] = llm_router
    _app_state["mcp_manager"] = mcp_manager
    _app_state["knowledge_memory"] = knowledge_memory
    _app_state["knowledge_store"] = knowledge_store
    _app_state["pipeline_executor"] = pipeline_executor
    _app_state["logger"] = logger
    app.state.mcp_manager = mcp_manager
    app.state.llm_router = llm_router
    app.state.settings = settings
    app.state.logger = logger
    app.state.knowledge_memory = knowledge_memory
    app.state.knowledge_store = knowledge_store
    app.state.pipeline_executor = pipeline_executor
    logger.info(
        "api_startup",
        version="1.0.0",
        cors_origins_count=len(settings.backend_cors_origins),
        llm_router_ok=llm_router is not None,
        mcp_manager_ok=mcp_manager is not None,
        knowledge_store_ok=knowledge_store is not None,
        pipeline_executor_ok=pipeline_executor is not None,
        db_ok=db_ok,
    )
    yield
    if mcp_manager is not None:
        try:
            await mcp_manager.stop_all()
        except Exception as e:
            logger.error("mcp_manager_shutdown_failed", error=str(e))
    try:
        from ..agents.bus import get_event_bus

        bus = get_event_bus()
        if bus._started:
            await bus.stop()
    except Exception as e:
        logger.error("agent_event_bus_shutdown_failed", error=str(e))
    try:
        await dispose_db()
    except Exception as e:
        logger.error("db_dispose_failed", error=str(e))
    logger.info("api_shutdown")


def create_app() -> FastAPI:
    settings = get_settings()
    app = FastAPI(
        title="Monster Agent API",
        description="Omnipotent AI Agent Team — 8-specialist agent backend on OpenClaw",
        version="1.0.0",
        lifespan=lifespan,
    )

    origins: List[str] = [str(o).rstrip("/") for o in settings.backend_cors_origins]
    app.add_middleware(
        CORSMiddleware,
        allow_origins=origins,
        allow_credentials=True,
        allow_methods=["*"],
        allow_headers=["*"],
        expose_headers=["X-Request-ID", "Content-Type"],
    )

    @app.get("/api/health", tags=["system"])
    async def health() -> Dict[str, str]:
        return {"status": "ok", "version": "1.0.0"}

    @app.get("/api/health/diag", tags=["system"])
    async def health_diag() -> Dict[str, Any]:
        try:
            s = get_settings()
        except Exception as e:
            import traceback as _tb
            tb_lines = _tb.format_exc(limit=8).splitlines()
            err_payload: Dict[str, Any] = {
                "type": type(e).__name__,
                "message": str(e),
                "trace_tail": tb_lines[-6:],
            }
            return {
                "status": "settings_validation_error",
                "version": "1.0.0",
                "settings_load_failed": True,
                "settings_error": err_payload,
                "hint": "Most common: TELEGRAM_ADMIN_IDS env var numeric. Ensure secret put uses a STRING (value with quotes pasted fine). Fix: re-run secret put TELEGRAM_ADMIN_IDS with STRING value.",
            }
        try:
            db_url = s.database_url or ""
            db_redacted = ""
            if db_url:
                try:
                    from urllib.parse import urlparse
                    # Strip DATABASE_URL= prefix if user accidentally pasted whole .env line as secret value
                    url_for_parse = db_url
                    if "=" in url_for_parse and url_for_parse.lower().startswith("database_url="):
                        url_for_parse = url_for_parse.split("=", 1)[1]
                    up = urlparse(url_for_parse)
                    host_snip = (up.hostname or "")[:16]
                    port_snip = f":{up.port}" if up.port else ""
                    db_redacted = f"{up.scheme or 'unknown'}:***@{host_snip}{port_snip}{(up.path or '')[:24]}"
                except Exception:
                    db_redacted = f"<{len(db_url)} chars>"
            telegram_token_present = bool(s.telegram_bot_token)
            telegram_token_pfx = s.telegram_bot_token[:8] + "…" if telegram_token_present else ""
            cors_origins: List[str] = []
            try:
                cors_origins = [str(o).rstrip("/").strip().strip("`").strip("'\"") for o in s.backend_cors_origins]
            except Exception:
                cors_origins = []
            mcp_manager = _app_state.get("mcp_manager")
            running_servers: List[str] = []
            server_errors: Dict[str, str] = {}
            configured_servers: List[str] = []
            dead_processes: Dict[str, Dict[str, Any]] = {}
            if mcp_manager is not None:
                specs = getattr(mcp_manager, "_specs", {}) or {}
                configured_servers = sorted(specs.keys())
                procs = getattr(mcp_manager, "_processes", {}) or {}
                for name, proc in procs.items():
                    try:
                        rc = proc.poll()
                        if rc is None:
                            running_servers.append(name)
                        else:
                            # Dead process — read stderr tail if pipe still accessible
                            try:
                                import asyncio as _aio
                                loop_safe = _aio.get_event_loop()
                            except Exception:
                                loop_safe = None
                            stderr_tail = ""
                            if loop_safe is not None and not loop_safe.is_closed():
                                try:
                                    # best-effort: just read buffer from stderr attr; don't await inside sync handler
                                    stderr_raw = getattr(proc.stderr, "_buffer", b"")
                                    if stderr_raw:
                                        stderr_tail = stderr_raw.decode("utf-8", errors="replace")[-400:]
                                except Exception:
                                    stderr_tail = ""
                            dp: Dict[str, Any] = {"exit_code": rc}
                            if stderr_tail:
                                dp["stderr_tail"] = stderr_tail
                            dead_processes[name] = dp
                    except Exception:
                        pass
                start_errs = getattr(mcp_manager, "_start_errors", {}) or {}
                for name, err in start_errs.items():
                    if err:
                        server_errors[name] = str(err)[:300]
                # For processes that died after spawn passed the liveness check (later crash),
                # surface as errors too.
                for name, info in dead_processes.items():
                    if name in server_errors:
                        continue
                    rc = info.get("exit_code")
                    tail = info.get("stderr_tail", "")
                    msg = f"process exited with code {rc}"
                    if tail:
                        msg += f": {tail}"
                    server_errors[name] = msg[:300]
                transports = getattr(mcp_manager, "_transports", {}) or {}
                for name in configured_servers:
                    if name in server_errors or name in running_servers:
                        continue
                    try:
                        tr = transports.get(name)
                        if tr is None and name not in procs:
                            server_errors[name] = "never started (no process, no transport)"
                    except Exception:
                        pass
            mcp_servers_block: Dict[str, Any] = {
                "configured": configured_servers,
                "running": running_servers,
                "errors": server_errors,
            }
            if dead_processes:
                mcp_servers_block["dead_processes"] = dead_processes
            llm_r = _app_state.get("llm_router")
            llm_profiles_ok: List[str] = []
            raw_providers = {}
            if llm_r is not None:
                raw_providers = getattr(llm_r, "_providers", {}) or {}
                _ok: List[str] = []
                for name, p_obj in raw_providers.items():
                    try:
                        if isinstance(p_obj, dict):
                            flags = [p_obj.get("ok"), p_obj.get("available"), p_obj.get("api_key")]
                        else:
                            flags = [
                                getattr(p_obj, "ok", None),
                                getattr(p_obj, "available", None),
                                bool(getattr(p_obj, "api_key", None)),
                                bool(getattr(p_obj, "_api_key", None)),
                                bool(getattr(p_obj, "base_url", None)),
                            ]
                        if any(f for f in flags if f not in (None, "", False, 0, [], {})):
                            _ok.append(name)
                    except Exception:
                        pass
                llm_profiles_ok = sorted(_ok)[:20]
            return {
                "status": "ok",
                "version": "1.0.0",
                "database": {
                    "configured": bool(db_url),
                    "redacted": db_redacted,
                    # Honest signal: is the async engine actually initialized?
                    # (The old value checked logger+executor and reported True
                    # even while init_db was failing on the URL scheme.)
                    "engine_initialized": _is_db_available_safe(),
                },
                "telegram": {
                    "bot_token_present": telegram_token_present,
                    "bot_token_prefix": telegram_token_pfx,
                    "chat_id": (s.telegram_chat_id or "")[:16] + ("…" if len(s.telegram_chat_id or "") > 16 else ""),
                    "chat_id_present": bool(s.telegram_chat_id),
                    "admin_ids_count": len(s.telegram_admin_ids),
                    "admin_ids_present": [
                        (aid[:4] + "…" + aid[-2:] if len(aid) > 6 else aid) for aid in s.telegram_admin_ids
                    ],
                    "mcp_server_running": "telegram" in running_servers,
                    "mcp_startup_error": server_errors.get("telegram"),
                },
                "mcp_servers": mcp_servers_block,
                "llm": {
                    "profiles_configured_count": len(raw_providers),
                    "profiles_with_keys": llm_profiles_ok,
                    "router_initialized": llm_r is not None,
                },
                "cors_origins": cors_origins,
                "log_level": s.log_level,
                "pipeline_executor_initialized": _app_state.get("pipeline_executor") is not None,
                "agent_event_bus_running": _app_state.get("logger") is not None,
            }
        except Exception as e:
            import traceback as _tb
            tb_lines = _tb.format_exc(limit=12).splitlines()
            return {
                "status": "handler_error",
                "version": "1.0.0",
                "settings_load_succeeded": True,
                "handler_error": {
                    "type": type(e).__name__,
                    "message": str(e),
                    "trace_tail": tb_lines[-8:],
                },
            }

    @app.post("/api/llm/test", tags=["system"])
    async def llm_test(body: LLMTestRequest) -> Dict[str, Any]:
        log = get_logger("api.llm_test")
        llm_router = _app_state.get("llm_router")
        if llm_router is None:
            return {
                "provider": "none",
                "model": "none",
                "response": (
                    "LLMRouter not initialized (LLM provider API keys not set). "
                    "Stub echo: " + body.prompt[:200]
                ),
            }
        from ..core.types import AgentRole

        try:
            result = await llm_router.generate(body.prompt, AgentRole.ORCHESTRATOR)
            return {
                "provider": result["provider"],
                "model": result.get("model_name") or result.get("model", "unknown"),
                "response": result["response"],
            }
        except Exception as e:
            raw_err = str(e)
            if not raw_err:
                try:
                    raw_err = repr(e)
                except Exception:
                    raw_err = type(e).__name__
            log.error("llm_test_failed", error=raw_err)
            # Guardrail for empty error strings — this means an exception's
            # __str__ returned empty (e.g. a blank-constructed LLMProviderError
            # or a RetryError with no message). Prefer explicit diagnostics.
            if not raw_err.strip():
                raw_err = f"{type(e).__name__} (empty message; check server logs)"
            return {
                "provider": "error",
                "model": "unknown",
                "response": f"LLM call failed: {raw_err}",
            }

    app.include_router(tasks_router)
    app.include_router(agents_router)
    app.include_router(mcp_router)
    app.include_router(knowledge_router)
    return app


app = create_app()
