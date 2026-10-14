"""Download the files (videos, PDFs) that last year's Notion pages hold, compress videos, and record them.

Scans site/content/book.json and site/content/notion/week-*.json for [[FILE name|block-id]] markers.
Videos are re-encoded (720p, 24fps, H.264 CRF 28, mono AAC 64k — as on the statistics site) to files/notion/.
Writes site/content/files.json: {block-id: {"path": "files/notion/<name>", "label": "<name>"}}.
Files already listed (and present) are skipped.

Usage: python tools/notion_files.py
"""
import json
import re
import subprocess
import tempfile
import urllib.request
from pathlib import Path

import notion_export as ne

ROOT = Path(__file__).resolve().parent.parent
CONTENT = ROOT / "site" / "content"
OUT = ROOT / "files" / "notion"
MAP = CONTENT / "files.json"
API = "https://relic-collarbone-9bf.notion.site/api/v3/getSignedFileUrls"
MARK = re.compile(r"\[\[FILE (.*?)\|([0-9a-f-]{36})\]\]")


def markers():
    found = {}
    for f in [CONTENT / "book.json", *sorted((CONTENT / "notion").glob("week-*.json"))]:
        for name, fid in MARK.findall(f.read_text(encoding="utf-8")):
            found.setdefault(fid, name.strip())
    return found


def signed(fid):
    ne.fetch([fid])
    b = ne.blocks[fid]
    src = b["properties"]["source"][0][0]
    body = {"urls": [{"url": src, "permissionRecord": {"table": "block", "id": fid, "spaceId": b.get("space_id")}}]}
    req = urllib.request.Request(API, data=json.dumps(body).encode(),
                                 headers={"content-type": "application/json", "user-agent": "Mozilla/5.0"})
    return json.loads(urllib.request.urlopen(req, timeout=60).read())["signedUrls"][0], src


def safe(name, fid):
    stem = re.sub(r"[^\w֐-׿.-]+", "-", name).strip("-") or "file"
    return f"{fid[:8]}-{stem}"


def main():
    OUT.mkdir(parents=True, exist_ok=True)
    done = json.loads(MAP.read_text(encoding="utf-8")) if MAP.exists() else {}
    for fid, name in markers().items():
        if fid in done and (ROOT / done[fid]["path"]).exists():
            continue
        try:
            url, src = signed(fid)
        except Exception as e:  # missing or empty file block
            print("skip", name or "(no name)", fid, e)
            continue
        ext = Path(src.split("?")[0]).suffix.lower() or Path(name).suffix.lower()
        label = re.sub(r"\.(mp4|mov|m4v|pdf)$", "", name, flags=re.I) or "סרטון"
        with tempfile.TemporaryDirectory() as tmp:
            raw = Path(tmp) / ("in" + ext)
            req = urllib.request.Request(url, headers={"user-agent": "Mozilla/5.0"})
            raw.write_bytes(urllib.request.urlopen(req, timeout=300).read())
            if ext in (".mp4", ".mov", ".m4v"):
                dest = OUT / (safe(Path(name).stem or "video", fid) + ".mp4")
                subprocess.run(["ffmpeg", "-y", "-loglevel", "error", "-i", str(raw),
                                "-vf", "scale=-2:'min(720,ih)'", "-r", "24", "-c:v", "libx264", "-preset", "medium",
                                "-crf", "28", "-c:a", "aac", "-ac", "1", "-b:a", "64k", "-movflags", "+faststart",
                                str(dest)], check=True)
                if dest.stat().st_size > raw.stat().st_size * 0.85:  # not worth it: keep the original
                    dest.write_bytes(raw.read_bytes())
            else:
                dest = OUT / safe(name or ("file" + ext), fid)
                dest.write_bytes(raw.read_bytes())
        done[fid] = {"path": dest.relative_to(ROOT).as_posix(), "label": label}
        print(f"{dest.stat().st_size / 1e6:6.2f} MB  {dest.name}")
        MAP.write_text(json.dumps(done, ensure_ascii=False, indent=1), encoding="utf-8")


if __name__ == "__main__":
    main()
