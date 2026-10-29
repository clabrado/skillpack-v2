#!/usr/bin/env python3
"""Render-check an intel debrief PDF: page count, footer-zone overflow, PNG per page.

usage: check.py <debrief.pdf> [--expect N] [--png-dir DIR]
Exit 1 if any page has body text intruding into the footer zone or the page
count differs from --expect. Inspect the PNGs visually before calling it done.
"""
import argparse, pathlib, sys
import fitz

ap = argparse.ArgumentParser()
ap.add_argument("pdf")
ap.add_argument("--expect", type=int)
ap.add_argument("--png-dir")
a = ap.parse_args()
doc = fitz.open(a.pdf)
png = pathlib.Path(a.png_dir or pathlib.Path(a.pdf).with_suffix(""))
png.mkdir(parents=True, exist_ok=True)
fail = False
print("pages", doc.page_count)
if a.expect and doc.page_count != a.expect:
    print(f"PAGE COUNT {doc.page_count} != expected {a.expect} (content spilled onto extra pages)")
    fail = True
for i, p in enumerate(doc):
    bad = []
    for b in p.get_text("dict")["blocks"]:
        for l in b.get("lines", []):
            t = "".join(s["text"] for s in l["spans"]).strip()
            if not t or "Debrief" in t or "Dynatrace internal" in t or t.replace(" ", "").replace("/", "").isdigit():
                continue
            if l["bbox"][3] > 740:
                bad.append((round(l["bbox"][3]), t[:40]))
    p.get_pixmap(dpi=80).save(str(png / f"p{i+1:02d}.png"))
    print(i + 1, "OK" if not bad else f"OVERFLOW {bad[:3]}")
    fail |= bool(bad)
print("pngs:", png)
sys.exit(1 if fail else 0)
