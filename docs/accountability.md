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

## Quiet hours

Reminders are suppressed **22:00–07:00 local** (`USER_TIMEZONE_OFFSET_HOURS`).
The window wraps midnight, so it is a union of two ranges — a naive
`start <= hour < end` is false for every hour of it.

Crucially, **a suppressed reminder is not counted as a reminder**. `nag_count`
and `last_nagged_at` are untouched overnight, so you wake to reminder #4, not
reminder #40 — the ladder does not climb in silence.

Anything that came due overnight fires at 07:00. `/status` on Telegram and the
commitments page both show the window and when reminders resume. An explicit
"poke me now" (`POST /api/commitments/{id}/nag`, or the console button) ignores
quiet hours — the window stops the schedule, not a direct request.

| Env var | Default |
|---|---|
| `QUIET_HOURS_ENABLED` | `true` |
| `QUIET_HOURS_START` | `22` |
| `QUIET_HOURS_END` | `7` |

## Storage: fail loudly, never silently

The repos keep an in-memory fallback for local dev. In production that turned a
database hiccup into invisible reminders: rows lived in one container's memory,
nagged until that container was replaced, then vanished with no trace in
Postgres — which is exactly how one commitment reached **reminder #83** while
`SELECT * FROM commitments` returned nothing.

The fallback is now allowed **only when `DATABASE_URL` is unset**. With a
database configured but unavailable, writes raise `StorageUnavailable` and the
API returns **503** with the reason, rather than accepting data it is about to
lose. Postgres is also initialised before the event bus and nag engine start, so
nothing can be written during the window where the engine was not yet ready.

Tests opt into the in-memory store explicitly
(`tests/unit/accountability/conftest.py`) rather than inheriting the exemption,
so the production guard stays honest.

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

## Routing: not everything is a research task

Every submission used to enter the same 11-step multi-agent pipeline. "Remind me
to pick Ibrahim up at 1:30pm" produced a Task Complexity Assessment, a Team
Assembly table and Verifier Criteria — minutes of model time for what is one row
in a table. Intent is now decided first (`backend/src/agents/intent.py`):

| Intent | Example | What runs |
|---|---|---|
| `reminder` | "remind me to call the bank tomorrow" | filed and confirmed. No pipeline. |
| `question` | "what's on my plate today?" | one model turn. No pipeline. |
| `schedule` | "sync my schedule sheet" | sheet reconciliation. No pipeline. |
| `work` | "research Chelsea's xG this season" | the full pipeline, as before. |

Patterns decide the clear cases at zero cost; the model is asked only when they
are silent. **Ambiguity resolves to `work`** — routing real research down the
cheap path is the expensive mistake, not the other way round.

A reminder wrapping a work verb stays a reminder: "remind me to research zk
rollups at 5pm" is a reminder. "How should I research zk proofs?" is work.

Explicit reminders skip the approval gate — asking you to confirm the reminder
you just asked for is friction.

## The request is not a to-do item

An extracted item whose words are >=70% the request's own words is the *task*,
not homework, and is dropped. Without this, "Write a scannable market research
digest for Lagos readers" became a commitment and generated **83 pinned
reminders** chasing the user to do the assistant's job.

## Approval: brief first, chase second

Extracted commitments land as **`proposed`**, not `open`. The nag engine skips
proposed rows entirely, so nothing chases you about work you never agreed to.

```
task completes → items extracted as `proposed` → you are briefed
              → you approve  → `open` → reminders start
              → you decline  → `dropped`
```

Approve from Telegram (`/proposed`, `/approve all`, `/approve <id>`), from the
console's commitments page, or by replying "approve" in the task thread.
`COMMITMENT_REQUIRE_APPROVAL=false` restores the old chase-immediately behaviour.

## The task thread

Every task has a conversation (`backend/src/agents/task_chat.py`). The assistant
opens it with the brief; you reply in plain language:

| You say | What happens |
|---|---|
| "approve" | every proposed item goes `open`, reminders start |
| "approve `7a29`" | just that one |
| "push the README to friday evening" | due time moves |
| "drop that" | dropped, never chased |
| "done: https://…" | closes the one open item, artifact recorded |
| "why did you schedule these that way?" | answered from the task's own material |

**Intent is applied before the model is called**, and the reply is constrained to
an action note listing what actually changed. An assistant that says "approved!"
without changing any state is worse than one that says nothing. If the model is
unreachable the actions still happen and you get a plain description of them.

An artifact sent while several things are open closes *nothing* and asks which.

## The report you read

`backend/src/orchestration/report.py`. The final report used to be a debug dump —
a header, an overall confidence score, then each agent's raw output under
`## Output from ORCHESTRATOR (confidence 0.88)`. For a planner agent that raw
output *is its plan*, so asking for a reminder returned Task Complexity
Assessment, Team Assembly tables and Verifier Criteria, and no answer.

The report now holds the answer and nothing else. Nothing is lost: the console
renders every agent's output with its confidence in its own panel, and step
events carry the rest.

- **`write_user_report()`** asks the LLM for the reply, with a prompt that bans
  pipeline vocabulary outright and scales length to the request — a reminder gets
  two lines, a research task gets the full piece. The orchestrator agent is
  deliberately *not* used to write it; it is a planner, and reusing it is how the
  machinery reached the user in the first place.
- **`strip_scaffolding_sections()`** removes planner sections wherever they
  appear, plus prose naming the actors ("ORCHESTRATOR will dispatch the
  CalendarAgent") and headings left with an empty body. Two tiers of matching:
  distinctive phrases match anywhere in a heading, generic ones must be the whole
  heading, so "Reflections on the naira" and "Key risks" survive.
- **The fallback is honest.** Sanitising cannot turn a plan into an answer. If
  less than 35% of the text survives stripping, the fallback says it could not
  produce a clean summary and points at the task page, rather than dressing up
  the remnants. It only runs when the LLM is unavailable.

## Extraction: why it stays quiet

The pipeline's "final report" often contains its own working notes — team-assembly
tables, prompt-injection strategy, verifier criteria. An eager parser turns
`Estimated effort: < 5 min` into something you get nagged about. Three guards
(`backend/src/agents/commitment_extractor.py`):

1. **LLM first**, told explicitly to ignore scaffolding and to extract from the
   *request* when the report is internal noise.
2. **The markdown fallback requires weekday headings.** It exists for the
   weekly-plan output shape; on any other report it returns nothing rather than
   scraping every bullet.
3. **`looks_like_scaffolding()`** drops scope/risk/effort/dependency notes, agent
   names and prompts, wave/step labels, verifier assertions ("Start time is X"),
   table rows, and raw JSON. Survivors are deduped and capped at 10.

Explicit clock times are honoured: "by 1:30 pm WAT" files at 13:30 local, not the
19:00 evening default. A clock time that has already passed today stays due today
so it nags immediately — a reminder you missed is more urgent, not less.

## Study and practice sources

Roadmaps, question banks and a season calendar live in Google Sheets. Left alone
they are reference material you mean to open and don't. `study_sync` turns them
into a finite daily ask — two topics from the AI tracker, one interview question,
this week's BUILD task — filed as proposed commitments so the nag engine keeps
you honest once you approve them.

Sources are declared in `backend/config/study_sources.json`
(override with `STUDY_SOURCES_PATH`, or inline JSON in `STUDY_SOURCES`):

| Field | Meaning |
|---|---|
| `kind` | `backlog` (flat list), `weekly` (one row per week), or `routine` (whole checklist, once per period) |
| `cadence` | `routine` only: `monthly` / `quarterly` / `weekly` / `daily` |
| `daily_count` | how many items a backlog hands over per run |
| `due_time` | local 24h — put items in the block of your day where that work happens |
| `item_columns` | `weekly` only: which columns become items (e.g. `["BUILD"]`) |
| `priority_order` | `backlog` only: e.g. `["must","should","could"]` |

**A routine recurs; a backlog does not.** Row keys carry the period for routines
(`[sheet:id#5@2026-09]`), so September's "make the contribution" is not
suppressed by August's. Routines also ignore the sheet's Done column on purpose:
tick boxes are not period-scoped, so a step ticked in August is still ticked in
September and the sheet cannot be the record. The ledger is.

**Progress is tracked two ways.** With a Status column, closing a commitment
writes back and the sheet stays the record. Without one, the ledger *is* the
record — a row already filed is never handed to you twice, whatever became of it.
So a dropped item does not reappear tomorrow.

Two shape problems these real sheets exposed, both fixed by trusting data over
labels:

- **The header is not row 1.** These sheets open with a title, a byline, a blank,
  sometimes a five-row preamble — the AI tracker's header is on row 7. Candidate
  rows are scored on how many known column names they contain.
- **"Wk" is not the date.** The season calendar puts a week *number* immediately
  left of "Week starting". Name matching picks the number, every date fails to
  parse, and the calendar reads as empty. The week column is now chosen by
  which column actually contains parseable dates.

Runs daily at 07:15 WAT (`15 6 * * *`) — just after quiet hours end — or on
`/study` in Telegram. `GET /api/study/preview/<key>` shows what a source would
hand over next without filing anything.

## Theme rotation

Left alone, whichever area has the most sheet rows eats the week: the AI tracker
has 48 topics and the football calendar has one BUILD, so the tracker would
dominate every day while video, writing, code review and job applications never
appeared.

Each day gets the **daily** themes — Web3 bounty and Web3 study, the stated
priority — plus exactly **one** theme from the cycle:

`web2 → football → video → articles → code review → interview prep → job applications`

The position comes from `date.toordinal() % len(cycle)`, not a stored counter, so
the rotation survives restarts, never drifts, and tomorrow is predictable. Ordinals
rather than day-of-year matter: day-of-year repeats or skips a theme every January.

Study sources marked `rotation_gated` run only on their theme's day. Themes with
no sheet behind them (video, writing, applications) carry `tasks` in the config
and are filed directly, keyed `[theme:<name>@<date>#<n>]` so a re-run in the same
day is a no-op.

## What is allowed to interrupt you

Being tracked and being chased are separate. Every commitment carries a `remind`
flag; the nag engine only ever considers `remind = true`.

| Source | Reminds | Why |
|---|---|---|
| rotation themes (web3 daily + the day's cycle) | yes | the core day plan |
| football season BUILD | yes | the one mandatory column |
| investing monthly routine | yes | money, once a month |
| AI tracker topics | no | two a day, already in your study block |
| system design question bank | no | one a day, sits in learning time |

The silent ones still appear on `/day`, still close with an artifact, still count
as progress — they just never buzz a phone. `POST /api/commitments/{ref}/remind`
flips any single one, and `remind` in `study_sources.json` sets the default per
source.

This is what stops two dozen study picks becoming two dozen reminders.

## Chain rotation

Four chains sharing one "web3 study" slot means whichever is listed first is the
only one ever studied. Themes can therefore carry **variants**, and a variant
advances per appearance:

- **web3-study** (daily) → EVM → Solana → Cosmos → Move → Infra
- **chain-interviews** (daily) → EVM → Solana → Cosmos → Move → Security

Both are daily and share a variant order, so the chain you read at 05:45 is the
chain you are questioned on at 14:30. Practice used to sit in the cycle, which
meant each chain came round every forty days — sampling rather than practice.

Each variant's tasks carry the link to work from, so a session never starts with
"where do I begin".

The index is `ordinal // stride`, where stride is the gap between appearances —
1 for a daily theme, the cycle length for a cycled one. Indexing on the raw
ordinal **resonates** whenever the cycle length is a multiple of the variant
count: an 8-day cycle with 4 variants shows variant 0 on every appearance,
forever. That is exactly what happened first, and there is a test pinning it.

## Reminders are capped

A day with twenty approved items used to mean twenty reminders every ten minutes,
which trains you to ignore all of them. One round now sends at most
`NAG_MAX_PER_ROUND` (default **2**), longest-ignored first, and says how many are
held back so a quiet queue is never mistaken for an empty one.

Being held back is not being reminded: `nag_count` is untouched, so nothing
escalates without actually having been sent.

## The day view

`/day` puts one day on one screen, and keeps two things deliberately apart.

**Blocks** are your timetable template read from the sheet — Book Reading 05:00,
Deep Block 1 05:45, and so on. They are the *shape* of the day: faint labels down
the left, read-only. They repeat daily, and turning 21 recurring blocks into 21
tracked commitments would mean 21 things nagging you every day.

Blocks can be **ticked off per day**. The template cell is shared across all
seven weekdays, so completion is recorded in `day_block_state` keyed by
(day, slot, label) rather than written back to the sheet — Thursday's tick would
otherwise mark every day.

**Items** are real commitments — study picks, the football BUILD, reminders,
anything you add. Drag one to a slot and it reschedules
(`POST /api/day/items/{ref}/move`); click it to approve, close with an artifact,
snooze, or drop. Nothing writes back to the timetable sheet, so the template
stays intact.

Drag-and-drop is the native HTML5 API, not a library — and the time field on the
quick-add covers touch devices, where dragging is unreliable.

Two things the real sheet forced:

- **Times parse from ranges and stray seconds.** Cells read `5:45AM - 7:15AM` and
  `4:00:00 PM - 5:00PM`; without allowing optional seconds the `PM` was never
  reached and 16:00 parsed as 04:00.
- **Days are bracketed in local time, not UTC.** An item at 00:30 local belongs to
  that day even though it is the previous day in UTC.

Rescheduling clears any snooze: dragging something to a new time is an explicit
decision about when it happens, and a stale snooze would silently suppress it.

## Your starred repos

120 stars fetched from the REST API (the MCP server exposes no starred tool) and
sorted onto shelves, because 120 undifferentiated links is a wall rather than a
place to start: **system design · Move, Sui & Aptos · security & audits · DSA & interview drills ·
chains & protocol · AI & ML · engineering craft · everything else**. Most-starred
first within a shelf.

Bucketing checks system design *before* interviews — a system-design-notes repo
says "Interview" in its description and would land in the DSA shelf otherwise.
Needles shorter than five characters match on word boundaries: as bare
substrings `erc` matches "ex**erc**ises", which filed `rustlings` under chains.

The best of them are wired into the daily tasks, so a session opens with a page
rather than a decision — Solodit and `smart-contract-vulnerabilities` on bounty
days, `LeetCode-Questions-CompanyWise` on interview-prep days,
`system-design-notes` on web2 days, `Cyfrin/audit-checklist` on code-review days,
`learn-yul` and `all-things-reentrancy` on the matching chain variants.

## /study — the shelf

The material lived in eight Google Sheets, a GitHub account and a separate prep
site, so "go and study" started with deciding where to look. `/study` is all of
it on one page: every resource tab plus your own repos, searchable across titles
and notes, filterable by area (System design · AI engineering · Investing ·
Stocks · Football · Your work).

Searching expands every group automatically — hiding matches behind a "show all"
the user has to click per card defeats the search.

## The grouped reading list

`GET /api/study/resources` returns one view assembled from where the material
actually lives, and `/hq` → **resources** renders it:

- **sheet tabs** — Books & Docs, Free Courses, GitHub Resources, Engineering
  Blogs, Research Papers, Tools & Frameworks, Datasets & Practice, Football
  Sources. One group per tab, configured in `resource_tabs`.
- **your repos** — via `github.search_repositories`, newest-updated first, so
  what you have built sits beside what you are reading.
- **curated** — anything in the config that lives in neither.

Resource tabs are shaped inconsistently ("Course | Provider | Level" with no link
column; "Repo | Owner | Type | Link"; "Paper | Year | Category | Link"), so
columns are **inferred, not declared**: the header is the first row three-or-more
cells wide, the title is the first named column, the link is whichever column
holds URLs (falling back to scanning the row), and the note is the column that
explains why the thing matters — never the pricing column.

One broken source degrades to an empty group carrying its reason; it never
blanks the list. Cached 15 minutes since this fans out to a dozen network calls;
`?refresh=true` bypasses it. The page falls back to its local shelf if the API
is unreachable.

## Google Sheet schedules

Point `SCHEDULE_SHEET_ID` at a sheet and its rows become commitments; outcomes are
written back so the Sheet and the ledger never drift.

Two layouts are supported, detected from the header.

**Long** — one row per item:

| Day    | Time  | Task                   | Status | Artifact | Notes |
|--------|-------|------------------------|--------|----------|-------|
| Monday | 19:00 | Rewrite the bot README | done   | https://…|       |

Only `Task` is required — column names match loosely (`Task`/`What`/`Item`,
`Artifact`/`Proof`/`Link`). Without `Status`/`Artifact` columns the sync is
read-only.

**Matrix** — days across the top, time slots down the side, which is how people
actually build a weekly template:

| DURATION | TIME            | SUN | MON | TUE | … |
|----------|-----------------|-----|-----|-----|---|
| 90 mins  | 5:45AM - 7:15AM | Deep Block 1 | Deep Block 1 | … | |

A time range takes its start. Because the same slot repeats across seven
columns, a matrix sync files **one day at a time** — today by default, or pass
`days: ["monday"]`. Syncing the whole grid would put 150+ items a week on your
hook. Write-back does not apply: a matrix cell holds the activity name, and
there is nowhere to record a status without destroying the template.

- **Edit the Sheet** → title and due time update on the next sync.
- **Tick `Status`** → the commitment closes, reminders stop.
- **Close it on Telegram** → `done` plus the artifact are written into the Sheet.

Rows are matched to commitments by a `[sheet:<id>#<row>]` marker in the
commitment's detail, so re-syncing updates rather than duplicates.

Runs hourly (`5 * * * *`), on `/schedule` in Telegram, or via the console's
**SYNC SHEET** button. `GET /api/schedule/preview` shows the column mapping
before you let it file anything.

## Telegram commands

| Command | Effect |
|---------|--------|
| `/todo`, `/list` | open commitments, most overdue first |
| `/done <id> <link\|text>` | close one — artifact required |
| `/snooze <id> [mins]` | delay the next reminder (5–720 min); never closes |
| `/drop <id>` | abandon it, recorded as dropped, not done |
| `/add do the thing \| tomorrow evening` | file a new commitment |
| `/nag` | force a reminder round now |
| `/schedule` | re-sync the Google Sheet schedule |
| `/delete <id>` | remove a commitment entirely (vs `/drop`, which records it) |
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
| `SCHEDULE_SHEET_ID` | `""` | Google Sheet holding your schedule (blank disables the sync) |
| `SCHEDULE_SHEET_RANGE` | `Sheet1!A1:H200` | range to read |
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
| `DELETE` | `/api/commitments/{id}` | remove entirely — `/drop` keeps it on the ledger |
| `POST` | `/api/commitments/purge` | bulk delete by `task_id` or `status` (one filter required) |
| `DELETE` | `/api/tasks/{id}` | delete a task **and** the commitments it filed |
| `GET` | `/api/tasks/count` | total, for pagination |
| `GET` | `/api/schedule/preview` | column mapping + sample rows |
| `POST` | `/api/schedule/sync` | reconcile the Sheet with the ledger |
| `POST` | `/api/commitments/tick` | one reminder round (cron) |
| `POST` | `/api/commitments/extract` | `{task_id}` — re-extract from a report |
| `GET` | `/api/commitments/health` | loop state, storage backing, counts |
