from __future__ import annotations

import asyncio
import base64
import os
from email.mime.text import MIMEText
from typing import Any, Dict, List, Optional, Tuple

from ...core.logging import get_logger
from ..registry import Tool

logger = get_logger("mcp.servers.google_workspace")

_GOOGLE_SCOPES = [
    "https://www.googleapis.com/auth/calendar",
    "https://www.googleapis.com/auth/documents",
    "https://www.googleapis.com/auth/spreadsheets",
    "https://www.googleapis.com/auth/drive.file",
    "https://www.googleapis.com/auth/gmail.send",
    "https://www.googleapis.com/auth/gmail.readonly",
]


class GoogleWorkspaceMcpServer:
    def __init__(
        self,
        client_id: str,
        client_secret: str,
        refresh_token: Optional[str] = None,
        subject_email: Optional[str] = None,
    ) -> None:
        self.client_id = client_id
        self.client_secret = client_secret
        self.refresh_token = refresh_token or ""
        self.subject_email = subject_email or ""
        self._log = get_logger("mcp.servers.google_workspace")
        self._direct_client: Optional["_DirectGoogleClient"] = None

    def exposed_tools(self) -> List[Tool]:
        return [
            Tool(
                name="create_doc",
                description="Create a new Google Doc with title and optional content",
                input_schema={
                    "type": "object",
                    "properties": {
                        "title": {"type": "string"},
                        "content": {"type": "string"},
                        "folder_id": {"type": "string"},
                    },
                    "required": ["title"],
                },
                server="google_workspace",
            ),
            Tool(
                name="read_doc",
                description="Read the contents of an existing Google Doc",
                input_schema={
                    "type": "object",
                    "properties": {
                        "doc_id": {"type": "string"},
                    },
                    "required": ["doc_id"],
                },
                server="google_workspace",
            ),
            Tool(
                name="append_to_doc",
                description="Append text content to the end of a Google Doc",
                input_schema={
                    "type": "object",
                    "properties": {
                        "doc_id": {"type": "string"},
                        "content": {"type": "string"},
                    },
                    "required": ["doc_id", "content"],
                },
                server="google_workspace",
            ),
            Tool(
                name="read_calendar",
                description="Read events from Google Calendar within a date range (RFC3339 times, e.g. 2026-01-01T00:00:00Z)",
                input_schema={
                    "type": "object",
                    "properties": {
                        "calendar_id": {"type": "string", "default": "primary"},
                        "time_min": {"type": "string"},
                        "time_max": {"type": "string"},
                        "max_results": {"type": "integer", "default": 50},
                    },
                    "required": ["time_min", "time_max"],
                },
                server="google_workspace",
            ),
            Tool(
                name="create_calendar_event",
                description="Create a new event in Google Calendar. start_time/end_time are RFC3339.",
                input_schema={
                    "type": "object",
                    "properties": {
                        "calendar_id": {"type": "string", "default": "primary"},
                        "summary": {"type": "string"},
                        "description": {"type": "string"},
                        "start_time": {"type": "string"},
                        "end_time": {"type": "string"},
                        "attendees": {
                            "type": "array",
                            "items": {"type": "string"},
                            "description": "List of attendee email addresses",
                        },
                    },
                    "required": ["summary", "start_time", "end_time"],
                },
                server="google_workspace",
            ),
            Tool(
                name="write_sheet",
                description="Write values (2D array) to a range in a Google Sheet. Range format: Sheet1!A1:C10",
                input_schema={
                    "type": "object",
                    "properties": {
                        "sheet_id": {"type": "string"},
                        "range": {"type": "string"},
                        "values": {
                            "type": "array",
                            "items": {
                                "type": "array",
                                "items": {"type": ["string", "number", "boolean"]},
                            },
                        },
                    },
                    "required": ["sheet_id", "range", "values"],
                },
                server="google_workspace",
            ),
            Tool(
                name="read_sheet",
                description="Read values from a range in a Google Sheet. Range format: Sheet1!A1:C10",
                input_schema={
                    "type": "object",
                    "properties": {
                        "sheet_id": {"type": "string"},
                        "range": {"type": "string"},
                    },
                    "required": ["sheet_id", "range"],
                },
                server="google_workspace",
            ),
            Tool(
                name="send_email",
                description="Send an email via Gmail. Supports HTML if html=true.",
                input_schema={
                    "type": "object",
                    "properties": {
                        "to": {"type": "string", "description": "Comma-separated recipient emails"},
                        "subject": {"type": "string"},
                        "body": {"type": "string"},
                        "html": {"type": "boolean", "default": False},
                        "cc": {"type": "string"},
                        "bcc": {"type": "string"},
                    },
                    "required": ["to", "subject", "body"],
                },
                server="google_workspace",
            ),
            Tool(
                name="list_emails",
                description="List recent emails from Gmail INBOX. Returns subject, from, date, snippet, threadId.",
                input_schema={
                    "type": "object",
                    "properties": {
                        "max_results": {"type": "integer", "default": 20},
                        "query": {
                            "type": "string",
                            "default": "",
                            "description": "Gmail search query, e.g. 'from:someone@example.com newer_than:7d'",
                        },
                        "label_ids": {
                            "type": "array",
                            "items": {"type": "string"},
                            "default": ["INBOX"],
                        },
                    },
                },
                server="google_workspace",
            ),
            Tool(
                name="read_email",
                description="Read the full body (plain text + HTML snippet) of a single Gmail message by ID.",
                input_schema={
                    "type": "object",
                    "properties": {
                        "message_id": {"type": "string"},
                    },
                    "required": ["message_id"],
                },
                server="google_workspace",
            ),
        ]

    def server_command(self) -> Tuple[str, List[str], dict]:
        cmd = "npx"
        args = ["-y", "workspace-mcp"]
        env = {
            "GOOGLE_CLIENT_ID": self.client_id,
            "GOOGLE_CLIENT_SECRET": self.client_secret,
            "GOOGLE_REFRESH_TOKEN": self.refresh_token,
            "GOOGLE_SUBJECT_EMAIL": self.subject_email,
        }
        return cmd, args, env

    async def start(self) -> asyncio.subprocess.Process:
        cmd, args, env = self.server_command()
        merged_env = os.environ.copy()
        merged_env.update(env)
        proc = await asyncio.create_subprocess_exec(
            cmd,
            *args,
            stdin=asyncio.subprocess.PIPE,
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.PIPE,
            env=merged_env,
        )
        self._log.info("google_workspace_server_started", pid=proc.pid)
        return proc

    def _get_direct_client(self) -> Optional["_DirectGoogleClient"]:
        if not self.client_id or not self.client_secret or not self.refresh_token:
            return None
        if self._direct_client is None:
            try:
                self._direct_client = _DirectGoogleClient(
                    client_id=self.client_id,
                    client_secret=self.client_secret,
                    refresh_token=self.refresh_token,
                    subject_email=self.subject_email,
                )
            except Exception as exc:
                self._log.warning("direct_google_client_init_failed", error=str(exc))
                self._direct_client = None
        return self._direct_client

    async def invoke_direct(self, tool_name: str, arguments: Dict[str, Any]) -> Dict[str, Any]:
        client = self._get_direct_client()
        if client is None:
            raise RuntimeError(
                "Direct Google client unavailable — set GOOGLE_WORKSPACE_CLIENT_ID, "
                "GOOGLE_WORKSPACE_CLIENT_SECRET, and GOOGLE_WORKSPACE_REFRESH_TOKEN."
            )
        return await client.invoke(tool_name, arguments)


class _DirectGoogleClient:
    def __init__(
        self,
        client_id: str,
        client_secret: str,
        refresh_token: str,
        subject_email: str = "",
    ) -> None:
        self._creds = None
        self._services: Dict[str, Any] = {}
        self._log = get_logger("mcp.servers.google_workspace.direct")
        from google.oauth2.credentials import Credentials
        self._creds = Credentials(
            token=None,
            refresh_token=refresh_token,
            token_uri="https://oauth2.googleapis.com/token",
            client_id=client_id,
            client_secret=client_secret,
            scopes=_GOOGLE_SCOPES,
        )
        self._subject_email = subject_email

    def _service(self, name: str, version: str):
        key = f"{name}:{version}"
        if key in self._services:
            return self._services[key]
        from googleapiclient.discovery import build
        svc = build(name, version, credentials=self._creds, cache_discovery=False)
        self._services[key] = svc
        return svc

    async def invoke(self, tool_name: str, arguments: Dict[str, Any]) -> Dict[str, Any]:
        loop = asyncio.get_running_loop()
        handler = {
            "create_doc": self._create_doc,
            "read_doc": self._read_doc,
            "append_to_doc": self._append_to_doc,
            "read_calendar": self._read_calendar,
            "create_calendar_event": self._create_calendar_event,
            "write_sheet": self._write_sheet,
            "read_sheet": self._read_sheet,
            "send_email": self._send_email,
            "list_emails": self._list_emails,
            "read_email": self._read_email,
        }.get(tool_name)
        if handler is None:
            raise ValueError(f"Unknown google_workspace tool: {tool_name}")
        return await loop.run_in_executor(None, lambda: handler(arguments))

    def _create_doc(self, args: Dict[str, Any]) -> Dict[str, Any]:
        drive = self._service("drive", "v3")
        docs = self._service("docs", "v1")
        title = args["title"]
        folder_id = args.get("folder_id")
        body = {"name": title, "mimeType": "application/vnd.google-apps.document"}
        if folder_id:
            body["parents"] = [folder_id]
        created = drive.files().create(body=body, fields="id,webViewLink").execute()
        doc_id = created.get("id", "")
        content = args.get("content")
        if content and doc_id:
            requests = [
                {
                    "insertText": {
                        "location": {"index": 1},
                        "text": content,
                    }
                }
            ]
            docs.documents().batchUpdate(
                documentId=doc_id, body={"requests": requests}
            ).execute()
        return {"doc_id": doc_id, "url": created.get("webViewLink", ""), "title": title}

    def _read_doc(self, args: Dict[str, Any]) -> Dict[str, Any]:
        docs = self._service("docs", "v1")
        doc = docs.documents().get(documentId=args["doc_id"]).execute()
        title = doc.get("title", "")
        body_content = doc.get("body", {}).get("content", [])
        lines: List[str] = []
        for elem in body_content:
            para = elem.get("paragraph")
            if not para:
                continue
            for el in para.get("elements", []):
                run = el.get("textRun")
                if run:
                    lines.append(run.get("content", ""))
        return {
            "doc_id": args["doc_id"],
            "title": title,
            "text": "\n".join(lines),
        }

    def _append_to_doc(self, args: Dict[str, Any]) -> Dict[str, Any]:
        docs = self._service("docs", "v1")
        doc = docs.documents().get(documentId=args["doc_id"]).execute()
        end_index = 1
        body_content = doc.get("body", {}).get("content", [])
        if body_content:
            end_index = body_content[-1].get("endIndex", 1) - 1
        text_to_insert = "\n" + args["content"]
        requests = [
            {
                "insertText": {
                    "location": {"index": max(1, end_index)},
                    "text": text_to_insert,
                }
            }
        ]
        docs.documents().batchUpdate(
            documentId=args["doc_id"], body={"requests": requests}
        ).execute()
        return {"doc_id": args["doc_id"], "appended_chars": len(text_to_insert)}

    def _read_calendar(self, args: Dict[str, Any]) -> Dict[str, Any]:
        cal = self._service("calendar", "v3")
        events_result = (
            cal.events()
            .list(
                calendarId=args.get("calendar_id", "primary"),
                timeMin=args["time_min"],
                timeMax=args["time_max"],
                maxResults=args.get("max_results", 50),
                singleEvents=True,
                orderBy="startTime",
            )
            .execute()
        )
        events = events_result.get("items", [])
        simplified = [
            {
                "id": e.get("id"),
                "summary": e.get("summary"),
                "start": e.get("start", {}).get("dateTime") or e.get("start", {}).get("date"),
                "end": e.get("end", {}).get("dateTime") or e.get("end", {}).get("date"),
                "htmlLink": e.get("htmlLink"),
                "attendees": [a.get("email") for a in e.get("attendees", [])],
            }
            for e in events
        ]
        return {"count": len(simplified), "events": simplified}

    def _create_calendar_event(self, args: Dict[str, Any]) -> Dict[str, Any]:
        cal = self._service("calendar", "v3")
        event: Dict[str, Any] = {
            "summary": args["summary"],
            "start": {"dateTime": args["start_time"]},
            "end": {"dateTime": args["end_time"]},
        }
        if args.get("description"):
            event["description"] = args["description"]
        if args.get("attendees"):
            event["attendees"] = [{"email": email} for email in args["attendees"]]
        created = (
            cal.events()
            .insert(calendarId=args.get("calendar_id", "primary"), body=event, sendUpdates="all")
            .execute()
        )
        return {
            "event_id": created.get("id"),
            "htmlLink": created.get("htmlLink"),
            "summary": args["summary"],
        }

    def _write_sheet(self, args: Dict[str, Any]) -> Dict[str, Any]:
        sheets = self._service("sheets", "v4")
        body = {"values": args["values"]}
        result = (
            sheets.spreadsheets()
            .values()
            .update(
                spreadsheetId=args["sheet_id"],
                range=args["range"],
                valueInputOption="RAW",
                body=body,
            )
            .execute()
        )
        return {
            "sheet_id": args["sheet_id"],
            "updated_range": result.get("updatedRange"),
            "updated_rows": result.get("updatedRows", 0),
            "updated_cells": result.get("updatedCells", 0),
        }

    def _read_sheet(self, args: Dict[str, Any]) -> Dict[str, Any]:
        sheets = self._service("sheets", "v4")
        result = (
            sheets.spreadsheets()
            .values()
            .get(spreadsheetId=args["sheet_id"], range=args["range"])
            .execute()
        )
        return {
            "sheet_id": args["sheet_id"],
            "range": result.get("range"),
            "values": result.get("values", []),
            "major_dimension": result.get("majorDimension", "ROWS"),
        }

    def _send_email(self, args: Dict[str, Any]) -> Dict[str, Any]:
        gmail = self._service("gmail", "v1")
        is_html = bool(args.get("html"))
        msg = MIMEText(args["body"], "html" if is_html else "plain", "utf-8")
        msg["to"] = args["to"]
        msg["subject"] = args["subject"]
        if args.get("cc"):
            msg["cc"] = args["cc"]
        if args.get("bcc"):
            msg["bcc"] = args["bcc"]
        if self._subject_email:
            msg["from"] = self._subject_email
        raw = base64.urlsafe_b64encode(msg.as_bytes()).decode("ascii")
        sent = gmail.users().messages().send(userId="me", body={"raw": raw}).execute()
        return {
            "message_id": sent.get("id"),
            "thread_id": sent.get("threadId"),
            "label_ids": sent.get("labelIds", []),
            "to": args["to"],
            "subject": args["subject"],
        }

    def _list_emails(self, args: Dict[str, Any]) -> Dict[str, Any]:
        gmail = self._service("gmail", "v1")
        max_results = args.get("max_results", 20)
        query = args.get("query", "")
        label_ids = args.get("label_ids") or ["INBOX"]
        list_kwargs: Dict[str, Any] = {
            "userId": "me",
            "maxResults": max_results,
            "labelIds": label_ids,
        }
        if query:
            list_kwargs["q"] = query
        response = gmail.users().messages().list(**list_kwargs).execute()
        messages = response.get("messages", [])
        enriched = []
        for m in messages[:max_results]:
            mid = m["id"]
            try:
                detail = (
                    gmail.users()
                    .messages()
                    .get(userId="me", id=mid, format="metadata",
                         metadataHeaders=["Subject", "From", "Date", "To"])
                    .execute()
                )
                headers = {
                    h["name"].lower(): h["value"]
                    for h in detail.get("payload", {}).get("headers", [])
                }
                enriched.append({
                    "id": mid,
                    "thread_id": detail.get("threadId"),
                    "subject": headers.get("subject", "(no subject)"),
                    "from": headers.get("from", ""),
                    "to": headers.get("to", ""),
                    "date": headers.get("date", ""),
                    "snippet": detail.get("snippet", ""),
                    "label_ids": detail.get("labelIds", []),
                })
            except Exception as exc:
                enriched.append({"id": mid, "error": str(exc)})
        return {"count": len(enriched), "messages": enriched}

    def _read_email(self, args: Dict[str, Any]) -> Dict[str, Any]:
        gmail = self._service("gmail", "v1")
        message = (
            gmail.users()
            .messages()
            .get(userId="me", id=args["message_id"], format="full")
            .execute()
        )
        headers = {
            h["name"].lower(): h["value"]
            for h in message.get("payload", {}).get("headers", [])
        }
        plain_body = ""
        html_body_snippet = ""
        payload = message.get("payload", {})
        parts = payload.get("parts") or ([payload] if payload.get("body") else [])
        for part in parts:
            mime = part.get("mimeType", "")
            data = part.get("body", {}).get("data")
            if not data and part.get("parts"):
                for sub in part["parts"]:
                    sub_mime = sub.get("mimeType", "")
                    sub_data = sub.get("body", {}).get("data")
                    if sub_data and sub_mime == "text/plain" and not plain_body:
                        plain_body = base64.urlsafe_b64decode(sub_data + "===").decode("utf-8", errors="replace")
                    elif sub_data and sub_mime == "text/html" and not html_body_snippet:
                        decoded = base64.urlsafe_b64decode(sub_data + "===").decode("utf-8", errors="replace")
                        html_body_snippet = decoded[:2000]
                continue
            if not data:
                continue
            decoded = base64.urlsafe_b64decode(data + "===").decode("utf-8", errors="replace")
            if mime == "text/plain" and not plain_body:
                plain_body = decoded
            elif mime == "text/html" and not html_body_snippet:
                html_body_snippet = decoded[:2000]
        return {
            "message_id": args["message_id"],
            "thread_id": message.get("threadId"),
            "subject": headers.get("subject", ""),
            "from": headers.get("from", ""),
            "to": headers.get("to", ""),
            "cc": headers.get("cc", ""),
            "date": headers.get("date", ""),
            "snippet": message.get("snippet", ""),
            "plain_body": plain_body,
            "html_body_snippet": html_body_snippet,
            "label_ids": message.get("labelIds", []),
        }
