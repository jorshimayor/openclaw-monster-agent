#!/usr/bin/env python3
"""The content doc, generated from content/doc/*.json.

    python3 content/publish_doc.py                 # preview, writes nothing
    python3 content/publish_doc.py --check         # duplicates and empty fields
    python3 content/publish_doc.py --rewrite       # replace every tab
    python3 content/publish_doc.py --promote "..." # thread + newsletter for a piece

One source of truth. Each file under content/doc/ is one tab; editing a file
and re-running --rewrite is the whole update loop. That is why this replaces
rather than appends: an append-only doc drifts away from its source until
nobody trusts either.

Two things that will bite whoever touches this next.

The document is TABS, not headings. documents.get returns only the first tab's
body unless you pass includeTabsContent, so "the end of the document" silently
means "the end of tab one" — which is where a whole topic bank once landed.
Every read here passes the parameter and every write names a tabId.

Tabs are matched by title. The API gives no way to create one, so a new tab has
to be added in the Google Docs UI first; --check will tell you which are
missing rather than silently dropping their content.
"""

from __future__ import annotations

import argparse
import json
import os
import re
import sys
from collections import Counter
from pathlib import Path
from typing import Any, Dict, List

HERE = Path(__file__).resolve().parent
SOURCE = HERE / "doc"
DOC_ID = "165XuUvubLFk3sAaB7QznrWK8frRnqHQ0ucYP2zJFY9w"

DOCS_API = "https://docs.googleapis.com/v1/documents"
TOKEN_URL = "https://oauth2.googleapis.com/token"


def load() -> List[Dict[str, Any]]:
    """Tab specs in filename order — the numeric prefix is the tab order."""
    specs = []
    for path in sorted(SOURCE.glob("*.json")):
        specs.append(json.loads(path.read_text()))
    if not specs:
        sys.exit(f"no tab sources in {SOURCE}")
    return specs


def _key(title: str) -> str:
    return re.sub(r"[^a-z0-9]+", " ", title.lower()).strip()


def check(specs: List[Dict[str, Any]]) -> int:
    """Duplicates across the whole doc, and entries missing a description."""
    seen: Dict[str, List[str]] = {}
    thin: List[str] = []
    for spec in specs:
        for group in spec["groups"]:
            for item in group["items"]:
                seen.setdefault(_key(item["t"]), []).append(spec["tab"])
                if len(item.get("d", "").strip()) < 25:
                    thin.append(f'{spec["tab"]}: {item["t"]}')

    dupes = {k: v for k, v in seen.items() if len(v) > 1}
    total = sum(len(v) for v in seen.values())
    print(f"{total} items, {len(seen)} unique titles")

    if dupes:
        print(f"\n{len(dupes)} repeated title(s):")
        for k, where in dupes.items():
            print(f"   {k[:60]:<62} {', '.join(where)}")
    else:
        print("no repeated titles")

    if thin:
        print(f"\n{len(thin)} without a real description:")
        for t in thin[:20]:
            print("   ", t)
    return 1 if (dupes or thin) else 0


def render(spec: Dict[str, Any]) -> str:
    """One tab, as plain text. The doc styles headings itself."""
    out = [spec["tab"].upper(), "", spec["intro"], ""]
    for group in spec["groups"]:
        out += ["", group["title"], ""]
        if group.get("note"):
            out += [group["note"], ""]
        for n, item in enumerate(group["items"], start=1):
            out.append(f"{n}. {item['t']}")
            out.append(f"    {item['d']}")
            out.append("")
        for link in group.get("links", []):
            out.append(f"    {link}")
        if group.get("links"):
            out.append("")
    return "\n".join(out)


def promotion(title: str, specs: List[Dict[str, Any]]) -> str:
    """Thread and newsletter structure for one piece.

    Structure, not copy. docs/writing-standard.md refuses generated prose and
    a generated thread reads exactly like a generated thread — which is the
    opposite of the thing you are trying to prove by writing at all.
    """
    found = None
    for spec in specs:
        for group in spec["groups"]:
            for item in group["items"]:
                if _key(title) in _key(item["t"]):
                    found = (spec["tab"], group["title"], item)
    if not found:
        return f"No topic matching {title!r}. Run --check to list what is there."

    tab, group, item = found
    return "\n".join([
        f"PROMOTION — {item['t']}",
        f"{tab}  ·  {group}",
        "",
        item["d"],
        "",
        "X THREAD",
        "  1. Open with the finding, not with 'a thread'. The number or the",
        "     surprise. If post one is not interesting alone, the rest is unread.",
        "  2. One claim per post — the claim you could not have made before",
        "     doing the work.",
        "  3. The counter-intuitive one: what you expected, what happened.",
        "     This is the post that gets quoted.",
        "  4. The method, briefly, so someone could check it.",
        "  5. Last post links the article. Nothing else, no 'follow for more'.",
        "",
        "NEWSLETTER",
        "  Subject: the finding in under nine words. No colon-subtitle.",
        "  Intro:   the one sentence that makes someone open the article.",
        "  Body:    what you learned that you did not expect, then the link.",
        "           One link.",
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


def tabs(head: Dict[str, str]) -> Dict[str, Dict[str, Any]]:
    """{title: {id, start, end}} for every tab. includeTabsContent is not optional."""
    import httpx

    r = httpx.get(f"{DOCS_API}/{DOC_ID}", headers=head, timeout=60,
                  params={"includeTabsContent": "true"})
    r.raise_for_status()
    out = {}
    for tab in r.json().get("tabs", []):
        body = tab.get("documentTab", {}).get("body", {}).get("content", [])
        # Content begins after the leading sectionBreak, and the body's very
        # last newline cannot be deleted — hence start=1 and end-1.
        out[tab["tabProperties"]["title"]] = {
            "id": tab["tabProperties"]["tabId"],
            "start": 1,
            "end": (body[-1]["endIndex"] - 1) if body else 1,
        }
    return out


def rewrite(specs: List[Dict[str, Any]]) -> None:
    """Replace each tab's body with its rendered source.

    Delete and insert are issued per tab as separate batches. Batching them
    together would be one round trip, but the indices of a later request are
    computed against the document as the earlier ones left it, and getting
    that wrong corrupts rather than fails.
    """
    import httpx

    head = {"Authorization": f"Bearer {_token()}"}
    known = tabs(head)

    missing = [s["tab"] for s in specs if s["tab"] not in known]
    if missing:
        sys.exit("no such tab (create it in Google Docs first): " + ", ".join(missing))

    for spec in specs:
        tab = known[spec["tab"]]
        text = render(spec)
        requests: List[Dict[str, Any]] = []
        if tab["end"] > tab["start"]:
            requests.append({"deleteContentRange": {"range": {
                "tabId": tab["id"], "startIndex": tab["start"], "endIndex": tab["end"]}}})
        requests.append({"insertText": {
            "location": {"index": tab["start"], "tabId": tab["id"]}, "text": text}})

        r = httpx.post(f"{DOCS_API}/{DOC_ID}:batchUpdate", headers=head, timeout=60,
                       json={"requests": requests})
        r.raise_for_status()
        items = sum(len(g["items"]) for g in spec["groups"])
        print(f"  {spec['tab']:<24} replaced, {items:>3} items, {len(text):>6} chars")


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--check", action="store_true")
    ap.add_argument("--rewrite", action="store_true")
    ap.add_argument("--promote", metavar="TITLE")
    args = ap.parse_args()

    specs = load()

    if args.promote:
        print(promotion(args.promote, specs))
        return 0
    if args.check:
        return check(specs)
    if args.rewrite:
        rewrite(specs)
        print(f"\nhttps://docs.google.com/document/d/{DOC_ID}/edit")
        return 0

    for spec in specs:
        print(render(spec))
        print("\n" + "=" * 70 + "\n")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
