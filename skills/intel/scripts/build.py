#!/usr/bin/env python3
"""Render an intel debrief: <workdir>/content.html -> PDF via headless Chrome.

usage: build.py <workdir> <out.pdf> [--title "Doc title"] [--footer "Acme Debrief"]

content.html is a sequence of <section class="page ..."> blocks (see
assets/skeleton.html). Placeholders:
  {{WAVE}}   gradient wave SVG for the cover
  {{P}}      running page number
  {{TOTAL}}  total page count
  {{FOOTER}} footer label (e.g. "Acme Debrief · Dynatrace internal")
Template assets (style.css, logo, fonts) are copied into workdir first. Brand fonts
are optional: *.otf from assets/template/ or $INTEL_FONT_DIR; otherwise Arial.
Set $CHROME to the Chrome/Chromium binary when not on macOS.
"""
import argparse, math, os, pathlib, re, shutil, subprocess

SKILL = pathlib.Path(__file__).resolve().parent.parent
TEMPLATE = SKILL / "assets" / "template"
CHROME = os.environ.get("CHROME", "/Applications/Google Chrome.app/Contents/MacOS/Google Chrome")


def wave_svg():
    paths = []
    W, H = 816, 211
    for i in range(22):
        amp = 26 + i * 1.6
        ph = i * 0.16
        y0 = 120 - i * 2.2
        pts = []
        for x in range(0, W + 9, 8):
            t = x / W
            y = y0 + amp * math.sin(2 * math.pi * (t * 1.15) + ph) * (0.35 + 0.65 * t) + 18 * math.sin(2 * math.pi * t * 2.6 + ph * 2)
            pts.append(f"{x},{y:.1f}")
        op = 0.10 + 0.5 * (i / 21) ** 2
        paths.append(f'<polyline points="{" ".join(pts)}" fill="none" stroke="url(#g)" stroke-width="{0.6 + i*0.03:.2f}" opacity="{op:.2f}"/>')
    return (f'<svg class="wave" viewBox="0 0 {W} {H}" preserveAspectRatio="none" xmlns="http://www.w3.org/2000/svg">'
            '<defs><linearGradient id="g" x1="0" x2="1"><stop offset="0" stop-color="#1866FE"/><stop offset=".6" stop-color="#7F1AFE"/><stop offset="1" stop-color="#01D393"/></linearGradient></defs>'
            + "".join(paths) + "</svg>")


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("workdir")
    ap.add_argument("out")
    ap.add_argument("--title", default="Intel Debrief")
    ap.add_argument("--footer", default="Debrief · Dynatrace internal")
    a = ap.parse_args()
    d = pathlib.Path(a.workdir).resolve()
    for f in TEMPLATE.iterdir():
        shutil.copy2(f, d / f.name)
    fonts = os.environ.get("INTEL_FONT_DIR")
    if fonts and pathlib.Path(fonts).is_dir():
        for f in pathlib.Path(fonts).glob("*.otf"):
            shutil.copy2(f, d / f.name)
    body = (d / "content.html").read_text()
    body = body.replace("{{WAVE}}", wave_svg()).replace("{{FOOTER}}", a.footer)
    body = body.replace("{{TOTAL}}", str(body.count('class="page')))
    n = iter(range(1, 1000))
    body = re.sub(r"\{\{P\}\}", lambda m: str(next(n)), body)
    html = (f'<!doctype html><html><head><meta charset="utf-8"><link rel="stylesheet" href="style.css">'
            f'<title>{a.title}</title></head><body>{body}</body></html>')
    (d / "debrief.html").write_text(html)
    out = pathlib.Path(a.out).resolve()
    subprocess.run([CHROME, "--headless=new", "--disable-gpu", "--no-pdf-header-footer",
                    "--allow-file-access-from-files", f"--print-to-pdf={out}", f"file://{d}/debrief.html"],
                   check=True, stderr=subprocess.DEVNULL)
    print("pages in html:", body.count('class="page'), "->", out)


if __name__ == "__main__":
    main()
