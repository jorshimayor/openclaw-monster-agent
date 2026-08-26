"""Inbound Telegram endpoints.

/webhook is the fast path: Telegram POSTs here the instant you reply, which
also wakes a sleeping container. /drain is the fallback for when no webhook is
registered — the cron calls it alongside the nag tick.

/webhook/register is a convenience so the webhook can be set up without
handling the bot token by hand.
"""

from __future__ import annotations

from typing import Any, Dict, Optional

from fastapi import APIRouter, Header, HTTPException, Request
from pydantic import BaseModel

from ...agents.telegram_inbox import drain_updates, handle_update, last_update_id
from ...core.config import get_settings
from ...core.logging import get_logger

logger = get_logger("api.telegram")
router = APIRouter(prefix="/api/telegram", tags=["telegram"])


class RegisterWebhookRequest(BaseModel):
    base_url: Optional[str] = None  # defaults to this request's own origin


@router.post("/webhook")
async def telegram_webhook(
    request: Request,
    x_telegram_bot_api_secret_token: Optional[str] = Header(default=None),
) -> Dict[str, Any]:
    settings = get_settings()
    expected = settings.telegram_webhook_secret
    if expected and x_telegram_bot_api_secret_token != expected:
        logger.warning("telegram_webhook_bad_secret")
        raise HTTPException(status_code=403, detail="bad webhook secret")

    try:
        update = await request.json()
    except Exception:
        raise HTTPException(status_code=400, detail="body must be JSON")
    if not isinstance(update, dict):
        raise HTTPException(status_code=400, detail="update must be an object")

    try:
        return await handle_update(update)
    except Exception as exc:
        # Always 200-shaped: a 5xx makes Telegram retry the same update forever.
        logger.exception("telegram_webhook_failed", error=str(exc))
        return {"handled": False, "error": str(exc)}


@router.post("/drain")
async def telegram_drain(limit: int = 40) -> Dict[str, Any]:
    return await drain_updates(limit=max(1, min(limit, 100)))


@router.get("/state")
async def telegram_state() -> Dict[str, Any]:
    s = get_settings()
    return {
        "bot_token_present": bool(s.telegram_bot_token),
        "chat_id_present": bool(s.telegram_chat_id),
        "admin_ids_count": len(s.telegram_admin_ids),
        "webhook_secret_set": bool(s.telegram_webhook_secret),
        "last_update_id": last_update_id(),
    }


@router.post("/webhook/register")
async def register_webhook(request: Request, body: RegisterWebhookRequest) -> Dict[str, Any]:
    """Point Telegram at this deployment's /api/telegram/webhook."""
    s = get_settings()
    if not s.telegram_bot_token:
        raise HTTPException(status_code=400, detail="TELEGRAM_BOT_TOKEN is not set")
    base = (body.base_url or str(request.base_url)).rstrip("/")
    if not base.startswith("https://"):
        raise HTTPException(
            status_code=400,
            detail=f"Telegram requires an https webhook URL; got {base!r}. Pass base_url explicitly.",
        )
    payload: Dict[str, Any] = {
        "url": f"{base}/api/telegram/webhook",
        "allowed_updates": ["message", "edited_message", "channel_post"],
        "drop_pending_updates": False,
    }
    if s.telegram_webhook_secret:
        payload["secret_token"] = s.telegram_webhook_secret
    try:
        import httpx

        async with httpx.AsyncClient(timeout=20) as client:
            r = await client.post(
                f"https://api.telegram.org/bot{s.telegram_bot_token}/setWebhook", json=payload
            )
            result = r.json()
    except Exception as exc:
        raise HTTPException(status_code=502, detail=f"setWebhook failed: {exc}")
    logger.info("telegram_webhook_registered", ok=result.get("ok"), url=payload["url"])
    return {"webhook_url": payload["url"], "telegram": result}
