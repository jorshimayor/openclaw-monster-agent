from __future__ import annotations

from contextlib import asynccontextmanager
from typing import Any, Dict, List

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel

from ..core.config import get_settings
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
        knowledge_memory = ExperienceMemory()
    except Exception as e:
        logger.warning("knowledge_memory_init_failed", error=str(e))
        knowledge_memory = ExperienceMemory()
    try:
        knowledge_store = CrystallizedKnowledgeStore(
            settings,
            memory=knowledge_memory,
            extractor=None,
        )
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
    )
    yield
    if mcp_manager is not None:
        try:
            await mcp_manager.stop_all()
        except Exception as e:
            logger.error("mcp_manager_shutdown_failed", error=str(e))
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
