# Accountability — commitments, nagging, and artifacts

The assistant used to produce a plan, push it to Telegram once, and forget it.
This subsystem makes it persistent: it files the things *you* said you would do,
chases each one on an escalating schedule, and refuses to close any of them
until you hand over something inspectable.

## The rule

**A commitment closes only with an artifact.** The word "done" is a claim, not
proof. Three things count (`backend/src/core/artifact.py`):

| Kind   | What it is                                    |
|--------|-----------------------------------------------|
| `link` | any `http(s)://` URL in your reply            |
| `file` | a document or photo attached to the message   |
| `text` | ≥ 40 characters, after acknowledgement filler ("done", "yep", "already") is stripped |

Rejections come back with the reason, and the commitment stays open.

## Lifecycle

```
task completes
   → LLM extracts YOUR action items from the final report
   → each becomes a commitment row with a due time
   → Telegram: "3 things now on your hook"

due time passes
   → reminder #1 … #2 … #n, intervals shrinking, tone escalating
   → nothing stops this except an artifact or an explicit /drop

you reply with a link / file / real text
   → closed, artifact recorded, reminders stop
```

## The escalation ladder

`backend/src/agents/nagger.py`. The rung is chosen by how many reminders have
already gone unanswered.

| Reminders sent | Interval | Tier | Behaviour                          |
|----------------|----------|------|------------------------------------|
| 0–1            | 30 min   | P1   | plain reminder, sound on           |
| 2–3            | 20 min   | P1   | blunter, restates the ask          |
| 4–6            | 15 min   | P0   | pinned, counts the misses          |
| 7–11           | 10 min   | P0   | pinned, shouts                     |
| 12+            | 10 min   | P0   | pinned, shouts, mirrors to Slack   |

The interval floor is 10 minutes and the ladder has no terminal rung — it
plateaus rather than stopping. `/mute` silences *status updates* only;
reminders for open commitments bypass the Personal Assistant's rate limiter
and mute state entirely, by design.

## Telegram commands

| Command | Effect |
|---------|--------|
| `/todo`, `/list` | open commitments, most overdue first |
| `/done <id> <link\|text>` | close one — artifact required |
| `/snooze <id> [mins]` | delay the next reminder (5–720 min); never closes |
| `/drop <id>` | abandon it, recorded as dropped, not done |
| `/add do the thing \| tomorrow evening` | file a new commitment |
| `/nag` | force a reminder round now |
| `/status` | counts + reminder-loop health |
| `/help` | the above |

Replying to a reminder with just a link or a file works too: if exactly one
commitment is overdue it closes that one, otherwise the bot asks which.

## How reminders survive container sleep

The container sleeps after 15 idle minutes, and an in-process loop dies with
it. So the reminder clock lives in the Worker:

- **`*/10 * * * *` cron** → `POST /api/commitments/tick` (one reminder round)
  and `POST /api/telegram/drain` (pick up replies). Waking the container is the
  point.
- **In-process loop** (`NAG_TICK_SECONDS`, default 300s) covers the gaps while
  the container is already awake.

Both call the same idempotent `NagEngine.tick()`.

⚠️ **Cost:** a 10-minute cron is shorter than the container's 15-minute
`sleepAfter`, so the container effectively stays warm around the clock. Raise
the cron interval in `backend-worker/wrangler.jsonc` (or lower `sleepAfter` in
`backend-worker/src/index.ts`) to trade persistence for spend.

## Inbound replies: webhook vs drain

Both paths land in `agents/telegram_inbox.handle_update()`.

**Webhook (preferred — instant, and it wakes the container):**

```bash
curl -X POST https://monster-agent-backend.joelobafemii.workers.dev/api/telegram/webhook/register \
  -H 'Content-Type: application/json' \
  -d '{"base_url":"https://monster-agent-backend.joelobafemii.workers.dev"}'
```

Set `TELEGRAM_WEBHOOK_SECRET` first so the endpoint can't be spoofed:

```bash
npx wrangler secret put TELEGRAM_WEBHOOK_SECRET
```

**Drain (fallback):** with no webhook registered, the cron long-polls
`getUpdates` every 10 minutes. Replies are picked up, just less promptly.

Either way, only `TELEGRAM_ADMIN_IDS` can command the bot. With no admin ids
set it falls back to accepting only the configured `TELEGRAM_CHAT_ID`.

## Settings

| Env var | Default | Meaning |
|---------|---------|---------|
| `NAG_ENABLED` | `true` | master switch for reminders |
| `NAG_TICK_SECONDS` | `300` | in-process loop cadence |
| `COMMITMENT_AUTO_EXTRACT` | `true` | file action items from completed reports |
| `USER_TIMEZONE_OFFSET_HOURS` | `1` | WAT — "evening" in a plan means *your* evening |
| `PUBLIC_APP_URL` | pages.dev URL | console links inside reminders |
| `TELEGRAM_WEBHOOK_SECRET` | `""` | shared secret for the webhook |

## Storage

Postgres table `commitments` (`backend/migrations/0002_commitments.sql`;
`create_all_tables()` also builds it on boot). When `DATABASE_URL` is unset the
repo falls back to a process-local dict so the flow still works locally — that
state is lost on restart, which is why `/api/commitments/health` reports
`db_backed`, and the console shows "IN-MEMORY (LOST ON RESTART)" in red.

## API

| Method | Path | Notes |
|--------|------|-------|
| `GET` | `/api/commitments?status=open` | list |
| `POST` | `/api/commitments` | file one (`due_at`, `due_in_minutes`, or `day`+`time_of_day`) |
| `POST` | `/api/commitments/{id}/done` | **422** with the reason if the artifact is too thin |
| `POST` | `/api/commitments/{id}/snooze` | `{minutes}` |
| `POST` | `/api/commitments/{id}/drop` | abandon |
| `POST` | `/api/commitments/{id}/nag` | remind me now |
| `POST` | `/api/commitments/tick` | one reminder round (cron) |
| `POST` | `/api/commitments/extract` | `{task_id}` — re-extract from a report |
| `GET` | `/api/commitments/health` | loop state, storage backing, counts |
