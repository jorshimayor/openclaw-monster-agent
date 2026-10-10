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

## Why it will die again in a week unless you do this

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
