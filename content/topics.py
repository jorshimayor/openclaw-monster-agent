#!/usr/bin/env python3
"""The topic bank, published into the Google Doc one dated version at a time.

    python3 content/topics.py                      # preview, writes nothing
    python3 content/topics.py --publish            # append the next version
    python3 content/topics.py --promote            # thread + newsletter for the pick

Why a bank and not a generator. docs/writing-standard.md refuses generated
prose, and for the same reason this refuses generated topics: a title you did
not earn is a title you will have nothing true to say under. So every entry in
topics.json carries a `project` — the thing you do that produces the evidence
— and content/pipeline.py turns that evidence into the three levels.

What is automated is the boring half: rendering the bank, appending a dated
version so you can see what changed between them, and drafting the promotion
for whichever piece the version is built around.

Appending only. The doc is 48KB of work that predates this and nothing here
overwrites a character of it.
"""

from __future__ import annotations

import argparse
import json
import os
import sys
from datetime import date
from pathlib import Path
from typing import Any, Dict, List, Optional

HERE = Path(__file__).resolve().parent
BANK = HERE / "topics.json"
# Tracked, not in content/out/: which topics the doc already has is durable
# knowledge about an external document, not build output. Ignored, a run from
# another machine would publish the whole bank again.
STATE = HERE / "topics-published.json"

DOCS_API = "https://docs.googleapis.com/v1/documents"
TOKEN_URL = "https://oauth2.googleapis.com/token"
LEVELS = ("beginner", "intermediate", "advanced")


def load_bank() -> Dict[str, Any]:
    return json.loads(BANK.read_text())


def published() -> Dict[str, Any]:
    """Which topics have already gone into the doc, by title."""
    try:
        return json.loads(STATE.read_text())
    except (FileNotFoundError, json.JSONDecodeError):
        return {"version": 0, "titles": []}


def pending(bank: Dict[str, Any], seen: List[str]) -> List[Dict[str, Any]]:
    """Sections containing only topics the doc has not had yet.

    Keyed on the title rather than an index, so reordering topics.json or
    dropping one does not re-publish the rest.
    """
    out = []
    for section in bank["sections"]:
        fresh = [t for t in section["topics"] if t["title"] not in seen]
        if fresh:
            out.append({**section, "topics": fresh})
    return out


def render(sections: List[Dict[str, Any]], version: int, today: date) -> str:
    """The text appended to the doc. Plain, because the doc styles itself."""
    lines = [
        "",
        f"TOPIC BANK v{version} — {today.isoformat()}",
        "",
        "Each topic carries the project that earns it. Write the project first;"
        " the article is the write-up, which is the only order that produces"
        " something true. Target query is the search this is aimed at.",
        "",
    ]
    for section in sections:
        lines += ["", section["title"].upper(), "", section["why"], ""]
        for n, topic in enumerate(section["topics"], start=1):
            lines += [
                f"{n}. {topic['title']}",
                f"    Level: {topic['level']}   Target query: {topic['query']}",
                f"    Project: {topic['project']}",
                f"    Why this one: {topic['angle']}",
                "",
            ]
    return "\n".join(lines)


def pick(sections: List[Dict[str, Any]]) -> Optional[Dict[str, Any]]:
    """The version's promoted piece: the first advanced topic, else intermediate.

    Beginner pieces are never promoted. A thread that opens with something
    your audience already knows spends the attention it just earned.
    """
    for level in ("advanced", "intermediate"):
        for section in sections:
            for topic in section["topics"]:
                if topic["level"] == level:
                    return {**topic, "section": section["title"]}
    return None


def promotion(topic: Dict[str, Any], version: int) -> str:
    """Thread and newsletter scaffolding for the promoted piece.

    Scaffolding, not copy. content/pipeline.py's channel notes say what each
    one has to do; filling them in is the part that has to be yours, because a
    generated thread reads exactly like a generated thread.
    """
    return "\n".join([
        f"PROMOTION — TOPIC BANK v{version}",
        f"Piece: {topic['title']}",
        f"Section: {topic['section']}   Level: {topic['level']}",
        "",
        "X THREAD",
        "  1. Open with the finding, not with 'a thread'. The number or the",
        f"     surprise from: {topic['project'][:88]}",
        "  2. One claim per post. The claim you could not have made before",
        "     doing the project.",
        "  3. The counter-intuitive one — what you expected and what happened.",
        "  4. The method, briefly, so it is checkable.",
        "  5. Last post links the article. No 'follow for more'.",
        "",
        "NEWSLETTER",
        "  Subject: the finding in under nine words, no colon-subtitle.",
        "  Intro: the one sentence that makes someone open the article.",
        "  Body: what you learned this week that you did not expect,",
        "        then the link. One link.",
        "",
        f"  Target query to keep in the title: {topic['query']}",
        "",
        "Run the draft through POST /api/writing/check before it ships.",
    ])


# --- Google Docs ----------------------------------------------------------

def _token() -> str:
    import httpx

    missing = [k for k in (
        "GOOGLE_WORKSPACE_CLIENT_ID",
        "GOOGLE_WORKSPACE_CLIENT_SECRET",
        "GOOGLE_WORKSPACE_REFRESH_TOKEN",
    ) if not os.environ.get(k)]
    if missing:
        sys.exit(f"missing credentials: {', '.join(missing)}")

    r = httpx.post(TOKEN_URL, timeout=30, data={
        "client_id": os.environ["GOOGLE_WORKSPACE_CLIENT_ID"],
        "client_secret": os.environ["GOOGLE_WORKSPACE_CLIENT_SECRET"],
        "refresh_token": os.environ["GOOGLE_WORKSPACE_REFRESH_TOKEN"],
        "grant_type": "refresh_token",
    })
    if r.status_code != 200:
        sys.exit(f"token refresh failed: {r.status_code} {r.json().get('error')}")
    return r.json()["access_token"]


def tabs(doc_id: str, head: Dict[str, str]) -> Dict[str, Dict[str, Any]]:
    """{tab title: {id, end}} for every tab in the document.

    includeTabsContent is not optional. Without it the API returns only the
    FIRST tab's body and says nothing about the others, so "the end of the
    document" silently means "the end of tab one" — which is how a whole topic
    bank once landed at the bottom of Web3 Security Topics.
    """
    import httpx

    r = httpx.get(f"{DOCS_API}/{doc_id}", headers=head, timeout=60,
                  params={"includeTabsContent": "true"})
    r.raise_for_status()
    out: Dict[str, Dict[str, Any]] = {}
    for tab in r.json().get("tabs", []):
        body = tab.get("documentTab", {}).get("body", {}).get("content", [])
        out[tab["tabProperties"]["title"]] = {
            "id": tab["tabProperties"]["tabId"],
            # One before the body end: that last index belongs to the final
            # paragraph's newline and inserting at it is rejected.
            "end": (body[-1]["endIndex"] - 1) if body else 1,
        }
    return out


def append(doc_id: str, by_tab: Dict[str, str]) -> Dict[str, int]:
    """Append each tab's text to that tab. One batch, indices are per-tab."""
    import httpx

    head = {"Authorization": f"Bearer {_token()}"}
    known = tabs(doc_id, head)

    missing = [t for t in by_tab if t not in known]
    if missing:
        sys.exit(f"no such tab: {', '.join(missing)} — have: {', '.join(known)}")

    requests, at = [], {}
    for title, text in by_tab.items():
        at[title] = known[title]["end"]
        requests.append({"insertText": {
            "location": {"index": at[title], "tabId": known[title]["id"]},
            "text": text,
        }})

    r = httpx.post(f"{DOCS_API}/{doc_id}:batchUpdate", headers=head, timeout=60,
                   json={"requests": requests})
    r.raise_for_status()
    return at


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--publish", action="store_true", help="append to the doc")
    ap.add_argument("--promote", action="store_true", help="thread + newsletter")
    ap.add_argument("--all", action="store_true", help="ignore what was published")
    args = ap.parse_args()

    bank = load_bank()
    state = published()
    seen = [] if args.all else state["titles"]
    sections = pending(bank, seen)

    if not sections:
        print("Nothing pending — every topic in the bank is already in the doc.")
        print("Add to content/topics.json, or re-render everything with --all.")
        return 0

    version = state["version"] + 1
    today = date.today()
    count = sum(len(s["topics"]) for s in sections)

    by_tab: Dict[str, List[Dict[str, Any]]] = {}
    for section in sections:
        by_tab.setdefault(section.get("tab", "Content"), []).append(section)
    texts = {tab: render(group, version, today) for tab, group in by_tab.items()}

    chosen = pick(sections)
    if args.promote and chosen:
        print(promotion(chosen, version))
        print()

    if not args.publish:
        for tab, text in texts.items():
            print(f"=== tab: {tab} ==={text}")
        print(f"--- preview only: {count} topics into {len(texts)} tab(s).")
        print("--- run again with --publish to append to the doc.")
        return 0

    at = append(bank["doc_id"], texts)
    STATE.parent.mkdir(parents=True, exist_ok=True)
    STATE.write_text(json.dumps({
        "version": version,
        "published_at": today.isoformat(),
        "titles": seen + [t["title"] for s in sections for t in s["topics"]],
    }, indent=1))

    for tab, index in at.items():
        print(f"v{version}: appended to '{tab}' at index {index}")
    print(f"https://docs.google.com/document/d/{bank['doc_id']}/edit")
    if chosen:
        print(f"promote: {chosen['title']}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
