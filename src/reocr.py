#!/usr/bin/env python3
"""Read the commentary again, from the page images, one typographic zone at a time.

The volume was first read whole-page with `heb --psm 6`, which was wrong twice
over. It fed Tesseract's square-script model lines of Rashi semi-cursive, which
it cannot read and does not decline to read — it returns a substitution cipher
that looks like Hebrew and is not — and it let that output be attributed to
Kaspi. And `--psm 6` asserts a uniform block where the page is in fact a
sequence of paragraphs at different measures.

Reading the zones separately, with the model and mode chosen by measurement
rather than by default, is worth about a third of the errors. Against the
43,456-form lexicon built from clean fourteenth-century Hebrew:

    heb      --psm 6   600 dpi      21.6 % unattested
    heb_best --psm 4   600 dpi      15.4 %

with the token count steady across the grid, so the gain is a better reading
and not a quieter one.

This module produces that second reading for every Hebrew page. It is not the
edition's text: it is one of three witnesses that `ensemble.py` arbitrates.

Dependencies: `pdftoppm` from poppler-utils, Tesseract with `heb_best`, Pillow.
"""
from __future__ import annotations

import json
import subprocess
import sys
import tempfile
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path

import zones

DPI = 600
LANG = "heb_best"
PSM = "4"          # a column of text of variable sizes

# The settings are arguments, not constants, because the point of this module
# is now to produce *more than one* reading. Resolution, model and segmentation
# mode are the three knobs that make two Tesseract runs disagree, and a witness
# that differs on all three is worth having beside one that differs on none:
# `heb --psm 6` at 300 dpi is a demonstrably different reader from `heb_best
# --psm 4` at 600, and where they agree, the agreement means something.


def _ocr(png: Path, lang: str, psm: str, dpi: int) -> str:
    out = subprocess.run(["tesseract", str(png), "stdout", "-l", lang,
                          "--psm", psm, "--dpi", str(dpi)],
                         capture_output=True, text=True)
    return out.stdout


def page(pdf: str, n: int, tmp: Path,
         lang: str = LANG, psm: str = PSM, dpi: int = DPI) -> dict:
    """Rasterise page *n*, split it, and read each zone on its own."""
    from PIL import Image

    tag = f"p{n}-{lang}-{psm}-{dpi}"
    subprocess.run(["pdftoppm", "-r", str(dpi), "-gray", "-png",
                    "-f", str(n), "-l", str(n), pdf, str(tmp / tag)],
                   check=True)
    src = next(tmp.glob(f"{tag}-*.png"))
    img = Image.open(src)
    got = {}
    for z in zones.zones(img):
        cut = tmp / f"{tag}-{z.kind}.png"
        zones.crop(img, z).save(cut)
        got.setdefault(z.kind, []).append(_ocr(cut, lang, psm, dpi))
        cut.unlink()
    src.unlink()
    return {"page": n, **{k: "\n".join(v) for k, v in got.items()}}


def run(pdf: str, pages: list[int], workers: int = 2,
        lang: str = LANG, psm: str = PSM, dpi: int = DPI) -> list[dict]:
    with tempfile.TemporaryDirectory() as t:
        tmp = Path(t)
        with ThreadPoolExecutor(workers) as pool:
            return sorted(pool.map(lambda n: page(pdf, n, tmp, lang, psm, dpi), pages),
                          key=lambda d: d["page"])


if __name__ == "__main__":
    pdf, want, out = sys.argv[1:4]
    lang, psm, dpi = (sys.argv[4:] + [LANG, PSM, DPI][len(sys.argv) - 4:])
    ps = json.load(open(want))
    got = run(pdf, ps, lang=lang, psm=str(psm), dpi=int(dpi))
    json.dump(got, open(out, "w"), ensure_ascii=False)
    print(f"{len(got)} pages read at {dpi} dpi, {lang} --psm {psm}", file=sys.stderr)
