"""Render the decks (slides/W*.qmd) into decks/, with one shared copy of the reveal.js libraries.

Quarto writes each deck with its own <deck>_files/libs/ (~6 MB). Here every deck is rendered to slides/_build/, the libraries are moved once to decks/_libs/, and the deck's links are rewritten to point there.
The logo and other resources go to decks/theme/.

Usage: python tools/build_decks.py            (all decks)
       python tools/build_decks.py W3 W4      (only these)
"""
import shutil
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
SLIDES = ROOT / "slides"
DECKS = ROOT / "decks"


def render(name):
    tmp = SLIDES / "_build"  # quarto wants the output folder inside the project
    shutil.rmtree(tmp, ignore_errors=True)
    if True:
        r = subprocess.run(["quarto", "render", f"{name}.qmd", "--output-dir", "_build", "-M", "embed-resources:false"],
                           cwd=SLIDES, capture_output=True, text=True, encoding="utf-8", errors="replace", shell=True)
        out = tmp / f"{name}.html"
        if r.returncode or not out.exists():
            print(r.stdout[-2000:], r.stderr[-2000:])
            raise SystemExit(f"render failed: {name}")
        html = out.read_text(encoding="utf-8")
        libs = tmp / f"{name}_files" / "libs"
        if libs.exists():
            dest = DECKS / "_libs"
            for f in libs.rglob("*"):
                if f.is_file():
                    target = dest / f.relative_to(libs)
                    target.parent.mkdir(parents=True, exist_ok=True)
                    if not target.exists() or target.read_bytes() != f.read_bytes():
                        shutil.copy2(f, target)
            html = html.replace(f"{name}_files/libs/", "_libs/")
        for res in ("theme",):
            src = tmp / res
            if src.exists():
                shutil.copytree(src, DECKS / res, dirs_exist_ok=True)
        (DECKS / f"{name}.html").write_text(html, encoding="utf-8")
        left = [p for p in tmp.rglob("*") if p.is_file() and "_libs" not in p.parts and p.suffix not in (".html",)
                and not str(p.relative_to(tmp)).startswith((f"{name}_files", "theme"))]
        if left:
            print("  note: extra output not copied:", [str(p.relative_to(tmp)) for p in left])
        print(f"{name}: {(DECKS / f'{name}.html').stat().st_size / 1e3:.0f} KB")
    shutil.rmtree(tmp, ignore_errors=True)


if __name__ == "__main__":
    DECKS.mkdir(exist_ok=True)
    names = sys.argv[1:] or sorted((p.stem for p in SLIDES.glob("W*.qmd")), key=lambda s: int(s[1:]))
    for name in names:
        render(name)
