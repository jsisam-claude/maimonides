#!/usr/bin/env python3
"""A fourth reading of the volume, made by looking at it.

The three readings this edition arbitrates between are all machine OCR, and
the adjudication crops showed what that costs. Words the print sets cleanly
and unambiguously — ‏בהקדמה‎, ‏משתתף‎, ‏מאמינים‎, ‏המתחייב‎, ‏הספקות‎ — come back
from all three as ‏בהקמדח‎, ‏טהחף‎, ‏מאמינם‎, ‏המתחיינ‎, ‏הםפקוה‎. The residue of
five thousand "doubtful" words was never a residue of ambiguous ink. It was
three weak readers agreeing to fail, and every stage built on top of them —
voting, lexicon repair, confusion tables — inherited the failure, because none
of those stages can see.

So this module prepares a reading that can. It cuts the commentary zone out of
the page at printing resolution and hands it to a reader that transcribes what
is actually printed. That reading then enters the ensemble as an ordinary
witness — no privilege, no override — and the existing arbitration decides what
to do with it. What makes it worth having is not authority but independence:
its errors are not the other three's errors, so where it agrees with any of
them the agreement means something.

Two decisions about the cut, both forced by how the reader receives an image.

*Strips of whole lines, not pages.* An image is scaled to fit a fixed budget on
its longest edge, so a tall page arrives shrunk to illegibility — the fix that
matters is not more resolution but a squarer crop. Six lines at a time keeps
the type at roughly the size it was on the adjudication sheet, where it read
cleanly. The bands are cut from the line geometry the publisher's layer already
carries, so no line is ever severed.

*The zone, and nothing around it.* Below the rule is Werbluner's Rashi
semi-cursive, a different text in a different script; the margins are paper.
Cropping to the ink that matters buys back the resolution the scaling took.

Dependencies: `pdftoppm` from poppler-utils, and Pillow.
"""
from __future__ import annotations

import json
import os
import re
import subprocess
import sys
import tempfile
from pathlib import Path

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import book                                       # noqa: E402
import measure                                    # noqa: E402

DPI = 600          # what the volume was printed at, near enough
WIDE = 1500        # px across a finished strip; above this the reader rescales
ROWS = 6           # lines per strip — a compromise between context and size
PAD = 2            # pt of paper kept around the band — see below

# The band already spans its own lines' full extent, so the padding is only to
# keep ink off the edge. It has to stay small: at ten points the neighbouring
# line bleeds in almost whole, and a reader cannot tell what it is meant to
# transcribe from what merely showed up. At two, a neighbour is a sliver and
# obviously not a line.


def bands(lines: list[book.Line], rows: int = ROWS) -> list[tuple[float, ...]]:
    """Groups of *rows* consecutive lines, as boxes in PDF points."""
    box = []
    for ln in lines:
        gs = [g for w in ln.word for g in w]
        if gs:
            box.append((min(g.x0 for g in gs), min(g.y0 for g in gs),
                        max(g.x1 for g in gs), max(g.y1 for g in gs)))
    out = []
    for i in range(0, len(box), rows):
        part = box[i:i + rows]
        out.append((min(b[0] for b in part), min(b[1] for b in part),
                    max(b[2] for b in part), max(b[3] for b in part)))
    return out


def raster(pdf: str, page: int, dpi: int = DPI):
    from PIL import Image

    with tempfile.TemporaryDirectory() as tmp:
        subprocess.run(["pdftoppm", "-r", str(dpi), "-gray", "-png",
                        "-f", str(page), "-l", str(page), pdf, f"{tmp}/p"],
                       check=True)
        img = Image.open(next(Path(tmp).glob("p-*.png")))
        img.load()
        return img


def strips(img, boxes, dpi: int = DPI, wide: int = WIDE):
    """Each band as its own image, scaled to where the type reads."""
    from PIL import Image

    s, out = dpi / 72.0, []
    for x0, y0, x1, y1 in boxes:
        c = img.crop((max(0, int((x0 - PAD) * s)), max(0, int((y0 - PAD) * s)),
                      min(img.size[0], int((x1 + PAD) * s)),
                      min(img.size[1], int((y1 + PAD) * s))))
        if c.size[0] > wide:
            c = c.resize((wide, max(1, round(c.size[1] * wide / c.size[0]))),
                         Image.LANCZOS)
        out.append(c)
    return out


def hebrew(base: str) -> list[int]:
    """The pages that are Kaspi's Hebrew — the same set every stage measures."""
    layer = json.load(open(f"{base}/data/book_layer.json", encoding="utf-8"))["pages"]
    return [p["page"] for p in layer
            if p["body"] and measure.hebrew(" ".join(t for t, _ in p["body"])
                                            + " " + " ".join(t for t, _ in p["notes"]))]


def render(pdf: str, want: list[int], dst: str, cut: dict | None = None) -> dict:
    """Write the strips and return, per page, the files and the lines in each."""
    Path(dst).mkdir(parents=True, exist_ok=True)
    pages = {p.page: p for p in book.read(pdf, cut or book.cuts(pdf))}
    out = {}
    for n in want:
        p = pages.get(n)
        if not p or not p.body:
            continue
        boxes = bands(p.body)
        files = [f"{dst}/p{n:03d}_{i}.png" for i in range(len(boxes))]
        if not all(os.path.exists(f) for f in files):
            for f, c in zip(files, strips(raster(pdf, n), boxes)):
                c.save(f, "PNG", optimize=True)
        out[n] = {"folio": p.folio, "files": files,
                  "lines": [len(p.body[i:i + ROWS])
                            for i in range(0, len(p.body), ROWS)]}
    return out


MARK = re.compile(r"⟪(.*?)⟫")


def head(text: str) -> str:
    """The page without its printed folio number.

    A reader looking at the top of a page transcribes the number at the head of
    it, because it is printed there. The publisher's layer drops it — a running
    head is not text — and the two readings have to agree about what the page
    contains or the number is aligned against a word and inserted into the
    commentary. A line of nothing but digits is unambiguous here: no page of
    this commentary begins with one.
    """
    lines = text.split("\n")
    if lines and lines[0].strip().isdigit():
        return "\n".join(lines[1:]).lstrip("\n")
    return text


def merge(base: str, src: str = "eyes_raw") -> tuple[list[dict], dict]:
    """Gather the per-page transcriptions into one reading of the volume.

    A reader that is unsure of a word wraps it in ⟪ ⟫ rather than silently
    guessing. The marks come out here — the text keeps the guess, and the guess
    itself is recorded separately, because a word the fourth reader hedged on is
    exactly the word that should still reach a human with the image beside it.

    What is recorded is the *form*, not its position. A position would have to
    be carried through two alignments before anything downstream could use it,
    and every alignment is a chance to be wrong about which word was meant. A
    form is carried by being itself. The cost is that a page which prints the
    same hedged form twice gets two crops instead of one, which is a cost worth
    paying to keep the link between the doubt and the ink direct.
    """
    idx = json.load(open(f"{base}/data/eyes/index.json", encoding="utf-8"))
    out, hedged = [], {}
    for n in sorted(int(k) for k in idx):
        f = Path(f"{base}/data/{src}/p{n:03d}.txt")
        if not f.exists():
            continue
        text = head(f.read_text(encoding="utf-8").strip())
        at = sorted({MARK.sub(r"\1", w) for w in text.split() if MARK.search(w)})
        out.append({"page": n, "body": MARK.sub(r"\1", text)})
        if at:
            hedged[n] = at
    return out, hedged


if __name__ == "__main__":
    if len(sys.argv) > 1 and sys.argv[1] == "merge":
        base = sys.argv[2] if len(sys.argv) > 2 else "."
        pages, hedged = merge(base)
        json.dump(pages, open(f"{base}/data/book_eyes.json", "w",
                              encoding="utf-8"), ensure_ascii=False)
        json.dump(hedged, open(f"{base}/data/eyes_hedged.json", "w",
                               encoding="utf-8"), ensure_ascii=False)
        w = sum(len(p["body"].split()) for p in pages)
        print(f"{len(pages)} pages, {w:,} words, "
              f"{sum(len(v) for v in hedged.values()):,} hedged", file=sys.stderr)
        raise SystemExit

    base, pdf = sys.argv[1], sys.argv[2]
    want = [int(a) for a in sys.argv[3:]] or hebrew(base)
    cf = f"{base}/data/rule.json"
    cut = ({int(k): v for k, v in json.load(open(cf)).items()}
           if os.path.exists(cf) else book.cuts(pdf))
    if not os.path.exists(cf):
        json.dump(cut, open(cf, "w"))
    # Re-rendering a page or two must not erase the record of the other
    # hundred and forty. The index is the only account of which strips exist
    # and which lines are in each, and `merge` reads it to know what to gather.
    ix = f"{base}/data/eyes/index.json"
    idx = render(pdf, want, f"{base}/data/eyes", cut)
    if os.path.exists(ix):
        idx = {**json.load(open(ix, encoding="utf-8")),
               **{str(k): v for k, v in idx.items()}}
    json.dump(idx, open(ix, "w"), ensure_ascii=False)
    print(f"{len(idx)} pages, {sum(len(v['files']) for v in idx.values())} strips",
          file=sys.stderr)
