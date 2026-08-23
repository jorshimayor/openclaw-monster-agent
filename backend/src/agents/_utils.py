from __future__ import annotations

import asyncio
import fnmatch
import json
import uuid
from typing import Any, Dict, List, Optional

from ..core.logging import get_logger

logger = get_logger(__name__)


def tool_matches(tool_allowlist: List[str], tool_name: str) -> bool:
    if not tool_allowlist:
        return False
    for pattern in tool_allowlist:
        if fnmatch.fnmatchcase(tool_name, pattern):
            return True
    return False


async def _call_tool(
    tool_name: str,
    arguments: Dict[str, Any],
    transport: Optional[Any] = None,
) -> Dict[str, Any]:
    if transport is None:
        return {"skipped": True, "reason": "no_mcp_transport"}

    # RoutingMcpTransport (production path): server-prefix routing + the
    # direct Google client. Raw stdio transports keep the legacy path below.
    route = getattr(transport, "route_tool_call", None)
    if route is not None:
        return await route(tool_name, arguments or {})

    msg_id = str(uuid.uuid4())
    payload: Dict[str, Any] = {
        "jsonrpc": "2.0",
        "id": msg_id,
        "method": "tools/call",
        "params": {
            "name": tool_name,
            "arguments": arguments or {},
        },
    }
    line = json.dumps(payload) + "\n"
    loop = asyncio.get_event_loop()
    future: "asyncio.Future[dict]" = loop.create_future()

    pending = getattr(transport, "_pending", None)
    if pending is None:
        logger.warning("call_tool_transport_no_pending", tool=tool_name)
        return {"skipped": True, "reason": "transport_missing_pending_attr"}

    pending[msg_id] = future
    try:
        lock = getattr(transport, "_lock", None)
        if lock is not None:
            async with lock:
                proc_stdin = getattr(transport, "_proc", None)
                if proc_stdin is None or proc_stdin.stdin is None:
                    return {"skipped": True, "reason": "transport_stdin_unavailable"}
                proc_stdin.stdin.write(line.encode("utf-8"))
                await proc_stdin.stdin.drain()
        else:
            proc_stdin = getattr(transport, "_proc", None)
            if proc_stdin is None or proc_stdin.stdin is None:
                return {"skipped": True, "reason": "transport_stdin_unavailable"}
            proc_stdin.stdin.write(line.encode("utf-8"))
            await proc_stdin.stdin.drain()

        read_timeout = getattr(transport, "_read_timeout", 30.0)
        timeout = min(read_timeout, 15.0)
        return await asyncio.wait_for(future, timeout=timeout)
    except asyncio.TimeoutError:
        logger.warning("call_tool_timeout", tool=tool_name, timeout=15)
        return {"skipped": True, "reason": "timeout"}
    except Exception as exc:
        logger.warning("call_tool_failed", tool=tool_name, error=str(exc))
        return {"skipped": True, "reason": str(exc)}
    finally:
        pending.pop(msg_id, None)
