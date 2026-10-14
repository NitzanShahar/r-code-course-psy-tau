"""Export last year's Notion course pages (public notion.site) to JSON.

Reads the "book" chapters (R + general coding) into site/content/book.json:
  [{"id", "group": "r"|"code", "title", "secs": [{"h", "items": [{"kind", "text"}]}]}]
kind: prompt (AI-tutor prompt, 🗨️), video (📽️), ref (🔎), or another block type.

Usage: python tools/notion_export.py
"""
import json
import time
import urllib.request
from pathlib import Path

API = "https://relic-collarbone-9bf.notion.site/api/v3/syncRecordValuesMain"
OUT = Path(__file__).resolve().parent.parent / "site" / "content" / "book.json"

# chapter pages, in book order
PAGES = [
    ("r", "1d0dccfe-d059-8181-b251-eab3c1a9ab4b"),  # עבודה עם ממשק R ו-RStudio
    ("r", "1d0dccfe-d059-819c-bf22-dec2f330e18c"),  # אובייקטים בסיסיים
    ("r", "1d0dccfe-d059-8142-a090-fde064c7130a"),  # מטריצות ווקטורים
    ("r", "1d0dccfe-d059-8178-b243-ffc34a0c2b1e"),  # מבנה נתונים וסטטיסטיקה תיאורית
    ("r", "1d0dccfe-d059-8117-b762-c477f44ed3c2"),  # דגימה מהתפלגויות
    ("r", "1d0dccfe-d059-8128-9360-c8eb33f584cc"),  # גרפיקה
    ("r", "1d0dccfe-d059-8104-9cc4-db9a4671152d"),  # מבחני ANOVA
    ("r", "1d0dccfe-d059-81c8-b063-e823436c06dc"),  # רגרסיה שכיחותנית
    ("r", "1d0dccfe-d059-8175-b194-c8ebfc61ea95"),  # בקרת זרימה
    ("r", "1d0dccfe-d059-8161-b43a-d06d0cf99202"),  # פונקציות ו-debugging
    ("code", "26fdccfe-d059-80a7-b524-f7f2a63a580d"),  # קווים מנחים בכתיבת קוד
    ("code", "1d0dccfe-d059-8199-8dc0-eb0a90473ea5"),  # ניהול גרסאות
]

blocks = {}


def fetch(ids):
    ids = [i for i in ids if i not in blocks]
    for k in range(0, len(ids), 80):
        body = {"requests": [{"pointer": {"table": "block", "id": i}, "version": -1} for i in ids[k:k + 80]]}
        req = urllib.request.Request(API, data=json.dumps(body).encode(),
                                     headers={"content-type": "application/json", "user-agent": "Mozilla/5.0"})
        rec = json.loads(urllib.request.urlopen(req, timeout=60).read())["recordMap"].get("block", {})
        for i, v in rec.items():
            v = v.get("value", {})
            blocks[i] = v.get("value", v)
        time.sleep(0.2)


def rich(prop):
    out = []
    for seg in prop or []:
        t, marks = seg[0], (seg[1] if len(seg) > 1 else [])
        s = t
        for m in marks:
            if m[0] == "a":
                s = t if t == m[1] else f"[{t}]({m[1]})"
            elif m[0] == "c":
                s = f"`{s}`"
        out.append(s)
    return "".join(out)


def flat(i):
    """Resolve synced blocks to the ids of the real blocks they show."""
    fetch([i])
    b = blocks.get(i)
    if not b:
        return []
    if b["type"] == "transclusion_reference":
        src = b.get("format", {}).get("transclusion_reference_pointer", {}).get("id")
        return flat(src) if src else []
    if b["type"] == "transclusion_container":
        fetch(b.get("content", []))
        return [x for k in b.get("content", []) for x in flat(k)]
    return [i]


def text(i):
    lines = []
    for j in flat(i):
        b = blocks[j]
        t, ty = rich(b.get("properties", {}).get("title")), b["type"]
        if ty == "code":
            lines.append("```\n" + t + "\n```")
        elif ty in ("file", "video"):
            lines.append(f"[[FILE {t}]]")
        elif ty == "bookmark":
            link = b.get("properties", {}).get("link", [[""]])[0][0]
            lines.append(f"[{t or link}]({link})" if t and t != link else link)
        elif ty == "bulleted_list":
            lines.append("- " + t)
        elif ty == "numbered_list":
            lines.append("1. " + t)
        elif ty == "page":
            lines.append(f"[[PAGE {t}]]")
        else:
            lines.append(t)
        if ty != "page" and b.get("content"):
            fetch(b["content"])
            lines += [text(k) for k in b["content"]]
    return "\n".join(lines)


def kind_of(b):
    if b["type"] != "callout":
        return b["type"]
    icon = b.get("format", {}).get("page_icon", "")
    for k, marks in (("prompt", "🗨💬"), ("video", "📽🎥"), ("ref", "🔎")):
        if icon and icon[0] in marks:
            return k
    return "callout:" + icon


def item(i):
    b = blocks[i]
    if b["type"] == "callout":
        body = [rich(b.get("properties", {}).get("title"))]
        fetch(b.get("content", []))
        body += [text(k) for k in b.get("content", [])]
        t = "\n".join(body)
    else:
        t = text(i)
    return {"kind": kind_of(b), "text": t.strip()}


def chapter(group, pid):
    fetch([pid])
    page = blocks[pid]
    fetch(page.get("content", []))
    top = [x for k in page.get("content", []) for x in flat(k)]
    secs, cur = [], None
    for i in top:
        b = blocks[i]
        if "header" in b["type"]:
            cur = {"h": rich(b.get("properties", {}).get("title")).replace("**", "").strip(), "items": []}
            secs.append(cur)
            kids = b.get("content", [])
            fetch(kids)
            cur["items"] += [item(x) for k in kids for x in flat(k)]
            continue
        if cur is None:
            cur = {"h": "", "items": []}
            secs.append(cur)
        cur["items"].append(item(i))
    for s in secs:
        s["items"] = [it for it in s["items"] if it["text"]]
    secs = [s for s in secs if s["h"] or s["items"]]
    return {"id": pid, "group": group, "title": rich(page["properties"]["title"]).strip(), "secs": secs}


if __name__ == "__main__":
    book = [chapter(g, p) for g, p in PAGES]
    OUT.parent.mkdir(parents=True, exist_ok=True)
    OUT.write_text(json.dumps(book, ensure_ascii=False, indent=1), encoding="utf-8")
    for c in book:
        print(c["title"], len(c["secs"]))
