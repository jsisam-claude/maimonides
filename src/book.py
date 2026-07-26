#!/usr/bin/env python3
"""Read the whole 1848 volume as text, with each line attributed to its author.

Three readings of this book are available and none of them is the truth.
Tesseract's `heb` model reading the page images is one; the same model on
`heb_best` at 600 dpi is a second; and the Hebrewbooks PDF carries a third,
its own OCR layer, which is neither better by decree nor to be trusted — it is
simply an independent witness that costs nothing to consult. This module
produces the third, because it is the only one that comes with geometry, and
geometry is what the other two lack.

Two things fall out of that geometry.

*Attribution.* The volume prints Kaspi's commentary in square Hebrew above a
rule and Werbluner's editorial notes in Rashi semi-cursive below it. Reading
the page as one text mixes them, which is not a transcription error but an
editorial one: Werbluner's words end up in Kaspi's mouth. `zones.py` finds the
rule in the page image; every line of the layer is then assigned to the side of
it that it falls on.

*Lemmata.* Where the print quotes the Guide it sets the words in a heavy
letter-spaced display face, and the producer of the layer, faithfully, wrote
each letter as its own word. A run of single-glyph words is therefore the
compositor's own marking of a quotation — evidence read off the page, not
inferred from it, and it survives OCR damage that defeats substring matching.

Dependencies: `pdftotext` and `pdftoppm` from poppler-utils, and Pillow, which
the OCR stage already needs. No Python packages beyond that.
"""
from __future__ import annotations

import html
import json
import re
import subprocess
import sys
import tempfile
from dataclasses import dataclass, field
from pathlib import Path

import layer
import zones

PAGE = re.compile(r'<page width="([\d.]+)" height="([\d.]+)">(.*?)</page>', re.S)
DPI = 150          # enough to see a hairline rule, cheap enough to scan in pure Python


@dataclass
class Line:
    text: str
    display: list[tuple[int, int]]      # character spans set in display type
    y: float                            # top, as a fraction of the page
    word: list[list[layer.Word]] = field(default_factory=list)
    # ^ the glyphs behind each whitespace token of `text`, in the same order,
    #   so a caller that has to point at the ink rather than quote it —
    #   src/crops.py, cutting the scan for a human — can find it. Not dumped:
    #   geometry is cheap to recover and would double the file.


@dataclass
class Page:
    page: int                           # 1-based index into the PDF
    folio: int | None                   # as printed at the head of the page
    body: list[Line] = field(default_factory=list)    # Kaspi, square script
    notes: list[Line] = field(default_factory=list)   # Werbluner, Rashi script

    def text(self, kind: str = "body") -> str:
        return "\n".join(ln.text for ln in getattr(self, kind))


def cuts(pdf: str, dpi: int = DPI, pages: list[int] | None = None) -> dict[int, float]:
    """For each page, where the rule falls — or 1.0 if the page carries none.

    *pages* narrows the scan to a few pages. A caller that wants one page's
    geometry should not have to rasterise a hundred and seventy.
    """
    from PIL import Image

    out: dict[int, float] = {}
    with tempfile.TemporaryDirectory() as tmp:
        for span in ([["-f", str(n), "-l", str(n)] for n in pages] if pages
                     else [[]]):
            subprocess.run(["pdftoppm", "-r", str(dpi), "-gray", "-png", *span,
                            pdf, f"{tmp}/p"], check=True)
        for f in sorted(Path(tmp).glob("p-*.png")):
            img = Image.open(f)
            zs = zones.zones(img)
            out[int(f.stem.split("-")[-1])] = (
                zs[1].top / img.size[1] if len(zs) > 1 else 1.0)
    return out


def read(pdf: str, cut: dict[int, float] | None = None) -> list[Page]:
    """Every page of the volume, its lines split between the two texts."""
    cut = cuts(pdf) if cut is None else cut
    xml = subprocess.run(["pdftotext", "-bbox-layout", "-enc", "UTF-8", pdf, "-"],
                         capture_output=True, text=True, check=True).stdout

    out = []
    for n, (_w, h, body) in enumerate(PAGE.findall(xml), start=1):
        h, edge, page = float(h), cut.get(n, 1.0), Page(n, None)
        lines = []
        for raw in layer.LINE.findall(body):
            ws = [layer.Word(layer.logical(html.unescape(t)),
                             float(a), float(b), float(c), float(d))
                  for a, b, c, d, t in layer.WORD.findall(raw)]
            ws = [w for w in ws if w.text.strip()]
            if ws:
                lines.append(sorted(ws, key=lambda w: -w.x1))
        page.folio = layer.folio(lines)
        for ln in lines:
            y = min(w.y0 for w in ln) / h
            text, disp = layer.render(ln)
            if page.folio is not None and text.strip() == str(page.folio) and y < 0.05:
                continue                      # the running head is not text
            (page.notes if y >= edge else page.body).append(
                Line(text, disp, y, [g for _, g, _ in layer.chunks(ln)]))
        out.append(page)
    return out


def dump(pages: list[Page], path: str) -> None:
    json.dump({"pages": [{"page": p.page, "folio": p.folio,
                          "body": [[ln.text, ln.display] for ln in p.body],
                          "notes": [[ln.text, ln.display] for ln in p.notes]}
                         for p in pages]},
              open(path, "w"), ensure_ascii=False)


if __name__ == "__main__":
    pdf, out = sys.argv[1], sys.argv[2]
    pages = read(pdf)
    dump(pages, out)
    ruled = sum(1 for p in pages if p.notes)
    bw = sum(len(ln.text.split()) for p in pages for ln in p.body)
    nw = sum(len(ln.text.split()) for p in pages for ln in p.notes)
    lem = sum(len(ln.display) for p in pages for ln in p.body)
    print(f"{len(pages)} pages, {ruled} with editorial notes\n"
          f"  Kaspi      {bw:>7,} words\n"
          f"  Werbluner  {nw:>7,} words\n"
          f"  lemmata    {lem:>7,} marked by the compositor", file=sys.stderr)
