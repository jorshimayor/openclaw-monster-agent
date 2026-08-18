from __future__ import annotations

from typing import Any, Dict, List

from fastapi import APIRouter, HTTPException, Request

from ...core.logging import get_logger
from ...mcp.manager import McpServerManager, McpServerStatus

logger = get_logger(__name__)
router = APIRouter(prefix="/api/mcp", tags=["mcp"])


def _get_manager(request: Request) -> McpServerManager:
    manager = getattr(request.app.state, "mcp_manager", None)
    if manager is None:
        raise HTTPException(
            status_code=503,
            detail="MCP Server Manager not initialized. Check app startup logs.",
        )
    return manager


@router.get("/doctor", response_model=List[McpServerStatus])
async def mcp_doctor(request: Request) -> List[McpServerStatus]:
    logger.info("mcp_doctor_requested")
    manager = _get_manager(request)
    try:
        return manager.get_server_statuses()
    except Exception as exc:
        logger.exception("mcp_doctor_failed", error=str(exc))
        raise HTTPException(status_code=500, detail=f"Doctor check failed: {exc}")


@router.get("/doctor/{server}/probe", response_model=Dict[str, Any])
async def mcp_probe(request: Request, server: str) -> Dict[str, Any]:
    logger.info("mcp_probe_requested", server=server)
    manager = _get_manager(request)
    try:
        return await manager.probe_server(server)
    except ValueError as exc:
        logger.warning("mcp_probe_unknown_server", server=server, error=str(exc))
        raise HTTPException(status_code=404, detail=str(exc))
    except RuntimeError as exc:
        logger.warning("mcp_probe_not_started", server=server, error=str(exc))
        raise HTTPException(status_code=503, detail=str(exc))
    except Exception as exc:
        logger.exception("mcp_probe_failed", server=server, error=str(exc))
        raise HTTPException(status_code=500, detail=f"Probe failed: {exc}")
