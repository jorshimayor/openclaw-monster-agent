"""What counts as proof that a commitment is actually done.

The rule the whole feature rests on: the word "done" closes nothing. A
commitment closes when the user hands over something inspectable — a URL, an
uploaded file, or enough pasted text that they plainly did the work.
"""

from __future__ import annotations

import re
from typing import Any, Dict, Optional

# Enough prose that it can't be "ok done" with padding, short enough that a
# tweet or a commit message still counts.
MIN_TEXT_ARTIFACT_CHARS = 40

_URL_RE = re.compile(r"https?://[^\s<>()\[\]]{4,}", re.I)

# Stripped before length-checking so "done done done done done…" can't pass.
_ACK_WORDS = re.compile(
    r"\b(done|finished|complete|completed|shipped|posted|sent|yes|yep|yeah|ok|okay|"
    r"sure|already|did it|i did|handled|sorted)\b",
    re.I,
)


def find_url(text: str) -> Optional[str]:
    m = _URL_RE.search(str(text or ""))
    return m.group(0).rstrip(".,;)") if m else None


def classify(
    text: str = "",
    file_url: Optional[str] = None,
    file_name: Optional[str] = None,
) -> Dict[str, Any]:
    """Decide whether `text`/attachment is a real artifact.

    Returns {accepted, kind, url, text, reason}. `reason` is user-facing copy
    explaining a rejection, so callers can echo it straight back to Telegram.
    """
    text = str(text or "").strip()

    if file_url or file_name:
        return {
            "accepted": True,
            "kind": "file",
            "url": file_url,
            "text": text or f"attached: {file_name or 'file'}",
            "reason": "",
        }

    url = find_url(text)
    if url:
        return {"accepted": True, "kind": "link", "url": url, "text": text, "reason": ""}

    # Substance test: drop acknowledgement filler, then measure what's left.
    substance = _ACK_WORDS.sub("", text)
    substance = re.sub(r"[^\w\s]", " ", substance)
    substance = re.sub(r"\s+", " ", substance).strip()

    if len(substance) >= MIN_TEXT_ARTIFACT_CHARS:
        return {"accepted": True, "kind": "text", "url": None, "text": text, "reason": ""}

    return {
        "accepted": False,
        "kind": None,
        "url": None,
        "text": text,
        "reason": (
            "That's not proof — it's a claim. Close it with one of:\n"
            "  • a link to the thing\n"
            "  • the file attached to this message\n"
            f"  • at least {MIN_TEXT_ARTIFACT_CHARS} characters of what you actually wrote/built"
        ),
    }
