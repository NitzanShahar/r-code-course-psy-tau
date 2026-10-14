"""Add the R solution of each week to site/content/notion/week-N.json (key "solution_r": [code, ...]).

The Notion solutions pages hold one code block per language; only the R blocks are kept.
Run after tools/notion_weeks.py.

Usage: python tools/notion_solutions.py
"""
import json
from pathlib import Path

import notion_export as ne
import notion_weeks as nw

DIR = Path(__file__).resolve().parent.parent / "site" / "content" / "notion"


def r_code(i, acc):
    for j in ne.flat(i):
        b = ne.blocks[j]
        if b["type"] == "code":
            lang = (b.get("properties", {}).get("language") or [[""]])[0][0]
            if lang.strip().lower() == "r":
                acc.append(ne.rich(b["properties"].get("title")))
        elif b["type"] != "page":
            for k in nw.kids(j):
                r_code(k, acc)
    return acc


if __name__ == "__main__":
    for f in sorted(DIR.glob("week-*.json"), key=lambda p: int(p.stem.split("-")[1])):
        d = json.loads(f.read_text(encoding="utf-8"))
        code = []
        for s in d.get("solutions", []):
            ne.fetch([s["id"]])
            for k in ne.blocks[s["id"]].get("content", []):
                r_code(k, code)
        d["solution_r"] = code
        f.write_text(json.dumps(d, ensure_ascii=False, indent=1), encoding="utf-8")
        print(f.stem, len(code), "R blocks", sum(len(c) for c in code), "chars")
