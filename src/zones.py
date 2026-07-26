#!/usr/bin/env python3
"""Split a page of the 1848 print into its typographic zones.

The volume sets two texts on one page in two different faces. Kaspi's
commentary is square Hebrew; Werbluner's editorial notes below the rule are
Rashi semi-cursive. Tesseract's `heb` model knows only square script, so when
the whole page is fed to it the notes come back not as noise but as a
*substitution cipher* — Rashi alef read as ``6``, he as ``ס``, resh as ``כ`` —
and that garbage was being concatenated onto the commentary. Two errors at
once: the commentary's quality figure was wrecked by text that is not the
commentary, and Werbluner's notes were being attributed to Kaspi.

So the zones must be separated before a single character is read. The
compositor marks the boundary with a horizontal rule, and a rule is the
easiest thing on the page to find — provided you look for the right property.
Its *length* is not it: on this scan the rules are broken and dotted, and the
longest unbroken black run in a rule (460 px) is no larger than one inside a
line of text. What separates them is density. Measure each row's ink extent,
from its leftmost inked pixel to its rightmost, and the fraction of that
extent which is inked:

    a line of body text    extent 2174 px   fill 0.45
    a line of Rashi note   extent 1894 px   fill 0.13
    the rule               extent  528 px   fill 0.95

Nothing else on a page of type is 95 % solid across half an inch. Runs are
computed with a small gap tolerance so a broken rule still reads as one.

Everything here is pure Python over a raw pixel buffer — no OpenCV, no NumPy.
A 2780x4563 page costs about a second, which is nothing beside the OCR that
follows.

Dependencies: none beyond Pillow, already required to rasterise the scan.
"""
from __future__ import annotations

from dataclasses import dataclass

INK = 0.60         # threshold this far from paper towards the darkest ink
GAP = 8            # px; a rule broken by less than this is still one rule
EXTENT = 0.10      # a rule reaches at least this fraction of the measure
FILL = 0.80        # ...and is at least this solid across that reach
THICK = 0.005      # ...and is no thicker than this fraction of the page
CLEAR = 0.05       # ...and has paper this clear on both sides of it
MARGIN = 0.06      # ignore this much at each edge: scan shadow, binding


@dataclass(frozen=True)
class Zone:
    top: int
    bottom: int
    kind: str      # "body" (square script) | "notes" (Rashi script)

    @property
    def height(self) -> int:
        return self.bottom - self.top


def threshold(img) -> int:
    """Where ink stops and paper starts, for this scan.

    A fixed cut-off cannot survive rasterisation at different resolutions: a
    hairline rule that is solid black at 600 dpi is averaged with the paper
    around it at 150 dpi and comes back mid-grey, so a constant threshold sees
    the body type and misses the rule — which is the one thing being looked
    for. Take paper to be the commonest tone on the page and ink the darkest
    percentile, and cut between them.
    """
    hist = img.convert("L").histogram()
    total = sum(hist)
    paper = max(range(256), key=lambda v: hist[v])
    seen, dark = 0, 0
    for v in range(256):                      # 1st percentile from the dark end
        seen += hist[v]
        if seen >= total * 0.01:
            dark = v
            break
    return max(1, int(dark + (paper - dark) * INK))


def _solid(px, y: int, x0: int, x1: int, ink: int) -> tuple[int, float]:
    """As _row, but over the longest gap-tolerant black run only.

    A rule sharing its row with a stray speck would otherwise have its extent
    stretched to the speck and its fill diluted.
    """
    best = (0, 0)                      # length, start
    cur = start = gap = 0
    for x in range(x0, x1):
        if px[x, y] < ink:
            cur += gap + 1
            gap = 0
            if cur > best[0]:
                best = (cur, x - cur + 1)
        else:
            gap += 1
            if gap > GAP:
                cur, gap, start = 0, 0, x
    if not best[0]:
        return 0, 0.0
    n = sum(1 for x in range(best[1], best[1] + best[0]) if px[x, y] < ink)
    return best[0], n / best[0]


def rules(img) -> list[int]:
    """Mid-row of every horizontal rule on the page, top to bottom."""
    w, h = img.size
    ink = threshold(img)
    px = img.convert("L").load()
    x0, x1 = int(w * MARGIN), int(w * (1 - MARGIN))
    measure = x1 - x0
    thick = max(2, int(h * THICK))

    hit = []
    for y in range(h):
        ext, fill = _solid(px, y, x0, x1, ink)
        if ext >= measure * EXTENT and fill >= FILL:
            hit.append(y)

    def clear(y: int) -> float:
        """Ink in row *y*, as a fraction of the measure. Off-page counts as clear."""
        if not 0 <= y < h:
            return 0.0
        return sum(1 for x in range(x0, x1) if px[x, y] < ink) / measure

    # How far to stand back before asking whether the page is clear. In page
    # fractions, not pixels: a fixed offset that clears the halo of a rule at
    # 150 dpi lands inside it at 600 dpi, and every rule in the book is then
    # rejected as crowded by its own antialiasing.
    off = [max(3, int(h * f)) for f in (0.0035, 0.0044, 0.0053)]

    out, group = [], []
    for y in hit + [1 << 30]:
        if group and y - group[-1] > 3:
            top, bot = group[0], group[-1]
            # A rule is thin, and it is *alone*: the compositor leaves paper
            # above and below it. Without that second test the densest lines of
            # display type pass — they are as solid as a rule across a short
            # run — but they have the rest of their own line pressing against
            # them, which no rule ever does.
            if (len(group) <= thick
                    and max(clear(top - d) for d in off) < CLEAR
                    and max(clear(bot + d) for d in off) < CLEAR):
                out.append(group[len(group) // 2])
            group = []
        if y < h:
            group.append(y)
    return out


def ink(img, y0: int, y1: int, step: int = 3) -> int:
    """Roughly how much ink lies in a horizontal band. Sampled, not counted.

    Only ever compared against a small threshold — the question asked of it is
    "is there text here or is this the foot of the page", and for that a sample
    every few pixels is as good an answer as every pixel and forty times
    cheaper.
    """
    w, h = img.size
    px, cut = img.convert("L").load(), threshold(img)
    return sum(1 for y in range(max(0, y0), min(h, y1), step)
               for x in range(int(w * MARGIN), int(w * (1 - MARGIN)), 4)
               if px[x, y] < cut)


def zones(img, floor: float = 0.02, least: int = 40) -> list[Zone]:
    """Body above the notes rule, Werbluner's notes below it.

    Not every rule on the page is *the* rule. The compositor also divides
    Kaspi's own text with one — page 8 sets a rule above ‏פתיחה‎, where
    ʿAmudei Kesef turns from its dedication to its introduction — and taking
    the first rule found made that division the boundary between the two texts.
    Sixteen lines of Kaspi were filed as Werbluner's notes, and because the
    fourth reading only ever looks at the body zone, they were never read by
    eye at all: the gold measurement found the passage missing from this
    edition and present in Tesseract, which reads the whole page and knows
    nothing of zones.

    The correction follows from where the apparatus sits. Werbluner's notes are
    at the foot of the page, so the rule that separates them is the *lowest*
    one with anything printed beneath it; a rule above that divides the body
    from itself, and dividing Kaspi from Kaspi is not this function's business.
    The ink test is what keeps a mark near the bottom edge from swallowing the
    apparatus — a boundary with nothing below it is not a boundary.

    Two pages of a hundred and seventy change: page 8, which is the bug, and
    page 156, whose trailing rule is the end of the German afterword.
    """
    h = img.size[1]
    cuts = [y for y in rules(img) if ink(img, y + 4, h) >= least]
    if not cuts:
        return [Zone(0, h, "body")]
    out, y = [], cuts[-1]
    if y > h * floor:
        out.append(Zone(0, y, "body"))
    if h - y > h * floor:
        out.append(Zone(y, h, "notes"))
    return out


def crop(img, z: Zone, pad: int = 10):
    w, h = img.size
    return img.crop((0, max(0, z.top - pad), w, min(h, z.bottom + pad)))


if __name__ == "__main__":
    import sys

    from PIL import Image

    for path in sys.argv[1:]:
        im = Image.open(path)
        print(f"{path}  {im.size[0]}x{im.size[1]}", file=sys.stderr)
        for z in zones(im):
            print(f"   {z.kind:<6} {z.top:>5}-{z.bottom:<5} "
                  f"{z.height / im.size[1]:>6.1%} of page", file=sys.stderr)
