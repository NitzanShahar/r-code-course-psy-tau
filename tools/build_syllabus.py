"""Build the detailed syllabus PDF from site/syllabus.html and site/site.json.

The schedule (weeks, Sunday dates, the Hanukkah break, due dates) and the number of assignments come from
site.json and the week files, so the PDF always matches the site. Printed with headless Edge/Chrome.

Usage: python tools/build_syllabus.py   ->  files/admin/syllabus-detailed.pdf
"""
import html
import json
import subprocess
import sys
import tempfile
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
SITE = ROOT / "site"
PORT = 8799
BROWSERS = [r"C:\Program Files\Google\Chrome\Application\chrome.exe",
            r"C:\Program Files (x86)\Microsoft\Edge\Application\msedge.exe"]


def main():
    cfg = json.loads((SITE / "site.json").read_text(encoding="utf-8"))
    weeks = cfg["weeks"]
    hw = {}
    for w in weeks:
        f = SITE / "content" / "weeks" / f"week-{w['n']}.json"
        if f.exists():
            d = json.loads(f.read_text(encoding="utf-8"))
            hw[w["n"]] = bool(d.get("hw", {}).get("title"))
    # the syllabus lists one assignment per week with a topic (the user: 12), even where the site has none yet (week 7)
    if cfg.get("syllabus_all_weeks_hw"):
        hw = {w["n"]: True for w in weeks if w["title"]}
    rows = []
    for i, w in enumerate(weeks):
        nxt = weeks[i + 1]["date"] if i + 1 < len(weeks) else ""
        due = f'<span class="ltr">{".".join(nxt.split(".")[:2])} · 12:00</span>' if hw.get(w["n"]) and nxt else "—"
        if w["title"]:
            rows.append(f'<tr><td class="n">{w["n"]}</td><td class="d">{w["date"]}</td><td>{html.escape(w["title"])}</td><td class="hw">{due}</td></tr>')
        else:
            rows.append(f'<tr class="empty"><td class="n">{w["n"]}</td><td class="d">{w["date"]}</td><td>—</td><td class="hw">—</td></tr>')
        for b in cfg.get("breaks", []):
            if b["after"] == w["n"]:
                rows.append(f'<tr class="brk"><td class="n"></td><td class="d">{b["date"]}</td><td>{html.escape(b["label"])} — אין מפגש</td><td class="hw"></td></tr>')
    n_hw = sum(hw.values())
    page = (SITE / "syllabus.html").read_text(encoding="utf-8")
    page = (page.replace("{schedule}", "\n".join(rows))
                .replace("{n_hw}", str(n_hw))
                .replace("{n_full}", str(n_hw - 2))
                .replace("{tas}", html.escape(cfg.get("syllabus_tas", "")))
                .replace("{logo}", "img/tau-logo.png"))
    tmp = ROOT / "site" / "_syllabus_print.html"
    tmp.write_text(page, encoding="utf-8")
    out = ROOT / "files" / "admin" / "syllabus-detailed.pdf"  # linked from the course-admin page
    browser = next(b for b in BROWSERS if Path(b).exists())
    # served over http (file:// paths with spaces fail in headless Chrome); a separate profile so a running browser
    # doesn't take the job
    server = subprocess.Popen([sys.executable, "-m", "http.server", str(PORT), "--bind", "127.0.0.1"], cwd=SITE,
                              stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
    try:
        time.sleep(1.5)
        with tempfile.TemporaryDirectory() as profile:
            pdf = Path(profile) / "out.pdf"
            subprocess.run([browser, "--headless=new", "--disable-gpu", "--no-pdf-header-footer", f"--user-data-dir={profile}",
                            "--virtual-time-budget=8000", f"--print-to-pdf={pdf}", f"http://127.0.0.1:{PORT}/{tmp.name}"],
                           capture_output=True, timeout=120)
            out.write_bytes(pdf.read_bytes())
    finally:
        server.terminate()
    tmp.unlink()
    print(out, f"{out.stat().st_size / 1e3:.0f} KB", f"| assignments: {n_hw}")


if __name__ == "__main__":
    main()
