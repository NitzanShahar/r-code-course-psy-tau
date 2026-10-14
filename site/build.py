"""Build the course site (GitHub Pages, served from the repo root).

Sources (edit these): site/site.json, site/site.css, site/img/, site/content/book.json, site/content/weeks/week-N.json
Output (do not edit by hand):
  index.html                  public site: title only while "published" is empty, otherwise the published weeks
  <staff_dir>/index.html …    staff ("מתרגלים") site: every week that has content + the book of units
  assets/                     css and images, shared by both

Usage: python site/build.py
"""
import html
import json
import re
import shutil
import urllib.parse
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
SRC = ROOT / "site"
CFG = json.loads((SRC / "site.json").read_text(encoding="utf-8"))
FONTS = ("https://fonts.googleapis.com/css2?family=Assistant:wght@400;500;600;700"
         "&family=Frank+Ruhl+Libre:wght@500;700;900&family=JetBrains+Mono:wght@400;600&display=swap")

ICON = {
    "deck": '<svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.8" stroke-linecap="round" stroke-linejoin="round"><rect x="3" y="4" width="18" height="12" rx="2"/><path d="M8 20h8M12 16v4"/></svg>',
    "play": '<svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.8" stroke-linecap="round" stroke-linejoin="round"><rect x="3" y="5" width="18" height="14" rx="3"/><path d="M10 9.5v5l4.5-2.5z" fill="currentColor"/></svg>',
    "book": '<svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.8" stroke-linecap="round" stroke-linejoin="round"><path d="M4 5.5A2.5 2.5 0 0 1 6.5 3H20v15H6.5A2.5 2.5 0 0 0 4 20.5z"/><path d="M4 20.5A2.5 2.5 0 0 0 6.5 23H20v-5"/></svg>',
    "chat": '<svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.8" stroke-linecap="round" stroke-linejoin="round"><path d="M4 5h16v11H9l-5 4z"/></svg>',
    "link": '<svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.8" stroke-linecap="round" stroke-linejoin="round"><path d="M10 14a4 4 0 0 0 5.7 0l3-3a4 4 0 0 0-5.7-5.7l-1 1"/><path d="M14 10a4 4 0 0 0-5.7 0l-3 3a4 4 0 0 0 5.7 5.7l1-1"/></svg>',
    "copy": '<svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.8" stroke-linecap="round" stroke-linejoin="round"><rect x="8" y="8" width="12" height="12" rx="2"/><path d="M16 8V5a1 1 0 0 0-1-1H5a1 1 0 0 0-1 1v10a1 1 0 0 0 1 1h3"/></svg>',
    "clock": '<svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.8" stroke-linecap="round"><circle cx="12" cy="12" r="9"/><path d="M12 7v5l3 2"/></svg>',
    "spark": '<svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.8" stroke-linecap="round" stroke-linejoin="round"><path d="M12 3l1.8 5.2L19 10l-5.2 1.8L12 17l-1.8-5.2L5 10l5.2-1.8z"/></svg>',
}

esc = html.escape


# ---------- content ----------

def fix(s):
    for a, b in CFG.get("book_replace", []):
        s = s.replace(a, b)
    return s


def load_book():
    raw = json.loads((SRC / "content" / "book.json").read_text(encoding="utf-8"))
    drop = set(CFG.get("book_drop_sections", []))
    names = CFG.get("book_chapter_titles", {})
    book = []
    for n, c in enumerate(raw, 1):
        secs = [s for s in c["secs"] if s["h"] and s["h"] not in drop]
        book.append({"n": n, "group": c["group"], "title": names.get(c["title"], c["title"]), "secs": secs})
    return book


def load_files():
    f = SRC / "content" / "files.json"
    return json.loads(f.read_text(encoding="utf-8")) if f.exists() else {}


FILES = load_files()
DEPTH = [0]  # depth of the page being built (for links to files/)


def short_date(d):
    """'18.10.2026' -> '18.10'"""
    return ".".join(d.split(".")[:2]) if d else ""


def load_weeks():
    out = {}
    for w in CFG["weeks"]:
        f = SRC / "content" / "weeks" / f"week-{w['n']}.json"
        if f.exists():
            out[w["n"]] = json.loads(f.read_text(encoding="utf-8"))
    return out


# ---------- text helpers ----------

LINK = re.compile(r"\[([^\]]*)\]\(([^)\s]+)\)|(https?://[^\s<>()\]]+[^\s<>()\].,;:!?'\"])")


def inline(s):
    """Escape text and turn markdown links, bare URLs, `code` and **bold** into HTML."""
    out, pos = [], 0
    for m in LINK.finditer(s):
        out.append(_marks(esc(s[pos:m.start()])))
        if m.group(2):
            label, url = m.group(1).strip() or m.group(2), m.group(2)
        else:
            label = url = m.group(3)
        cls = ' class="ltr"' if label.startswith("http") else ""
        out.append(f'<a href="{esc(url)}" target="_blank" rel="noopener"{cls}>{esc(label)}</a>')
        pos = m.end()
    out.append(_marks(esc(s[pos:])))
    return "".join(out)


def _marks(s):
    s = re.sub(r"\*\*(.+?)\*\*", r"<b>\1</b>", s)
    return re.sub(r"`([^`\n]+)`", r'<code class="ltr">\1</code>', s)


CODE_LINE = re.compile(r"^[\x20-\x7E—–“”]+$")


def lines_html(s):
    """One block per line; ASCII lines that look like code (assignment, call, comment) read left-to-right in mono."""
    out = []
    for line in s.split("\n"):
        t = line.strip()
        if t and CODE_LINE.match(t) and re.search(r"[=(#<\[]|\w\.\w|^\w+$", t) and "http" not in t:
            out.append(f'<div class="cl">{esc(line)}</div>')
        else:
            out.append(f"<div>{inline(line) if t else '&nbsp;'}</div>")
    return "".join(out)


def plain(s):
    """Text for the clipboard: links as their label (and URL), no markdown marks."""
    s = re.sub(r"\[([^\]]*)\]\(([^)\s]+)\)", lambda m: m.group(1) if m.group(1).strip() in ("", m.group(2)) else f"{m.group(1)} ({m.group(2)})", s)
    return s.replace("**", "")


def link_lines(s):
    """Split a video/reference callout into list items."""
    items = []
    for line in s.split("\n"):
        line = line.strip().lstrip("-").strip()
        if not line:
            continue
        m = re.match(r"\[\[FILE (.*?)(?:\|([0-9a-f-]+))?\]\]$", line)
        if m:
            name, fid = m.group(1).strip(), m.group(2)
            path = FILES.get(fid or "", {}).get("path")
            label = FILES.get(fid or "", {}).get("label") or re.sub(r"\.(mp4|mov|pdf)$", "", name) or "סרטון"
            if path and path.lower().endswith(".mp4"):
                items.append(f'<a href="{esc(player(path, label))}">{esc(label)}</a>')
            elif path:
                items.append(f'<a href="{"../" * DEPTH[0]}{esc(path)}" target="_blank" rel="noopener">{esc(label)}</a>')
            elif name:
                items.append(f'<span class="pend">{esc(name)} — יועלה בהמשך</span>')
        else:
            items.append(inline(line))
    return items


def md_lines(lines):
    """Notion-style lines -> HTML: "1. " numbered, "- " bulleted, two spaces of indent per level, else a paragraph."""
    out, stack = [], []  # open lists: (indent, tag)

    def close():
        out.append(f"</li></{stack.pop()[1]}>")

    for raw in lines:
        for line in raw.split("\n"):
            if not line.strip():
                continue
            ind = (len(line) - len(line.lstrip(" "))) // 2
            t = line.strip()
            m = re.match(r"^(\d+\.|[-•])\s*(.*)$", t)
            if not m:
                if stack and ind > 0:  # an indented line inside a list item
                    out.append(f"<br>{inline(t)}")
                    continue
                while stack:
                    close()
                cls = ' class="hp"' if re.match(r"^(חלק|בונוס)", t) else ""
                out.append(f"<p{cls}>{inline(t)}</p>")
                continue
            tag = "ol" if m.group(1)[0].isdigit() else "ul"
            while stack and stack[-1][0] > ind:
                close()
            if stack and stack[-1][0] == ind:
                if stack[-1][1] == tag:
                    out.append(f"</li><li>{inline(m.group(2))}")
                    continue
                close()
            out.append(f"<{tag}><li>{inline(m.group(2))}")
            stack.append((ind, tag))
    while stack:
        close()
    return "".join(out)


def week_label(w):
    return f"שבוע {w['n']}"


# ---------- page shell ----------

def page(title, body, depth, staff, script=""):
    up = "../" * depth
    robots = '<meta name="robots" content="noindex,nofollow">' if staff else ""
    return f"""<!doctype html>
<html lang="he" dir="rtl">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width,initial-scale=1">
{robots}<title>{esc(title)}</title>
<link rel="preconnect" href="https://fonts.googleapis.com">
<link rel="preconnect" href="https://fonts.gstatic.com" crossorigin>
<link href="{FONTS}" rel="stylesheet">
<link rel="stylesheet" href="{up}assets/site.css">
<link rel="icon" href="{up}assets/tau-logo.png">
</head>
<body>
<div class="wrap">
{body}
</div>
<script>
{script}
</script>
</body>
</html>
"""


def header(depth, staff, on):
    up = "../" * depth
    nav = ""
    if on is not None:
        links = [("admin.html", "מנהלות הקורס", "admin"), ("index.html", "השבועות", "weeks"), ("book.html", "ספר היחידות", "book")]
        if staff and (ROOT / CFG["staff_dir"] / "syllabus.pdf").exists():  # staff site only, for now
            links.append(("syllabus.pdf", "סילבוס", "syllabus"))
        nav = '<nav class="gen">' + "".join(
            f'<a href="{h}" class="{"on" if k == on else ""}">{t}</a>' for h, t, k in links) + "</nav>"
    badge = '<span class="staffbadge">גרסת מתרגלים</span>' if staff else ""
    return f"""<header class="hdr">
<img class="logo" src="{up}assets/tau-logo.png" alt="אוניברסיטת תל אביב">
<span class="sep"></span>
<a class="home" href="index.html"><span class="t1">{esc(CFG['title'])}</span><span class="t2">{esc(CFG['subtitle'])}</span></a>
{badge}{nav}
</header>"""


def footer(depth, staff):
    up = "../" * depth
    if staff:
        gate = f'<a class="ln" href="{up}index.html">לאתר הסטודנטים</a>'
    else:
        gate = ('<details class="tlog"><summary>כניסת מתרגלים</summary><form class="tlogf">'
                '<input type="password" autocomplete="off" aria-label="סיסמה" placeholder="סיסמה">'
                '<button type="submit">כניסה</button><span class="terr" hidden>סיסמה שגויה</span></form></details>')
    return (f'<footer class="foot"><img class="flogo" src="{up}assets/tau-logo.png" alt="">'
            f'<b>{esc(CFG["title"])}</b><span>{esc(CFG["subtitle"])}</span>{gate}</footer>')


GATE_JS = """// TA sign-in: the password is the name of the staff site's folder.
document.querySelectorAll('.tlogf').forEach(function(f){
  f.addEventListener('submit',function(e){ e.preventDefault();
    var v=f.querySelector('input').value.trim().toLowerCase().replace(/[^a-z0-9_-]/g,''), er=f.querySelector('.terr');
    if(!v) return;
    if(location.protocol==='file:'){ location.href=v+'/index.html'; return; }
    fetch(v+'/index.html',{method:'HEAD',cache:'no-store'}).then(function(r){ if(r.ok) location.href=v+'/'; else er.hidden=false; }).catch(function(){er.hidden=false});
  });
});"""


ADMIN_LINK = ('<a class="adminlink" href="admin.html"><svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.8" '
              'stroke-linecap="round" stroke-linejoin="round"><rect x="4" y="3" width="16" height="18" rx="2"/><path d="M8 8h8M8 12h8M8 16h5"/></svg>'
              '<b>מנהלות הקורס</b><span>סרטון הסבר, צוות, סילבוס</span></a>')


# ---------- week pages ----------

def rail_weeks(avail, sel):
    items = []
    for w in CFG["weeks"]:
        cls = "wk"
        if w["n"] == sel:
            cls += " sel"
        if w["n"] == CFG.get("current"):
            cls += " cur"
        now = '<span class="now">השבוע</span>' if w["n"] == CFG.get("current") else ""
        name = esc(w["title"]) if w["title"] else '<span class="empty">—</span>'
        inner = f'<span class="c">{w["n"]}</span><span>{name}<small class="wd">{short_date(w.get("date", ""))}</small>{now}</span>'
        if w["n"] in avail:
            items.append(f'<a href="week-{w["n"]}.html" class="{cls}">{inner}</a>')
        else:
            items.append(f'<div class="{cls} fut" title="בהכנה">{inner}</div>')
        for b in CFG.get("breaks", []):
            if b["after"] == w["n"]:
                items.append(f'<div class="wk brk"><span class="c">✦</span><span>{esc(b["label"])}<small class="wd">{short_date(b["date"])}</small></span></div>')
    items.append(f'<div class="wk fut exam"><span class="c">✱</span><span>{esc(CFG["exam"])}</span></div>')
    return "".join(items)


def player(url, title):
    """Local videos open in the site's own player page (no download button)."""
    return "play.html?" + urllib.parse.urlencode({"v": url, "t": title})


def href(url, depth, title=""):
    """External links open in a new tab; local videos open in the player; other repo files are relative to the repo root."""
    if re.match(r"https?://", url):
        return f'href="{esc(url)}" target="_blank" rel="noopener"'
    if url.lower().endswith(".mp4"):
        return f'href="{esc(player(url, title))}"'
    return f'href="{"../" * depth}{esc(url)}"'


def week_page(w, c, avail, book, depth, staff):
    n = w["n"]
    DEPTH[0] = depth
    weeks = rail_weeks(avail, n)
    rail = f'<aside class="rail card">{ADMIN_LINK}<h3>שבועות הקורס</h3>{weeks}</aside>'
    mob = (f'<details class="mweeks card"><summary><span class="c" style="background:var(--ink);color:#fff;border-color:var(--ink)">{n}</span>'
           f'<span><b>שבוע {n}</b> · {esc(w["title"])}</span><span class="more">כל השבועות ▾</span></summary><div class="list">{weeks}</div></details>')

    deck, videos = [], []
    if c.get("deck"):
        d = c["deck"]
        deck.append(f'<a {href(d["url"], depth)} class="deck"><small>מצגת</small>'
                     f'<b>{esc(d["title"])}</b><small>{esc(d.get("note", ""))}</small><code>#### WEEK {n} ----</code></a>')
        r = d.get("recording")  # a recorded walk-through of the deck, in the site's player
        if r:
            deck.append(f'<a {href(r["url"], depth, r["title"])} class="vid"><span class="ic">{ICON["play"]}</span>'
                        f'<span class="vt">{esc(r["title"])}<span class="vs">{esc(r.get("note", ""))}</span></span></a>')
    for v in c.get("videos", []):
        videos.append(f'<a {href(v["url"], depth, v["title"])} class="vid"><span class="ic">{ICON["play"]}</span>'
                     f'<span class="vt">{esc(v["title"])}<span class="vs">{esc(v.get("note", ""))}</span></span></a>')

    # the week's units, grouped by chapter: the same unit component as the book, opening in place
    units = []
    for u in c.get("units", []):
        ch = book[u["ch"] - 1]
        index = {s["h"]: k for k, s in enumerate(ch["secs"], 1)}
        for s in u["secs"]:
            if s not in index:
                print(f"  ! week {n}: section not in chapter {u['ch']}: {s}")
        g = ch["group"] == "code"
        tag = '<span class="tag">כתיבת קוד</span>' if g else ""
        secs = "".join(book_section(ch, index[s], ch["secs"][index[s] - 1], [], in_week=True) for s in u["secs"] if s in index)
        units.append(f'<div class="wch{" g" if g else ""}"><span class="num chn{" g" if g else ""}">פרק {ch["n"]}</span><b>{esc(ch["title"])}</b>{tag}'
                     f'<a class="tobook" href="book.html?w={n}#ch{ch["n"]}">הפרק המלא בספר ↗</a></div><div class="wunits">{secs}</div>')
    reading = "".join(f'<a href="{esc(r["url"])}" target="_blank" rel="noopener" class="row"><span class="ic">{ICON["book"]}</span>'
                      f'<span><span class="rt ltr" style="display:block;text-align:right">{esc(r["title"])}</span><span class="rs">{esc(r.get("note", ""))}</span></span></a>'
                      for r in c.get("reading", []))

    hw = c.get("hw") or {}
    if not hw.get("title"):
        hw_html = '<div class="hw"><p class="none">אין מטלה להגשה השבוע.</p></div>'
    else:
        due = (f'<p class="due">{ICON["clock"]}להגשה עד {esc(hw["due"])}</p>' if hw.get("due")
               else f'<p class="due tbd">{ICON["clock"]}תאריך ההגשה יפורסם בהמשך</p>')
        body = md_lines(hw["lines"]) if "lines" in hw else f'<ol>{"".join(f"<li>{esc(s)}</li>" for s in hw["steps"])}</ol>'
        ctx = f'<div class="ctx">{md_lines(hw["context"])}</div>' if hw.get("context") else ""
        dl = "".join(
            f'<a class="dfile" href="{"../" * depth}{esc(FILES[fid]["path"])}" download>{ICON["link"]}{esc(Path(FILES[fid]["path"]).name.split("-", 1)[-1] if "-" in Path(FILES[fid]["path"]).name else FILES[fid]["label"])}</a>'
            for fid in hw.get("files", []) if fid in FILES)
        dl = f'<p class="dfiles">קובצי נתונים: {dl}</p>' if dl else ""
        hw_html = (f'<div class="hw"><b class="ht">{esc(hw["title"])}</b>{ctx}{dl}<div class="hwb">{body}</div>'
                   + "".join(f'<p class="sm">{esc(p)}</p>' for p in hw.get("submit", [])) + due + "</div>")

    prev_n = next((m for m in sorted(avail, reverse=True) if m < n), None)
    next_n = next((m for m in sorted(avail) if m > n), None)
    title_of = {x["n"]: x["title"] for x in CFG["weeks"]}
    prev = (f'<a href="week-{prev_n}.html">→ שבוע {prev_n}: {esc(title_of[prev_n])}</a>' if prev_n else "<span>→ אין שבוע קודם</span>")
    nxt = (f'<a href="week-{next_n}.html">שבוע {next_n}: {esc(title_of[next_n])} ←</a>' if next_n else "<span>השבוע הבא בהכנה ←</span>")

    main = f"""<main class="card">
<section class="hero"><p class="eyebrow">שבוע {n} · יום ראשון {w.get('date', '')}</p><h1>{esc(w['title'])}</h1>{''.join(f'<p class="intro">{inline(p)}</p>' for p in c['intro'].split(chr(10) + chr(10)) if p.strip())}</section>
<section class="sec"><div class="ch"><h2>מצגת</h2></div><div class="media">{''.join(deck)}</div></section>
<section class="sec"><div class="ch"><h2>מה לומדים השבוע</h2><span>יחידות מספר היחידות · לחצו על יחידה כדי לפתוח אותה</span></div>{''.join(units)}
{('<p class="sub">קריאה מומלצת</p>' + reading) if reading else ''}</section>
{f'<section class="sec"><div class="ch"><h2>סרטוני עזר מהרשת</h2></div><div class="media">{"".join(videos)}</div></section>' if videos else ''}
<section class="sec"><div class="ch"><h2>המטלה השבועית</h2></div>{hw_html}{solution_html(c, staff)}</section>
<nav class="nav">{prev}{nxt}</nav>
</main>"""
    return f'{mob}<div class="layout">{rail}{main}</div>'


def solution_html(c, staff):
    """Staff site only: the solution, after the assignment (released to students later)."""
    sol = c.get("solution")
    if not staff or not sol:
        return ""
    parts = []
    for blk in sol:
        if blk.get("code") is not None:
            parts.append(f'<pre class="solcode ltr"><code>{esc(blk["code"])}</code></pre>')
        else:
            parts.append(f'<p>{inline(blk["text"])}</p>')
    return (f'<details class="sol"><summary>{ICON["spark"]}פתרון <span>(באתר המתרגלים בלבד · ישוחרר לסטודנטים אחרי מועד ההגשה)</span></summary>'
            f'<div class="solb">{"".join(parts)}</div></details>')


# ---------- book of units ----------

def book_page(book, weeks):
    # which weeks use each section (to open them from a week's link: book.html?w=N)
    used = {}
    for n, c in weeks.items():
        for u in c.get("units", []):
            for s in u["secs"]:
                used.setdefault((u["ch"], s), []).append(n)

    nav, body = [], []
    for grp, label in (("r", "R"), ("code", "כתיבת קוד")):
        chs = [c for c in book if c["group"] == grp]
        nav.append(f"<h3>{label}</h3>")
        body.append(f'<p class="grp">{"פרקי R" if grp == "r" else "כתיבת קוד — לכל שפה"}</p>')
        for ch in chs:
            g = " g" if grp == "code" else ""
            nav.append(f'<a href="#ch{ch["n"]}"><span class="num chn{g}">פרק {ch["n"]}</span>{esc(ch["title"])}</a>')
            secs = []
            for k, s in enumerate(ch["secs"], 1):
                secs.append(book_section(ch, k, s, used.get((ch["n"], s["h"]), [])))
            body.append(f'<section class="chap{g}" id="ch{ch["n"]}"><div class="ch"><span class="num chn{g}">פרק {ch["n"]}</span>'
                        f'<h2>{esc(ch["title"])}</h2><span>{len(ch["secs"])} יחידות</span></div>{"".join(secs)}</section>')

    rail = f'<aside class="rail card">{ADMIN_LINK}<h3>פרקי הספר</h3><nav class="bnav">{"".join(nav)}</nav></aside>'
    mob = (f'<details class="mweeks card"><summary><span class="ic">{ICON["book"]}</span><span><b>ספר היחידות</b></span>'
           f'<span class="more">כל הפרקים ▾</span></summary><div class="list bnav">{"".join(nav)}</div></details>')
    main = f"""<main class="card">
<section class="bhero"><p class="eyebrow">ספר היחידות</p><h1>ספר היחידות של הקורס</h1>
<p class="intro">כל יחידה היא שיחה קצרה עם מתרגל AI: מעתיקים את ההנחיה, מדביקים אותה בצ׳אט, ומתקדמים איתו שלב אחר שלב. ליד כל יחידה יש גם סרטונים וקישורים להעמקה.</p>
<div class="howto">{ICON["spark"]}<span>לחצו על „העתקה״, הדביקו בצ׳אט של מתרגל ה-AI, וענו לו כשהוא עוצר ושואל. אם נתקעים — אפשר לבקש ממנו רמז, ורק בסוף את הפתרון.</span></div>
{books_html()}</section>
{''.join(body)}
</main>"""
    return f'{mob}<div class="layout">{rail}{main}</div>'


def books_html():
    books = CFG.get("books", [])
    if not books:
        return ""
    items = "".join(f'<li><a href="{esc(u)}" target="_blank" rel="noopener" class="ltr">{esc(t)}</a></li>' for t, u in books)
    return f'<div class="books"><p class="lbl">{ICON["book"]}ספרים מומלצים</p><ul class="links">{items}</ul></div>'


def book_section(ch, k, s, wks, in_week=False):
    blocks = []
    for it in s["items"]:
        t = fix(it["text"])
        if it["kind"] == "prompt":
            lines = t.split("\n")
            first = lines[0].replace("**", "").strip()
            if first in (s["h"], ch["title"]) or (len(lines) > 1 and len(first) < 30 and not re.match(r"^\d", first)):
                t = "\n".join(lines[1:]).strip()
            blocks.append(f'<p class="lbl">{ICON["chat"]}הנחיה למתרגל AI</p><div class="prompt">'
                          f'<button class="copy" type="button">{ICON["copy"]}<span>העתקה</span></button>'
                          f'<div class="pt">{lines_html(t)}</div><textarea hidden>{esc(plain(t))}</textarea></div>')
        elif it["kind"] in ("video", "ref"):
            items = link_lines(t)
            if items:
                label = (ICON["play"] + "סרטונים") if it["kind"] == "video" else (ICON["link"] + "להעמקה")
                blocks.append(f'<p class="lbl">{label}</p><ul class="links">{"".join(f"<li>{i}</li>" for i in items)}</ul>')
        elif it["kind"] == "code":
            blocks.append(f'<div class="prompt ltr" style="padding:14px 16px;font-family:JetBrains Mono,monospace;font-size:13.5px;text-align:left">{esc(t.strip("`").strip())}</div>')
        else:
            blocks.append(f'<div class="prompt" style="padding:14px 16px">{lines_html(t)}</div>')
    uid = f'ch{ch["n"]}-{k}'
    if in_week:
        blocks.append(f'<p class="bsfoot">יחידה {ch["n"]}.{k} בספר היחידות · <a href="book.html#{uid}">לראות אותה בתוך הפרק ↗</a></p>')
    data = f' data-w="{" ".join(map(str, wks))}"' if wks else ""
    g = " g" if ch["group"] == "code" else ""
    return (f'<details class="bs{g}" id="{uid}"{data}><summary><span class="un">{ch["n"]}.{k}</span>{esc(fix(s["h"]))}</summary>'
            f'<div class="bsb">{"".join(blocks)}</div></details>')


COPY_JS = """// copy an AI-tutor prompt
document.querySelectorAll('.copy').forEach(function(b){
  b.addEventListener('click',function(){
    var t=b.parentNode.querySelector('textarea').value, s=b.querySelector('span');
    function ok(){ b.classList.add('ok'); s.textContent='הועתק'; setTimeout(function(){b.classList.remove('ok'); s.textContent='העתקה';},1600); }
    if(navigator.clipboard) navigator.clipboard.writeText(t).then(ok,function(){});
    else { var a=document.createElement('textarea'); a.value=t; document.body.appendChild(a); a.select(); try{document.execCommand('copy'); ok();}catch(e){} a.remove(); }
  });
});"""

BOOK_JS = COPY_JS + """
// book.html?w=N opens (and marks) the sections that week N uses; #chN-K opens one section
(function(){
  var w=(location.search.match(/[?&]w=(\\d+)/)||[])[1];
  if(w) document.querySelectorAll('.bs[data-w]').forEach(function(d){ if((' '+d.dataset.w+' ').indexOf(' '+w+' ')>=0){ d.open=true; d.classList.add('hl'); } });
  var h=location.hash.slice(1), el=h&&document.getElementById(h);
  if(el&&el.tagName==='DETAILS') el.open=true;
})();"""


# ---------- course admin + player ----------

def admin_page(prefix, avail):
    a = json.loads((SRC / "content" / "admin.json").read_text(encoding="utf-8"))
    v = a["video"]
    video = (f'<a href="{esc(player(v["url"], v["title"]))}" class="vid guide"><span class="ic">{ICON["play"]}</span>'
             f'<span class="vt">{esc(v["title"])}<span class="vs">{esc(v.get("note", ""))}</span></span></a>')
    people = "".join(f'<div class="person"><b>{esc(p["role"])}</b><span>{esc(p["name"])}</span>'
                     f'<a class="ltr" href="mailto:{esc(p["email"])}">{esc(p["email"])}</a></div>' for p in a["staff"])
    secs = "".join(f'<section class="sec"><div class="ch"><h2>{esc(x["h"])}</h2></div><div class="adm">{md_lines(x["lines"])}</div></section>'
                   for x in a["sections"])
    links = "".join(f'<a href="{esc(l["url"])}" class="row" target="_blank" rel="noopener"><span class="ic">{ICON["book"]}</span>'
                    f'<span><span class="rt">{esc(l["title"])}</span><span class="rs">{esc(l.get("note", ""))}</span></span></a>'
                    for l in a.get("links", []) if (ROOT / prefix / l["url"]).exists())
    weeks = rail_weeks(avail, None)
    rail = f'<aside class="rail card">{ADMIN_LINK.replace("adminlink", "adminlink on")}<h3>שבועות הקורס</h3>{weeks}</aside>'
    mob = (f'<details class="mweeks card"><summary><span class="ic">{ICON["book"]}</span><span><b>מנהלות הקורס</b></span>'
           f'<span class="more">כל השבועות ▾</span></summary><div class="list">{weeks}</div></details>')
    docs = f'<section class="sec"><div class="ch"><h2>מסמכים</h2></div>{links}</section>' if links else ""
    main = (f'<main class="card"><section class="hero"><p class="eyebrow">מנהלות הקורס</p><h1>מנהלות הקורס</h1>'
            f'<p class="intro">{esc(a["intro"])}</p></section>'
            f'<section class="sec"><div class="ch"><h2>איך עובדים עם האתר</h2></div><div class="media">{video}</div></section>'
            f'<section class="sec"><div class="ch"><h2>צוות הקורס</h2></div><div class="people">{people}</div></section>'
            f'{secs}{docs}</main>')
    return f'{mob}<div class="layout">{rail}{main}</div>'


PLAYER_JS = """// the site's player: a local video, no download button, no right-click menu (makes saving harder, not impossible)
(function(){
  var q=new URLSearchParams(location.search), v=q.get('v')||'', t=q.get('t')||'';
  var vid=document.getElementById('vid');
  if(/^files\\/[^?#]+\\.mp4$/i.test(v) && v.indexOf('..')<0){ vid.src='__UP__'+v; }
  document.getElementById('ptitle').textContent=t;
  if(t) document.title=t+' · '+document.title;
  vid.addEventListener('contextmenu',function(e){e.preventDefault();});
  var b=document.getElementById('back');
  if(document.referrer && document.referrer.indexOf(location.host)>=0){ b.href=document.referrer; }
})();"""


def player_page(depth, staff):
    body = (header(depth, staff, None) + '<main class="card player"><a class="back" href="index.html" id="back">→ חזרה</a>'
            '<h1 class="ptitle" id="ptitle"></h1>'
            '<video id="vid" controls controlsList="nodownload" disablePictureInPicture playsinline preload="metadata"></video>'
            '</main>' + footer(depth, staff))
    return page(CFG["title"], body, depth, staff, PLAYER_JS.replace("__UP__", "../" * depth))


# ---------- build ----------

def write(rel, text):
    p = ROOT / rel
    p.parent.mkdir(parents=True, exist_ok=True)
    p.write_text(text, encoding="utf-8")
    print("  ", rel)


def build_site(prefix, staff, avail, weeks, book):
    depth = 1 if prefix else 0
    title_of = {w["n"]: w for w in CFG["weeks"]}
    for n in avail:
        body = header(depth, staff, "weeks") + week_page(title_of[n], weeks[n], avail, book, depth, staff) + footer(depth, staff)
        html_ = page(f"שבוע {n} · {CFG['title']}", body, depth, staff, COPY_JS + "\n" + GATE_JS)
        write(f"{prefix}week-{n}.html", html_)
    home = CFG.get("current") if CFG.get("current") in avail else min(avail)
    body = header(depth, staff, "weeks") + week_page(title_of[home], weeks[home], avail, book, depth, staff) + footer(depth, staff)
    write(f"{prefix}index.html", page(CFG["title"], body, depth, staff, COPY_JS + "\n" + GATE_JS))
    DEPTH[0] = depth
    body = header(depth, staff, "book") + book_page(book, {n: weeks[n] for n in avail}) + footer(depth, staff)
    write(f"{prefix}book.html", page(f"ספר היחידות · {CFG['title']}", body, depth, staff, BOOK_JS + "\n" + GATE_JS))
    body = header(depth, staff, "admin") + admin_page(prefix, avail) + footer(depth, staff)
    write(f"{prefix}admin.html", page(f"מנהלות הקורס · {CFG['title']}", body, depth, staff, GATE_JS))
    write(f"{prefix}play.html", player_page(depth, staff))


def build_solo():
    body = (f'<main class="solo"><img src="assets/tau-logo.png" alt="אוניברסיטת תל אביב">'
            f'<h1>{esc(CFG["title"])}</h1><p>{esc(CFG["subtitle"])}</p></main>' + footer(0, False))
    write("index.html", page(CFG["title"], body, 0, False, GATE_JS))


def main():
    book = load_book()
    weeks = load_weeks()
    staff = CFG["staff_dir"].strip("/")
    (ROOT / "assets").mkdir(exist_ok=True)
    shutil.copy2(SRC / "site.css", ROOT / "assets" / "site.css")
    for f in (SRC / "img").iterdir():
        shutil.copy2(f, ROOT / "assets" / f.name)

    # clear generated pages from previous builds
    for d in (ROOT, ROOT / staff):
        for f in list(d.glob("week-*.html")) + [d / "book.html", d / "admin.html", d / "play.html"]:
            if f.exists():
                f.unlink()

    print("staff site:")
    build_site(f"{staff}/", True, sorted(weeks), weeks, book)
    print("public site:")
    pub = sorted(n for n in CFG.get("published", []) if n in weeks)
    if pub:
        build_site("", False, pub, weeks, book)
    else:
        build_solo()
    (ROOT / ".nojekyll").touch()


if __name__ == "__main__":
    main()
