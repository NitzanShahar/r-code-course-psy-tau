"""Export last year's Notion week pages (R track only) to site/content/notion/week-N.json.

Each file holds the raw material a week page is written from:
  intro (lines), deck (url), topics (lines), r_units [{"group", "units": [title]}],
  hw (lines, "  " per nesting level), solutions [{"id", "title"}], files [{"name", "id"}].
Python and MATLAB toggles are skipped.

Usage: python tools/notion_weeks.py
"""
import json
import re
from pathlib import Path

import notion_export as ne

OUT = Path(__file__).resolve().parent.parent / "site" / "content" / "notion"

WEEKS = {
    1: "244dccfe-d059-8012-a05c-fbd15972ca00",
    2: "244dccfe-d059-8012-8697-c51ef65b8c6a",
    3: "244dccfe-d059-80dc-9f0d-e0786e52875a",
    4: "244dccfe-d059-80c3-988a-f5dee5f2fdae",
    5: "244dccfe-d059-8030-ab25-c3dc67d89fc3",
    6: "244dccfe-d059-806c-be49-d248531a7bd7",
    7: "244dccfe-d059-8014-92b5-f7c986b05e45",
    8: "244dccfe-d059-80bf-ae2b-f6596b08b529",
    9: "244dccfe-d059-805c-b119-e948da6bbcb2",
    10: "244dccfe-d059-80c9-a17d-c67802e6cf05",
    11: "2e2dccfe-d059-802f-9bc3-f2e9d0172e1b",
    12: "2ecdccfe-d059-805e-931e-cde16369020e",
}


def title(b):
    return ne.rich(b.get("properties", {}).get("title")).strip()


def kids(i):
    b = ne.blocks[i]
    if b["type"] == "page":
        return []
    ne.fetch(b.get("content", []))
    return [x for k in b.get("content", []) for x in ne.flat(k)]


def lines(i, depth=0):
    """Text lines of a block subtree; nested list items are indented."""
    out = []
    for j in ne.flat(i):
        b = ne.blocks[j]
        t = title(b)
        if b["type"] == "page":
            continue
        if b["type"] in ("file", "video", "pdf"):
            t = f"[[FILE {t}|{j}]]"
        elif b["type"] == "bulleted_list":
            t = "- " + t
        elif b["type"] == "numbered_list":
            t = "1. " + t
        elif b["type"] == "code":
            t = "```\n" + t + "\n```"
        out.append("  " * depth + t)
        for k in kids(j):
            out += lines(k, depth + (1 if b["type"] in ("bulleted_list", "numbered_list") else 0))
    return out


def files_in(i, acc):
    for j in ne.flat(i):
        b = ne.blocks[j]
        if b["type"] in ("file", "video", "pdf"):
            acc.append({"name": title(b), "id": j, "type": b["type"]})
        if b["type"] != "page":
            for k in kids(j):
                files_in(k, acc)
    return acc


def week(n, pid):
    ne.fetch([pid])
    page = ne.blocks[pid]
    ne.fetch(page.get("content", []))
    top = [x for k in page.get("content", []) for x in ne.flat(k)]
    data = {"n": n, "title": title(page), "intro": [], "deck": [], "topics": [], "r_units": [], "hw": [],
            "solutions": [], "files": [], "other": []}
    mode = None
    for i in top:
        b = ne.blocks[i]
        t = title(b)
        if b["type"] == "page":
            data["solutions"].append({"id": i, "title": t})
            continue
        if "header" in b["type"]:
            if "יחידות לימוד R" in t or t.strip("‣ ").startswith("יחידות לימוד R"):
                mode = "r"
                group = None
                for k in kids(i):
                    for j in [k] + kids(k):
                        bb = ne.blocks[j]
                        tt = title(bb).replace("**", "").strip()
                        if "header" not in bb["type"] or not tt:
                            continue
                        if re.match(r"^(\d+\.|📘)", tt):
                            group = {"group": re.sub(r"^(\d+\.\s*|📘\s*)", "", tt).rstrip(":").strip(), "units": []}
                            data["r_units"].append(group)
                        else:
                            if group is None:
                                group = {"group": "", "units": []}
                                data["r_units"].append(group)
                            group["units"].append(tt)
                files_in(i, data["files"])
                continue
            if "פייתון" in t or "מאטלאב" in t or "matlab" in t.lower() or "python" in t.lower():
                mode = "skip"
                continue
            if "המטלה השבועית" in t:
                mode = "hw"
                continue
            if "יחידות הלימוד" in t:
                mode = None
                continue
        if mode == "skip":
            continue
        txt = lines(i)
        joined = "\n".join(txt)
        if mode == "hw":
            data["hw"] += txt
        elif "חומר הלימוד" in joined and not data["intro"]:
            data["intro"] = txt
            data["deck"] = re.findall(r"https://docs\.google\.com/presentation/[^)\s]+", joined)
        elif "רשימת חומרי הלימוד" in joined:
            data["topics"] = txt
        else:
            data["other"] += txt
    return data


if __name__ == "__main__":
    OUT.mkdir(parents=True, exist_ok=True)
    for n, pid in WEEKS.items():
        d = week(n, pid)
        (OUT / f"week-{n}.json").write_text(json.dumps(d, ensure_ascii=False, indent=1), encoding="utf-8")
        print(n, d["title"], "| units:", sum(len(g["units"]) for g in d["r_units"]), "| hw lines:", len(d["hw"]),
              "| solutions:", len(d["solutions"]), "| files:", len(d["files"]), "| other:", len(d["other"]))
