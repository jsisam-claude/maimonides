#!/usr/bin/env python3
"""Read the text layer Hebrewbooks left inside the scan, with its geometry.

The 1848 volume was re-OCR'd here from page images, which was unnecessary
work: the Hebrewbooks PDF already carries a text layer, and it is markedly
better than what Tesseract's `heb` model produces from the same pixels —
9 % of its word-forms are unattested against 24 % for ours. It is not perfect,
and it is not a substitute for collation, but it is the better first reading
and it costs nothing.

It also carries something no plain OCR pass can give: the compositor's own
marking of the lemmata. Where the print sets a quotation from the Guide in the
heavy display face, the type is letter-spaced, and `pdftotext -bbox-layout`
faithfully reports each letter as its own word:

    ל ה ש ת כ ל  ב א ו ר  ה נ ר א ה  ו א ו ת ו  ה א ו ר  ל א  ה י ה  ג ש ם

So a run of single-glyph words *is* a lemma — read off the page rather than
inferred. That is a different and much stronger kind of evidence than the
substring matching in `quote.py`, and it finds lemmata that matching cannot:
a lemma Kaspi abridges, or one the OCR has damaged past the twelve-letter
threshold, is still set in display type and still shows up here.

Two mechanical points about the layer:

* Words arrive in *visual* order with their characters reversed, because the
  producer wrote glyphs left to right. Reversing is nearly enough — but digits
  and Latin runs must be turned back the right way round, and brackets must be
  mirrored, or ``(וקרא`` comes out as ``ארקו)``.
* The folio number printed at the head of the page is its own block. Taking it
  from the layer settles the page-numbering question the scan could not: the
  printed folio is not a fixed offset from the PDF page.

Dependencies: `pdftotext` from poppler-utils. No Python packages.
"""
from __future__ import annotations

import html
import re
import subprocess
from dataclasses import dataclass

WORD = re.compile(r'<word xMin="([\d.-]+)" yMin="([\d.-]+)" '
                  r'xMax="([\d.-]+)" yMax="([\d.-]+)">(.*?)</word>')
LINE = re.compile(r"<line\b[^>]*>(.*?)</line>", re.S)
PAGE = re.compile(r"<page\b[^>]*>(.*?)</page>", re.S)
LTR = re.compile(r"[0-9A-Za-z]+")
BIDI = re.compile("[‎‏‪-‮⁦-⁩]")
MIRROR = str.maketrans("()[]{}<>", ")(][}{><")

DISPLAY = 3        # this many single-glyph words in a row means display type
GAP = 1.6          # a space wider than this many median gaps splits a run


@dataclass(frozen=True)
class Word:
    text: str
    x0: float
    y0: float
    x1: float
    y1: float

    @property
    def size(self) -> float:
        return self.y1 - self.y0


def logical(s: str) -> str:
    """Turn one visually-ordered token the right way round."""
    s = BIDI.sub("", s).translate(MIRROR)[::-1]
    return LTR.sub(lambda m: m.group()[::-1], s)


def words(pdf: str, page: int) -> list[list[Word]]:
    """Every line of *page*, each a list of Words in reading order."""
    xml = subprocess.run(["pdftotext", "-f", str(page), "-l", str(page),
                          "-bbox-layout", "-enc", "UTF-8", pdf, "-"],
                         capture_output=True, text=True, check=True).stdout
    out = []
    for body in LINE.findall(PAGE.search(xml).group(1) if PAGE.search(xml) else ""):
        ws = [Word(logical(html.unescape(t)), float(a), float(b), float(c), float(d))
              for a, b, c, d, t in WORD.findall(body)]
        ws = [w for w in ws if w.text.strip()]
        if ws:
            out.append(sorted(ws, key=lambda w: -w.x1))     # RTL: rightmost first
    return out


def folio(lines: list[list[Word]]) -> int | None:
    """The printed folio number, if the head of the page carries one."""
    if not lines:
        return None
    head = min(lines, key=lambda ln: min(w.y0 for w in ln))
    if len(head) == 1 and head[0].text.isdigit() and len(head[0].text) <= 3:
        return int(head[0].text)
    return None


def _runs(line: list[Word]) -> list[tuple[int, int]]:
    """Index ranges of consecutive single-glyph words."""
    out, start = [], None
    for i, w in enumerate(line + [Word("  ", 0, 0, 0, 0)]):
        if len(w.text) == 1 and w.text.isalpha():
            start = i if start is None else start
        else:
            if start is not None and i - start >= DISPLAY:
                out.append((start, i))
            start = None
    return out


def chunks(line: list[Word]) -> list[tuple[str, list[Word], bool]]:
    """The line's words as they will be set, each with the glyphs it came from.

    A word the compositor letter-spaced arrives from the PDF as one Word per
    glyph. Within such a run the inter-letter distance is even and a real word
    boundary is markedly wider, so the run is cut at the wide gaps; everything
    else is already a word. The third field says whether the word was set in
    display type.

    Handing back the glyphs alongside the text is what lets a caller that needs
    geometry rather than text — src/crops.py, cutting the scan for a human to
    look at — find the ink a given word was read from.
    """
    disp = dict.fromkeys(range(len(line)), False)
    for a, b in _runs(line):
        for i in range(a, b):
            disp[i] = True

    out: list[tuple[str, list[Word], bool]] = []
    i = 0
    while i < len(line):
        if not disp[i]:
            out.append((line[i].text, [line[i]], False))
            i += 1
            continue
        j = i
        while j < len(line) and disp[j]:
            j += 1
        run = line[i:j]
        gaps = [run[k].x0 - run[k + 1].x1 for k in range(len(run) - 1)]
        med = sorted(gaps)[len(gaps) // 2] if gaps else 0.0
        buf = [run[0]]
        for k in range(1, len(run)):
            if gaps[k - 1] > max(med * GAP, med + 1.0):
                out.append(("".join(w.text for w in buf), buf, True))
                buf = [run[k]]
            else:
                buf.append(run[k])
        out.append(("".join(w.text for w in buf), buf, True))
        i = j
    return out


def render(line: list[Word]) -> tuple[str, list[tuple[int, int]]]:
    """The line as text, plus character spans set in display type."""
    out: list[str] = []
    spans: list[tuple[int, int]] = []
    pos, run = 0, None
    for text, _, disp in chunks(line):
        if disp and run is None:
            run = pos
        elif not disp and run is not None:
            spans.append((run, pos - 1))
            run = None
        out.append(text)
        pos += len(text) + 1
    if run is not None:
        spans.append((run, pos - 1))
    return " ".join(out), spans


if __name__ == "__main__":
    import sys

    pdf, page = sys.argv[1], int(sys.argv[2])
    ls = words(pdf, page)
    print(f"folio {folio(ls)}   {len(ls)} lines", file=sys.stderr)
    for ln in ls:
        t, sp = render(ln)
        mark = "".join("^" if any(a <= k < b for a, b in sp) else " "
                       for k in range(len(t)))
        print(f"  {t}", file=sys.stderr)
        if sp:
            print(f"  {mark}", file=sys.stderr)
