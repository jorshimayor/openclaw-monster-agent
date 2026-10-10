#!/usr/bin/env python3
"""Mint a Google refresh token, and write it where everything expects it.

    python3 scripts/google-auth.py

Why this exists: the calendar, Sheets, Docs and Gmail tools all read one
refresh token, and when it dies they all die together and silently. There was
no way to renew it except by hand, which is why it stayed dead.

If your OAuth consent screen is in "Testing", Google expires refresh tokens
after SEVEN DAYS regardless of use. Re-running this fixes today; publishing the
app fixes it for good. See the note printed at the end.
"""

from __future__ import annotations

import json
import re
import subprocess
import sys
import urllib.parse
import webbrowser
from http.server import BaseHTTPRequestHandler, HTTPServer
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
ENV_FILE = ROOT / "backend" / ".env"
PORT = 8765
REDIRECT = f"http://localhost:{PORT}"

# Must stay in step with _GOOGLE_SCOPES in
# backend/src/mcp/servers/google_workspace.py — a token minted without one of
# these fails only when that specific tool is first used.
SCOPES = [
    "https://www.googleapis.com/auth/calendar",
    "https://www.googleapis.com/auth/documents",
    "https://www.googleapis.com/auth/spreadsheets",
    "https://www.googleapis.com/auth/drive.file",
    "https://www.googleapis.com/auth/gmail.send",
    "https://www.googleapis.com/auth/gmail.readonly",
]


def read_env() -> dict[str, str]:
    out: dict[str, str] = {}
    for line in ENV_FILE.read_text().splitlines():
        if "=" in line and not line.strip().startswith("#"):
            key, _, value = line.partition("=")
            out[key.strip()] = value.strip().strip("\"'")
    return out


def write_env(key: str, value: str) -> None:
    text = ENV_FILE.read_text()
    line = f"{key}={value}"
    if re.search(rf"^{key}=", text, re.M):
        text = re.sub(rf"^{key}=.*$", line, text, flags=re.M)
    else:
        text = text.rstrip("\n") + "\n" + line + "\n"
    ENV_FILE.write_text(text)


class Catch(BaseHTTPRequestHandler):
    code: str | None = None

    def do_GET(self) -> None:  # noqa: N802
        params = urllib.parse.parse_qs(urllib.parse.urlparse(self.path).query)
        Catch.code = (params.get("code") or [None])[0]
        error = (params.get("error") or [None])[0]
        self.send_response(200)
        self.send_header("Content-Type", "text/html; charset=utf-8")
        self.end_headers()
        body = (
            "<h2>Authorised. You can close this tab.</h2>"
            if Catch.code
            else f"<h2>Refused: {error}</h2>"
        )
        self.wfile.write(body.encode())

    def log_message(self, *_args) -> None:
        pass  # the server is a one-shot catcher, not a web server


def post_form(url: str, fields: dict[str, str]) -> dict:
    """curl rather than urllib: a TLS-intercepting proxy breaks python's trust
    store on this machine, and curl uses the system keychain."""
    body = urllib.parse.urlencode(fields)
    out = subprocess.run(
        ["curl", "-sS", "--max-time", "45", url, "-d", "@-"],
        input=body, capture_output=True, text=True, timeout=60,
    )
    return json.loads(out.stdout or "{}")


def main() -> int:
    env = read_env()
    client_id = env.get("GOOGLE_WORKSPACE_CLIENT_ID", "")
    client_secret = env.get("GOOGLE_WORKSPACE_CLIENT_SECRET", "")
    if not client_id or not client_secret:
        print("GOOGLE_WORKSPACE_CLIENT_ID / _SECRET missing from backend/.env", file=sys.stderr)
        return 1

    auth_url = "https://accounts.google.com/o/oauth2/v2/auth?" + urllib.parse.urlencode({
        "client_id": client_id,
        "redirect_uri": REDIRECT,
        "response_type": "code",
        "scope": " ".join(SCOPES),
        # offline for a refresh token at all; consent to force a NEW one even
        # when a grant already exists, which is the case that silently returns
        # an access token only and leaves you none the wiser.
        "access_type": "offline",
        "prompt": "consent",
        "include_granted_scopes": "true",
    })

    print(f"Opening Google consent. If nothing opens, paste this:\n\n{auth_url}\n")
    print(f"Listening on {REDIRECT} for the redirect...")
    webbrowser.open(auth_url)

    server = HTTPServer(("127.0.0.1", PORT), Catch)
    server.handle_request()
    if not Catch.code:
        print("no authorisation code received", file=sys.stderr)
        return 1

    tok = post_form("https://oauth2.googleapis.com/token", {
        "code": Catch.code,
        "client_id": client_id,
        "client_secret": client_secret,
        "redirect_uri": REDIRECT,
        "grant_type": "authorization_code",
    })
    refresh = tok.get("refresh_token")
    if not refresh:
        print("no refresh_token returned:", json.dumps(tok)[:400], file=sys.stderr)
        return 1

    granted = tok.get("scope", "").split()
    missing = [s for s in SCOPES if s not in granted]

    write_env("GOOGLE_WORKSPACE_REFRESH_TOKEN", refresh)
    print(f"\nwrote GOOGLE_WORKSPACE_REFRESH_TOKEN to {ENV_FILE.relative_to(ROOT)}")
    print(f"granted {len(granted)} scopes; calendar: "
          f"{'yes' if any('calendar' in s for s in granted) else 'NO'}")
    if missing:
        print("  NOT granted (those tools will fail):")
        for s in missing:
            print(f"    {s}")

    print("\nNow push it to the Worker, or production keeps the dead one:")
    print("  cd backend-worker && grep -m1 '^GOOGLE_WORKSPACE_REFRESH_TOKEN=' ../backend/.env \\")
    print("    | cut -d= -f2- | npx wrangler secret put GOOGLE_WORKSPACE_REFRESH_TOKEN")
    print("  npx wrangler deploy          # the container reads env at start")
    print("\nIf this keeps dying every week: your OAuth consent screen is in")
    print("Testing, and Google expires those refresh tokens after 7 days.")
    print("Google Cloud Console -> APIs & Services -> OAuth consent screen ->")
    print("PUBLISH APP. Unverified is fine for personal use; the token stops expiring.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
