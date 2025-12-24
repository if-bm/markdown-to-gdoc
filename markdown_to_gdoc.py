"""
Convert markdown meeting notes into a formatted Google Doc using the Google Docs API.

Designed for Google Colab (interactive auth).
"""
from __future__ import annotations

import re
from dataclasses import dataclass
from typing import List, Dict, Any, Tuple, Optional

from googleapiclient.discovery import build
from googleapiclient.errors import HttpError


MENTION_RE = re.compile(r"@\w+")


@dataclass
class Block:
    kind: str                     # h1, h2, h3, bullet, checkbox, footer, p, blank
    text: str
    level: int = 0                # bullet nesting level
    checked: bool = False         # for checkbox blocks only


def parse_markdown(md_text: str) -> List[Block]:
    """
    Minimal parser tailored to the assessment prompt.
    Supports headings, bullets, nested bullets (2-space indentation), and task checkboxes.
    """
    blocks: List[Block] = []

    for line in md_text.splitlines():
        raw = line.rstrip("\n")

        if not raw.strip():
            blocks.append(Block(kind="blank", text=""))
            continue

        if raw.startswith("# "):
            blocks.append(Block(kind="h1", text=raw[2:].strip()))
            continue

        if raw.startswith("## "):
            blocks.append(Block(kind="h2", text=raw[3:].strip()))
            continue

        if raw.startswith("### "):
            blocks.append(Block(kind="h3", text=raw[4:].strip()))
            continue

        # Checkbox items like: - [ ] task or - [x] task
        if re.match(r"^\s*-\s\[( |x|X)\]\s+", raw):
            checked = bool(re.match(r"^\s*-\s\[(x|X)\]\s+", raw))
            text = re.sub(r"^\s*-\s\[( |x|X)\]\s+", "", raw).strip()
            level = (len(raw) - len(raw.lstrip(" "))) // 2
            blocks.append(Block(kind="checkbox", text=text, level=level, checked=checked))
            continue

        # Bullets: - item or * item (with optional indentation)
        if re.match(r"^\s*[-*]\s+", raw):
            text = re.sub(r"^\s*[-*]\s+", "", raw).strip()
            level = (len(raw) - len(raw.lstrip(" "))) // 2
            blocks.append(Block(kind="bullet", text=text, level=level))
            continue

        # Treat footer lines distinctly
        if raw.startswith("Meeting recorded by:") or raw.startswith("Duration:"):
            blocks.append(Block(kind="footer", text=raw.strip()))
            continue

        # Horizontal rule --- becomes a blank spacer line (simple + acceptable)
        if raw.strip() == "---":
            blocks.append(Block(kind="blank", text=""))
            continue

        blocks.append(Block(kind="p", text=raw.strip()))

    return blocks


def _paragraph_style_request(start: int, end: int, named_style_type: str | None = None, indent_pt: int | None = None) -> Dict[str, Any]:
    style: Dict[str, Any] = {}
    fields: List[str] = []

    if named_style_type:
        style["namedStyleType"] = named_style_type
        fields.append("namedStyleType")

    if indent_pt is not None:
        style["indentStart"] = {"magnitude": indent_pt, "unit": "PT"}
        fields.append("indentStart")

    return {
        "updateParagraphStyle": {
            "range": {"startIndex": start, "endIndex": end},
            "paragraphStyle": style,
            "fields": ",".join(fields),
        }
    }


def _text_style_request(start: int, end: int, *, bold: Optional[bool] = None, italic: Optional[bool] = None,
                        font_size_pt: Optional[int] = None, rgb: Optional[Dict[str, float]] = None) -> Dict[str, Any]:
    style: Dict[str, Any] = {}
    fields: List[str] = []

    if bold is not None:
        style["bold"] = bold
        fields.append("bold")

    if italic is not None:
        style["italic"] = italic
        fields.append("italic")

    if font_size_pt is not None:
        style["fontSize"] = {"magnitude": font_size_pt, "unit": "PT"}
        fields.append("fontSize")

    if rgb is not None:
        style["foregroundColor"] = {"color": {"rgbColor": rgb}}
        fields.append("foregroundColor")

    return {
        "updateTextStyle": {
            "range": {"startIndex": start, "endIndex": end},
            "textStyle": style,
            "fields": ",".join(fields),
        }
    }


def markdown_to_google_doc(md_text: str, *, title: str = "Product Team Sync (Generated)") -> Tuple[str, str]:
    """
    Creates a Google Doc and formats it according to the assessment requirements.

    Returns:
        (document_id, document_url)
    """
    # Build Docs service (expects Colab auth to already be done)
    docs_service = build("docs", "v1")

    # Create a new doc
    doc = docs_service.documents().create(body={"title": title}).execute()
    doc_id = doc["documentId"]
    doc_url = f"https://docs.google.com/document/d/{doc_id}/edit"

    blocks = parse_markdown(md_text)

    # Build plain text + keep paragraph index ranges for formatting.
    # Docs documents usually have an initial newline; insert at index 1.
    cursor = 1
    text_parts: List[str] = []
    spans: List[Dict[str, Any]] = []

    for b in blocks:
        start = cursor
        line = b.text
        text_parts.append(line + "\n")
        cursor += len(line) + 1
        end = cursor
        spans.append({"block": b, "start": start, "end": end})

    full_text = "".join(text_parts)

    requests: List[Dict[str, Any]] = []
    requests.append({"insertText": {"location": {"index": 1}, "text": full_text}})

    # Apply heading and footer styles
    for s in spans:
        b: Block = s["block"]
        start, end = s["start"], s["end"]

        if b.kind == "h1":
            requests.append(_paragraph_style_request(start, end, named_style_type="HEADING_1"))
        elif b.kind == "h2":
            requests.append(_paragraph_style_request(start, end, named_style_type="HEADING_2"))
        elif b.kind == "h3":
            requests.append(_paragraph_style_request(start, end, named_style_type="HEADING_3"))
        elif b.kind == "footer":
            # distinct style: smaller + italic + gray
            requests.append(_text_style_request(
                start, end, italic=True, font_size_pt=10,
                rgb={"red": 0.4, "green": 0.4, "blue": 0.4},
            ))

    # Bullets + checkbox bullets
    for s in spans:
        b: Block = s["block"]
        start, end = s["start"], s["end"]

        if b.kind == "bullet":
            requests.append({
                "createParagraphBullets": {
                    "range": {"startIndex": start, "endIndex": end},
                    "bulletPreset": "BULLET_DISC_CIRCLE_SQUARE",
                }
            })
            if b.level > 0:
                requests.append(_paragraph_style_request(start, end, indent_pt=18 * b.level))

        elif b.kind == "checkbox":
            # Unchecked and checked items use the same checkbox bullet preset.
            # The Docs API does not set checked-state per item here; it renders a checklist.
            requests.append({
                "createParagraphBullets": {
                    "range": {"startIndex": start, "endIndex": end},
                    "bulletPreset": "BULLET_CHECKBOX",
                }
            })
            if b.level > 0:
                requests.append(_paragraph_style_request(start, end, indent_pt=18 * b.level))

    # Style @mentions
    for s in spans:
        b: Block = s["block"]
        if not b.text:
            continue
        for m in MENTION_RE.finditer(b.text):
            a = s["start"] + m.start()
            z = s["start"] + m.end()
            requests.append(_text_style_request(a, z, bold=True))

    try:
        docs_service.documents().batchUpdate(documentId=doc_id, body={"requests": requests}).execute()
    except HttpError as e:
        # Surface a helpful message for troubleshooting
        raise RuntimeError(f"Google API error: {e}") from e

    return doc_id, doc_url


def read_text_file(path: str) -> str:
    with open(path, "r", encoding="utf-8") as f:
        return f.read()


if __name__ == "__main__":
    # Example local run (in Colab, you usually call markdown_to_google_doc from the notebook)
    import sys
    md_path = sys.argv[1] if len(sys.argv) > 1 else "meeting_notes.md"
    md = read_text_file(md_path)
    doc_id, url = markdown_to_google_doc(md)
    print("Created document:", url)
