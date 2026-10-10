# Google Calendar (and the rest of Workspace)

## The short version

Nothing needs building. `read_calendar` and `create_calendar_event` already
exist in
[`google_workspace.py`](../backend/src/mcp/servers/google_workspace.py), and
`https://www.googleapis.com/auth/calendar` is already in the scope list.

The refresh token is dead:

```
{"error": "invalid_grant", "error_description": "Token has been expired or revoked."}
```

That one token is shared by calendar, Sheets, Docs and Gmail, so all four are
down together — including the Sheets sync that fills your timetable.

## Fix it

```bash
python3 scripts/google-auth.py
```

It opens Google's consent screen, catches the redirect on `localhost:8765`,
and writes the new token into `backend/.env`. Then push it to production, which
the script prints at the end — the Worker keeps using the dead one otherwise,
and the container only reads its environment at start, so a deploy is required
rather than optional.

If `localhost:8765` is rejected, the OAuth client is a **Web application**
type: add `http://localhost:8765` to its Authorised redirect URIs in the Google
Cloud console. A **Desktop app** client accepts any localhost port already.

## You are told when it breaks

`POST /api/integrations/google/check` runs daily from the 06:15 cron, just
before the study sync — which is one of the things that dies silently with the
credential. It exchanges the refresh token, and on the transition from working
to broken sends one Telegram message naming what is down and the command that
fixes it.

On the transition only. A daily "Google is still dead" is how an alert becomes
something you swipe away. It also tells you when the credential comes back, so
a fix is confirmed rather than assumed.

A network failure is reported as `unreachable` and never alerts — otherwise a
flaky minute sends you re-authorising a token that is perfectly fine.

`GET /api/integrations/google` is the same check with no notification. Safe to
curl, safe to poll.

A token that works but is **missing a scope** is flagged rather than passed:
those tools fail only when first used, which is a long way from the cause.

## What actually kills the token

The consent screen is already **In production**, so the seven-day Testing
expiry does not apply — I was wrong about that twice. What remains:

- **A Google account password change.** This revokes refresh tokens carrying
  Gmail scopes, and this one requests `gmail.send` and `gmail.readonly`. The
  most likely cause, and entirely silent.
- **Manual revocation** at myaccount.google.com/permissions.
- **Six months unused.**
- **Token churn** — every `prompt=consent` run mints a new refresh token, and
  past roughly a hundred per client per account Google invalidates the oldest.

Google does not say which, and there is no audit trail. Which is why the
watchdog above matters more than the diagnosis.

## The old theory, kept because it is true elsewhere

A Google OAuth consent screen in **Testing** issues refresh tokens that expire
after **seven days**, used or not. That is almost certainly what has been
happening, and it is why the Workspace integration keeps silently going quiet.

**Google Cloud Console → APIs & Services → OAuth consent screen → Publish
App.** Unverified is fine for personal use — you get a warning on the consent
screen and the token stops expiring. This is the actual fix; re-running the
script only buys another week.

## What breaks while the token is dead

Silently, which is the problem:

- the Google Sheets timetable sync
- the study-source syncs that read your roadmap sheets
- anything reading or writing Docs
- Gmail send and read
- calendar, which is what you noticed

`GET /api/mcp/doctor` reports status for every MCP server, and all of them read
as unknown rather than failed, so it does not surface this either.

## Wiring calendar into the morning brief

Once the token is live, the brief can read the day's events through the
existing tool. The pieces that exist today:

- `read_calendar(calendar_id, time_min, time_max, max_results)` — returns
  summary, start, end, link, attendees
- `/api/day` — the themes, blocks and commitments for a date

They are not joined yet. That is the only part that is genuinely unbuilt, and
it is small once the credential works.
