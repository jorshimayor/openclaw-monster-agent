"""How another agent finds out how to talk to this one.

Served unauthenticated and on the Access bypass list, deliberately: an agent
that cannot get in is precisely the agent that needs to read how. A 401 that
does not say what to do next is a dead end, so the Worker's rejection points
here and this says the rest.

Nothing here is a secret. It is a description of a door, not a key.
"""

from __future__ import annotations

from typing import Any, Dict

from fastapi import APIRouter

router = APIRouter(tags=["system"])

CARD: Dict[str, Any] = {
    "name": "Monster Agent",
    "description": (
        "A personal accountability and research assistant. It holds commitments "
        "and chases them until an artifact proves they are done, runs a "
        "multi-agent research pipeline, and tracks a 48-week research "
        "fellowship. It reaches a real person's phone, so treat anything that "
        "notifies as an interruption of a human, not a log line."
    ),
    "contact": "https://jorshimayor.is-a.dev",
    "auth": {
        "type": "cloudflare-access-service-token",
        "how": (
            "Send CF-Access-Client-Id and CF-Access-Client-Secret on every "
            "request. Ask the operator to issue you a service token; tokens are "
            "per-agent so one can be revoked without affecting the others."
        ),
        "unauthenticated_paths": ["/api/agent-card", "/api/health"],
        "note": (
            "A 401 means no token was presented; a 403 means the token is valid "
            "but not on this application's policy."
        ),
    },
    "preferred_transport": {
        "type": "mcp",
        "why": (
            "Tools are discoverable and arguments are validated before they "
            "reach the API. Prefer this over raw HTTP."
        ),
        "server": "mcp-servers/monster in github.com/jorshimayor/openclaw-monster-agent",
        "env": [
            "MONSTER_API_BASE_URL",
            "MONSTER_ACCESS_CLIENT_ID",
            "MONSTER_ACCESS_CLIENT_SECRET",
        ],
    },
    "capabilities": [
        {"tool": "get_today", "http": "GET /api/day",
         "does": "The day's themes, time blocks and everything due."},
        {"tool": "list_commitments", "http": "GET /api/commitments",
         "does": "The accountability ledger. status=proposed|open|done|dropped."},
        {"tool": "create_commitment", "http": "POST /api/commitments",
         "does": "File something the human must do. It will be chased until closed."},
        {"tool": "close_commitment", "http": "POST /api/commitments/{ref}/done",
         "does": "Close with proof. Requires a URL or 40+ characters of substance."},
        {"tool": "get_fellowship_status", "http": "GET /api/day",
         "does": "Week of 48, the anchor paper, the lab, what is due."},
        {"tool": "list_tasks", "http": "GET /api/tasks", "does": "Research tasks."},
        {"tool": "create_task", "http": "POST /api/tasks",
         "does": "Hand the agent team a research question. Costs model credits."},
        {"tool": "suggest_study", "http": "POST /api/study/queue",
         "does": (
             "Recommend what to learn next. Queues for the human to promote — "
             "it does NOT create a reminder, so suggest freely. The rationale "
             "is required and is the whole value."
         )},
        {"tool": "list_study_queue", "http": "GET /api/study/queue",
         "does": "What has already been suggested. Check before adding."},
        {"tool": "notify", "http": "POST /api/notify/send",
         "does": "Message the human on Telegram and Slack."},
    ],
    "what_the_human_is_doing": {
        "_why": "So a suggestion lands on the work, not on a guess about it.",
        "building": "Pesarc — cross-border payments on EVM and SVM; and an "
                    "invariant-first smart-contract auditing agent.",
        "auditing": "Web3 bug bounties daily — Solodit findings, invariant "
                    "libraries, Foundry PoCs.",
        "studying": "A 48-week applied-AI research fellowship: agent "
                    "evaluation harnesses and retrieval systems.",
        "wants_to_be": "A software engineer who passes hard interviews, ships "
                       "audited contracts, and publishes work worth reading.",
        "ask_first": "GET /api/day and GET /api/study/queue before suggesting, "
                     "so you build on what is already queued rather than "
                     "repeating it.",
    },
    "rules": [
        "An acknowledgement never closes a commitment. Only a link, a file, or "
        "40+ characters of real substance — 'done' is rejected with a 422.",
        "Do not file vague or speculative work. A commitment you cannot satisfy "
        "becomes a reminder that fires forever.",
        "notify reaches a phone. Use it for things that warrant interrupting a "
        "person, not for status chatter.",
        "create_task runs a multi-agent pipeline on the operator's credits. "
        "Send a real question, not a ping.",
        "A study suggestion is not a commitment. It queues until the human "
        "promotes it, which is why you may suggest freely and why a weak "
        "rationale is simply ignored. 'Learn Rust' is noise.",
        "There is no delete or purge in the MCP surface, by design. If you think "
        "you need to erase part of the accountability record, you are wrong.",
    ],
    "on_error": {
        "422": "Your artifact was not good enough. Send what you produced, not that you produced it.",
        "401": "No Access token. Request a service token from the operator.",
        "403": "Token valid but not permitted for this application.",
        "503": "Storage is unavailable. Nothing was saved — do not treat as success and retry later.",
    },
}


@router.get("/api/agent-card")
async def agent_card() -> Dict[str, Any]:
    """Unauthenticated on purpose — see the module docstring."""
    return CARD


@router.get("/.well-known/agent-card.json")
async def well_known_agent_card() -> Dict[str, Any]:
    """The conventional location, so an agent can guess it without being told."""
    return CARD
