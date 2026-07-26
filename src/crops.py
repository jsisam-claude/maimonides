#!/usr/bin/env python3
"""Cut the page open where the reading failed, so the ink can speak for itself.

An earlier version of this file said the residue of doubtful words was ink that
was genuinely ambiguous, and that no further reasoning over the readings could
settle it. That was wrong, and the crops themselves are what disproved it: sent
to a reader that could see, words the print sets perfectly cleanly — ‏בהקדמה‎,
‏משתתף‎, ‏מאמינים‎ — came back correct at once, having defeated all three machine
readings. The residue was not ambiguity. It was three weak readers failing
together, and the answer was a fourth reader that could look (`eyes.py`). It
cut the doubtful words from five thousand to two.

What is left after that really is thin, and it is a different kind of thin:
proper names, place names, and the Judeo-German of the 1848 title matter —
‏ווערבלונר‎, ‏דלייפצג‎, ‏קרשקש‎, ‏דמיין‎ — words no Hebrew lexicon can confirm
because they are not Hebrew words. About those the edition has nothing further
to say, and pretending otherwise would be the one dishonest move available to
it. So it says what it read, and prints the ink beside it.

That is this module's two jobs, which are the same job at two sizes.

*The footnote.* For every word the edition is still unsure of — the ones
arbitration could not decide, and the ones the fourth reader flagged as it went
— cut that word alone out of the page at printing resolution and carry it into
the edition as an image beside the printed guess. Tight, not a band: the
context is already there, in the line of the edition the note hangs from, and
what the reader needs is the letter-shapes. About eight hundred words, under a
kilobyte each.

*The worklist.* The wider question — which of several candidate readings is
right — still wants the whole line, because what settles ‏רבר‎ against ‏דבר‎ is
the sense of the clause. `cut` and `sheet` build that: the band, marked
underneath, with what each reading returned set below it.

Geometry comes from the publisher's text layer, which is the one reading of
this book that carries coordinates: `pdftotext -bbox-layout` gives a box per
glyph, `layer.chunks` groups the letter-spaced ones back into words, and
`book.read` has already decided which lines are Kaspi's. The arbitrated text
has drifted from that backbone — words were inserted, quotations were replaced
wholesale — so the two are aligned with the same routine the ensemble uses
rather than assumed to be parallel.

Nothing here is a correction. This module only shows.

Dependencies: `pdftoppm` from poppler-utils, and Pillow, which the OCR stage
already needs.
"""
from __future__ import annotations

import base64
import collections
import io
import json
import os
import subprocess
import sys
import tempfile
from pathlib import Path

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import book                                      # noqa: E402
import ensemble                                  # noqa: E402
import measure                                   # noqa: E402
import ocrqual                                   # noqa: E402
import repair                                    # noqa: E402

DPI = 600          # what the volume was printed at, near enough
PAD = 18           # px of paper kept above and below the line
SIDE = 520         # px of neighbouring text kept on each side, for context
RULE = 7           # px of the marker drawn under the word in question
MINLEN = 4         # a two-letter crop tells the eye nothing

# The footnote crop. A word alone, close-shaved, at the smallest size its
# letters survive: this one travels inside the edition and there are eight
# hundred of it, so every byte is paid for eight hundred times. The numbers are
# measured rather than chosen — 56 px of height is where ‏ד‎ and ‏ר‎ stay apart
# on a screen, and four grey levels is where the type stops looking like type.
SHAVE = 8          # px of paper around the word — enough that no stroke is clipped
TALL = 56          # px of height, after scaling; the ceiling, not a target
GREYS = 4          # ink, paper, and two levels of the antialiasing between them
MINHEB = 2         # a one-letter flag is punctuation or scanner dirt, not a word


def raster(pdf: str, page: int, dpi: int = DPI, gray: bool = True):
    """The page as an image, at the resolution the type was cut for.

    Grey by default: the volume is black type on paper and the scan's colour
    channels carry nothing but their own noise, so asking for three of them
    triples the memory to hold a 5,100 × 7,000 page and buys nothing. `cut`
    converts back up where it needs to draw in red.
    """
    from PIL import Image

    with tempfile.TemporaryDirectory() as tmp:
        subprocess.run(["pdftoppm", "-r", str(dpi), *(["-gray"] if gray else []),
                        "-png", "-f", str(page), "-l", str(page), pdf, f"{tmp}/p"],
                       check=True)
        f = next(Path(tmp).glob("p-*.png"))
        img = Image.open(f)
        img.load()
        return img


def cut(img, glyphs, dpi: int = DPI):
    """The word's line, cropped around it and marked underneath.

    The crop is a band, not a box, because a word out of its line is unreadable
    even to someone who knows the hand: what settles ‏רבר‎ against ‏דבר‎ is
    usually the sense of the clause, and the clause has to be in the picture.
    """
    from PIL import Image, ImageDraw

    s = dpi / 72.0
    x0 = min(g.x0 for g in glyphs) * s
    x1 = max(g.x1 for g in glyphs) * s
    y0 = min(g.y0 for g in glyphs) * s
    y1 = max(g.y1 for g in glyphs) * s

    left = max(0, int(x0 - SIDE))
    right = min(img.size[0], int(x1 + SIDE))
    top = max(0, int(y0 - PAD))
    bottom = min(img.size[1], int(y1 + PAD + RULE + 4))

    band = img.crop((left, top, right, bottom)).convert("RGB")
    draw = ImageDraw.Draw(band)
    draw.rectangle([x0 - left, bottom - top - RULE - 2,
                    x1 - left, bottom - top - 2], fill=(200, 30, 30))
    return band


def png(img, width: int = 900) -> str:
    """The crop as a data URL, so the sheet is one file with nothing beside it."""
    from PIL import Image

    if img.size[0] > width:
        img = img.resize((width, max(1, round(img.size[1] * width / img.size[0]))),
                         Image.LANCZOS)
    buf = io.BytesIO()
    img.save(buf, "PNG", optimize=True)
    return "data:image/png;base64," + base64.b64encode(buf.getvalue()).decode()


def word(img, glyphs, dpi: int = DPI) -> str:
    """One word, alone, as small as it can be and still be read.

    This is the crop that travels: it goes into the edition itself, under the
    word it belongs to, so a reader who distrusts the transcription can check
    the letters without leaving the page. Nothing else needs to be in it. The
    band `cut` makes exists to supply context; here the context is the sentence
    the note hangs from, already set in type two lines above.

    Three reductions, in the order that costs least. Grey rather than colour,
    because the page is black on cream and the colour channels are scanner
    noise. Scaled to where the letters stop being distinguishable and no
    further. Then quantised to four levels, which is what a printed letter
    actually has — ink, paper, and the edge between them — and is where PNG's
    filters begin to work properly on it. Together: about 850 bytes a word,
    against 40 kB for the same crop taken naively.
    """
    from PIL import Image

    s = dpi / 72.0
    box = (max(0, int(min(g.x0 for g in glyphs) * s) - SHAVE),
           max(0, int(min(g.y0 for g in glyphs) * s) - SHAVE),
           min(img.size[0], int(max(g.x1 for g in glyphs) * s) + SHAVE),
           min(img.size[1], int(max(g.y1 for g in glyphs) * s) + SHAVE))
    c = img.crop(box).convert("L")
    if c.size[1] > TALL:
        c = c.resize((max(1, round(c.size[0] * TALL / c.size[1])), TALL),
                     Image.LANCZOS)
    buf = io.BytesIO()
    c.quantize(colors=GREYS, dither=Image.NONE).save(buf, "PNG", optimize=True)
    return "data:image/png;base64," + base64.b64encode(buf.getvalue()).decode()


def heb(text: str) -> str:
    """The word reduced to the letters an identity can be argued about."""
    return ocrqual.fold("".join(ocrqual.LETTERS.findall(text)))


def flags(base: str) -> dict[int, dict[int, str]]:
    """Every word the edition should print its own ink beside, by page.

    Two sources, and they mean different things, which is why neither is asked
    to stand for the other. A `doubt` token is a place where the arbitration
    ran out of evidence: no reading was a Hebrew word and no single repair made
    one. A hedged form is a place where the reader who could actually see the
    page said so — ⟪ ⟫ around its own best guess — and that reader's doubt is
    worth at least as much as the machinery's, since it is the only one of the
    four with eyes.

    The footnote is the same in both cases because it says the same thing: here
    is what we read, here is the ink, judge for yourself. Which is also why this
    does not route through `why`: the mark on the word in the text says how the
    word was chosen, and the note says look at it yourself, and those are two
    different statements about one word.

    A flag shorter than two Hebrew letters is dropped. Most of them are a
    stray point or a fragment of the scanner's furniture, and an image of a
    comma answers no question anyone has.

    And a hedge is dropped where its form is not unique on its page. `eyes.py`
    records the *form* the fourth reader hedged over, not its position, for
    reasons given there — a position would have to survive two alignments. The
    price shows up here: a hedge over ‏זה‎ on a page that sets ‏זה‎ fourteen
    times identifies fourteen words, and the edition then prints fourteen
    pictures of a word nobody doubts. Which of them was meant is not recoverable
    from a form, so the honest reading of the evidence is that the hedge locates
    nothing and the edition should say nothing. Measured on this volume the rule
    costs 68 hedges and saves 66 spurious footnotes, and the 66 are concentrated
    in exactly the commonest words — ‏זה‎, ‏לו‎, ‏בזה‎, ‏אשר‎, ‏לא‎ — where a
    footnote is not merely useless but misleading, because a mark on a word is
    itself a claim that there is something to look at.
    """
    data = json.load(open(f"{base}/data/ensemble.json", encoding="utf-8"))
    layers = json.load(open(f"{base}/data/book_layer.json", encoding="utf-8"))["pages"]
    try:
        hedged = json.load(open(f"{base}/data/eyes_hedged.json", encoding="utf-8"))
    except FileNotFoundError:
        hedged = {}
    keep = {p["page"] for p in layers
            if measure.hebrew(" ".join(t for t, _ in p["body"]))}

    out: dict[int, dict[int, str]] = {}
    for p in data["pages"]:
        if p["page"] not in keep:
            continue
        form = [heb(t) for t, _ in p["body"]]
        once = collections.Counter(form)
        hed = {h for h in map(heb, hedged.get(str(p["page"]), ()))
               if len(h) >= MINHEB and once[h] == 1}
        at = {i: t for i, ((t, why), f) in enumerate(zip(p["body"], form))
              if len(f) >= MINHEB and (why == ensemble.DOUBT or f in hed)}
        if at:
            out[p["page"]] = at
    return out


def ink(at: list[int], i: int, upto: int) -> range:
    """The backbone words token *i* was read from.

    Almost always exactly one. It is more when the repair pass joined a word the
    scanner had broken in two: the joined token keeps the first half's position,
    and the second half leaves no token of its own, so the ink runs from here to
    wherever the next surviving token starts. Nothing needs to be stored for
    that — the gap in the sequence *is* the record of it.
    """
    hi = next((a for a in at[i + 1:] if a >= 0), upto)
    return range(at[i], max(at[i] + 1, hi))


def cutouts(base: str, pdf: str) -> dict[str, dict[str, str]]:
    """The flagged words as images, keyed by page and by position in the book.

    Keyed by position rather than by form, because two instances of one form on
    one page are two pieces of ink and the whole point of the note is that the
    reader sees this one.
    """
    want = flags(base)
    data = json.load(open(f"{base}/data/ensemble.json", encoding="utf-8"))
    where = {p["page"]: p["at"] for p in data["pages"]}

    pages = sorted(want)
    geo = glyphs(book.read(pdf, book.cuts(pdf, pages=pages)))
    out: dict[str, dict[str, str]] = {}
    for k, n in enumerate(pages, 1):
        if k % 20 == 0:
            print(f"  ...{k}/{len(pages)} pages", file=sys.stderr, flush=True)
        at, gs, img, got = where[n], geo.get(n, []), None, {}
        for i in sorted(want[n]):
            if at[i] < 0:
                continue           # a word only one reader saw; there is no box
            span = [g for j in ink(at, i, len(gs)) if j < len(gs) for g in gs[j]]
            if not span:
                continue
            img = raster(pdf, n) if img is None else img
            got[str(i)] = word(img, span)
        if got:
            out[str(n)] = got
    return out


def readings(base: str, page: int, backbone: list[str]) -> list[dict[int, str]]:
    """What each Tesseract pass has at each position of the layer's reading."""
    out = []
    for f in ("book_tess.json", "book_tess300.json"):
        other = ensemble.reading(f"{base}/data/{f}").get(page, "").split()
        if other:
            out.append(ensemble.against(backbone, other)[0])
    return out


def glyphs(pages: list[book.Page]) -> dict[int, list[list]]:
    """Every Kaspi word of every page, in backbone order, with its geometry."""
    return {p.page: [g for ln in p.body for g in ln.word] for p in pages}


def pick(data: dict, keep: set[int], want: str, n: int, seen: set[str]) -> list[tuple]:
    """Flagged words worth a human's time.

    Three filters and a stride. Only the Hebrew commentary pages, because the
    title page and Werbluner's German are not Kaspi and their damage is not the
    edition's problem; only words long enough for a crop to be worth looking
    at; no word twice, since the second instance of a confusion asks the same
    question as the first. Then an even stride through what is left, so the
    sample is of the volume rather than of its first quire.
    """
    got = []
    for p in data["pages"]:
        if p["page"] not in keep:
            continue
        for i, (text, why) in enumerate(p["body"]):
            if why != want:
                continue
            bare = ocrqual.fold("".join(ocrqual.LETTERS.findall(text)))
            if len(bare) < MINLEN or bare in seen:
                continue
            seen.add(bare)
            got.append((p["page"], i, text, why))
    if len(got) <= n:
        return got
    step = len(got) / n
    return [got[int(k * step)] for k in range(n)]


def ask(base: str, pdf: str, want: dict[str, int]) -> list[dict]:
    """One question per flagged word: the ink, the readings, and the verdict."""
    data = json.load(open(f"{base}/data/ensemble.json", encoding="utf-8"))
    layers = json.load(open(f"{base}/data/book_layer.json", encoding="utf-8"))["pages"]
    corpus = json.load(open(f"{base}/data/corpus.json", encoding="utf-8"))
    lex = ensemble.lexicon(corpus)
    spine = {p["page"]: " ".join(t for t, _ in p["body"]).split() for p in layers}

    tab = {a: set(b) for a, b in data.get("confusions", {}).items()}
    keep = {p["page"] for p in layers
            if measure.hebrew(" ".join(t for t, _ in p["body"]))}

    seen: set[str] = set()
    chosen = [w for kind, n in want.items() for w in pick(data, keep, kind, n, seen)]
    pages = sorted({p for p, *_ in chosen})
    geo = glyphs(book.read(pdf, book.cuts(pdf, pages=pages)))

    out = []
    for n in pages:
        here = [c for c in chosen if c[0] == n]
        arb = [t for t, _ in next(p for p in data["pages"] if p["page"] == n)["body"]]
        back = spine.get(n, [])
        # The arbitrated text is not the backbone any more; find the backbone
        # position of each flagged word rather than trusting the index.
        to = {a: b for a, b in ensemble.align(arb, back) if a is not None and b is not None}
        tess = readings(base, n, back)
        img = raster(pdf, n)
        for _, i, text, why in here:
            j = to.get(i)
            if j is None or j >= len(geo.get(n, ())) or not geo[n][j]:
                continue
            bare = ocrqual.fold("".join(ocrqual.LETTERS.findall(text)))
            out.append({
                "page": n, "folio": next(
                    (p["folio"] for p in layers if p["page"] == n), None),
                "word": text, "why": why,
                "cand": [c for c in ([back[j]] + [t.get(j) for t in tess]) if c],
                "crop": png(cut(img, geo[n][j])),
                # What the repair pass considered and would not commit to. This
                # is the substance of the question: not "is this word wrong"
                # but "is it one of these, and which".
                "near": [repair.spell(w) for w in
                         sorted(repair.variants(bare, tab, 2) & lex)][:5],
            })
    return out


SHEET = """<!DOCTYPE html><html lang="he" dir="rtl"><meta charset="utf-8">
<title>מלים שלא הוכרעו — עמודי כסף</title>
<style>
 :root{color-scheme:light}
 body{margin:0;padding:2.2rem 1.4rem 4rem;background:#faf8f4;color:#1a1713;
      font:16px/1.65 "Frank Ruehl CLM",David,"Times New Roman",serif}
 h1{font-size:1.5rem;font-weight:600;margin:0 0 .3rem;letter-spacing:.01em}
 p.lead{max-width:44rem;margin:0 auto 2.2rem;color:#4a443c;font-size:.95rem}
 h1,p.lead{text-align:center}
 .card{max-width:56rem;margin:0 auto 1.6rem;background:#fff;border:1px solid #e6e0d6;
       border-radius:10px;overflow:hidden;box-shadow:0 1px 2px rgba(0,0,0,.04)}
 .crop{display:block;width:100%;background:#fff}
 .meta{display:flex;flex-wrap:wrap;gap:.5rem 1.6rem;align-items:baseline;
       padding:.75rem 1rem;border-top:1px solid #efeae1;font-size:.9rem}
 .tag{font:600 .72rem/1 ui-sans-serif,system-ui;letter-spacing:.06em;
      text-transform:uppercase;padding:.28rem .5rem;border-radius:4px;
      background:#f2ede4;color:#6b6255}
 .tag.doubt{background:#fdeceb;color:#a02a20}
 .tag.keep{background:#fdf3e0;color:#8a5a10}
 .tag.fix{background:#eaf1fb;color:#1f4f8f}
 .k{color:#7a7268;font-size:.8rem}
 b{font-weight:600}
 .cand b{margin-inline-end:.9rem}
 .near b{color:#1f4f8f}
 .num{margin-inline-start:auto;color:#a09789;font-size:.8rem;font-variant-numeric:tabular-nums}
</style>
<h1>מלים שלא הוכרעו</h1>
<p class="lead">כל שורה: הדפוס עצמו, ותחתיו מה שקראו שלושת העדים, מה שנדפס
במהדורה, והצורות הקרובות שהמכונה שקלה ולא הכריעה ביניהן. הקו האדום מסמן את
המלה הנדונה.</p>
__CARDS__
"""


def sheet(items: list[dict]) -> str:
    """The worklist as one self-contained page: ink first, argument under it."""
    def esc(s):
        return (s or "").replace("&", "&amp;").replace("<", "&lt;").replace(">", "&gt;")

    cards = []
    for k, it in enumerate(items, 1):
        cand = " ".join(f"<b>{esc(c)}</b>" for c in it["cand"])
        near = (" ".join(f"<b>{esc(w)}</b>" for w in it["near"])
                if it["near"] else "<span class=k>אין</span>")
        cards.append(
            f'<div class=card><img class=crop src="{it["crop"]}" alt="">'
            f'<div class=meta><span class="tag {it["why"]}">{it["why"]}</span>'
            f'<span class=cand><span class=k>הקריאות</span> {cand}</span>'
            f'<span><span class=k>נדפס</span> <b>{esc(it["word"])}</b></span>'
            f'<span class=near><span class=k>קרוב</span> {near}</span>'
            f'<span class=num>#{k} · דף {it["folio"] or it["page"]}</span>'
            f'</div></div>')
    return SHEET.replace("__CARDS__", "\n".join(cards))


if __name__ == "__main__":
    base = sys.argv[1] if len(sys.argv) > 1 else "."
    pdf = sys.argv[2]
    if len(sys.argv) > 3 and sys.argv[3] == "notes":
        out = cutouts(base, pdf)
        dst = f"{base}/data/crops.json"
        json.dump(out, open(dst, "w", encoding="utf-8"), ensure_ascii=False)
        n = sum(len(v) for v in out.values())
        print(f"{n:,} words cropped from {len(out)} pages, "
              f"{os.path.getsize(dst)/1024:,.0f} kB -> {dst}", file=sys.stderr)
        raise SystemExit
    want = {ensemble.DOUBT: 6, ensemble.KEEP: 3, ensemble.FIX: 3}
    items = ask(base, pdf, want)
    dst = f"{base}/out/AmudeiKesef_adjudication.html"
    open(dst, "w", encoding="utf-8").write(sheet(items))
    print(f"{len(items)} words cropped -> {dst}", file=sys.stderr)
