from __future__ import annotations

import asyncio
import json
from datetime import datetime
from typing import Any, AsyncGenerator, Dict, Optional


class EventSourceResponse:
    def __init__(
        self,
        status_code: int = 200,
        headers: Optional[Dict[str, str]] = None,
        media_type: str = "text/event-stream",
    ) -> None:
        self.status_code = status_code
        self.media_type = media_type
        self._headers: Dict[str, str] = {
            "Cache-Control": "no-cache, no-transform",
            "Connection": "keep-alive",
            "X-Accel-Buffering": "no",
        }
        if headers:
            self._headers.update(headers)
        self._queue: asyncio.Queue[Optional[bytes]] = asyncio.Queue()
        self._done = False

    @property
    def headers(self) -> Dict[str, str]:
        return self._headers

    def _format_sse(
        self,
        data: Any,
        event: Optional[str] = None,
        id: Optional[str] = None,
        retry: Optional[int] = None,
    ) -> bytes:
        lines: list[str] = []
        if id is not None:
            lines.append(f"id: {id}")
        if event is not None:
            lines.append(f"event: {event}")
        if retry is not None:
            lines.append(f"retry: {retry}")
        if isinstance(data, (dict, list)):
            payload = json.dumps(data, default=str, ensure_ascii=False)
        else:
            payload = str(data)
        for line in payload.split("\n"):
            lines.append(f"data: {line}")
        raw = "\n".join(lines) + "\n\n"
        return raw.encode("utf-8")

    async def send(
        self,
        data: Any,
        event: Optional[str] = None,
        id: Optional[str] = None,
        retry: Optional[int] = None,
    ) -> None:
        if self._done:
            return
        chunk = self._format_sse(data, event=event, id=id, retry=retry)
        await self._queue.put(chunk)

    async def close(self) -> None:
        if self._done:
            return
        self._done = True
        await self._queue.put(None)

    async def ping(self, comment: str = "ping") -> None:
        if self._done:
            return
        raw = f": {comment}\n\n".encode("utf-8")
        await self._queue.put(raw)

    async def __aiter__(self) -> AsyncGenerator[bytes, None]:
        try:
            while True:
                chunk = await self._queue.get()
                if chunk is None:
                    return
                yield chunk
        finally:
            self._done = True

    async def body_iterator(self) -> AsyncGenerator[bytes, None]:
        async for chunk in self:
            yield chunk

    def make_sse_id(self) -> str:
        return datetime.utcnow().strftime("%Y%m%d%H%M%S%f")
