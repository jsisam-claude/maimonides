"""The sentences in which a word came out as something that is not a word.

Every other measurement in this edition compares one reading against another and
asks which is likelier. This one asks nothing of any witness. A Hebrew word with
a comma, a caret or a full stop wedged between two of its letters is wrong on its
face — ‏הא.דם‎ is not a spelling of ‏האדם‎, it is a failure — and it stays wrong
whatever the modern editor's manuscripts happen to read at that place. So this is
the one class of error in the volume that needs no gold, no lexicon and no vote to
establish, and the only one that can be quoted over the whole book rather than
over the 1,241 words the gold covers.

The mark has to be foreign to Hebrew orthography to count. Geresh and gershayim
sit inside words by design — ‏ר״ל‎, ‏בפ״ע‎, ‏ס׳‎ are abbreviations, not damage — and
an earlier version of this test that did not know that reported sixty-odd
abbreviations as broken words, which is the same mistake as the lexicon licensing
a split: a rule confident about a language it has not been told the rules of.

Shown as sentences because a word alone cannot be judged. What is visibly wrong
with ‏למנר,נם,‎ is that no clause can be built round it, and the reader can only
see that with the clause in front of them; the crop underneath is the same
argument made against the ink.
"""
from __future__ import annotations

import base64
import io
import json
import os
import re
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import book                                        # noqa: E402
import crops                                       # noqa: E402

HEB = re.compile(r"[א-ת]")
GERESH = "\"'׳״’”"                 # abbreviation marks: inside a word by design
NIQQUD = "֑-ׇ"                     # points and accents, likewise
BROKEN = re.compile(rf"[א-ת][^\sא-ת{re.escape(GERESH)}{NIQQUD}-]+[א-ת]")
STOP = re.compile(r"[.:?!]$")      # as much of a sentence as this text marks
REACH = 22                         # words either side, when nothing marks the end
HEBREW = 0.9                       # of a page's letters, for it to be Kaspi's

CSS = """
:root{--ink:#1a1a1a;--pale:#8a8580;--paper:#faf8f4;--line:#e4ded4;--bad:#c81e1e}
*{box-sizing:border-box}
body{margin:0;background:var(--paper);color:var(--ink);
 font:16px/1.65 Georgia,'Times New Roman',serif}
main{max-width:60rem;margin:0 auto;padding:3rem 1.5rem 6rem}
h1{font-size:1.9rem;margin:0 0 .4rem;letter-spacing:-.01em}
h2{font-size:1.1rem;margin:3rem 0 .8rem;padding-bottom:.35rem;
 border-bottom:1px solid var(--line)}
.lede{color:var(--pale);margin:0 0 2rem;max-width:46rem}
.k{font:12px/1.5 ui-monospace,SFMono-Regular,Menlo,monospace;color:var(--pale)}
.num{font-variant-numeric:tabular-nums;font-weight:600}
.box{border:1px solid var(--line);background:#fff;border-radius:.4rem;
 padding:1rem 1.2rem;margin:1.5rem 0}
.heb{direction:rtl;unicode-bidi:isolate;font-size:1.22rem;line-height:2}
figure{margin:0 0 2.4rem;padding-bottom:1.6rem;border-bottom:1px solid var(--line)}
figure:last-of-type{border:0}
.bad{color:var(--bad);font-weight:700;border-bottom:2px solid var(--bad);
 padding-bottom:1px}
img.band{width:100%;max-width:52rem;display:block;margin:.9rem 0 .3rem;
 border:1px solid var(--line);border-radius:.25rem;background:#fff}
figcaption{color:var(--pale);font:12px/1.5 ui-monospace,Menlo,monospace}
footer{margin-top:4rem;color:var(--pale);font-size:.85rem}
"""


def esc(s: str) -> str:
    return (s.replace("&", "&amp;").replace("<", "&lt;").replace(">", "&gt;"))


def kaspi(page: dict) -> bool:
    """Is this one of Kaspi's pages, or Werbluner's German?

    Twenty-one of the volume's leaves are the editor's own German introduction
    and his list of subscribers, set in Fraktur. Tesseract reads Fraktur as
    Hebrew-adjacent noise, and every word of it would land in this report and
    swamp the thing it is meant to show. The test is the page's own letters:
    Kaspi's pages are at least nine parts in ten Hebrew, the German ones are
    never more than half, and nothing in the volume falls between.
    """
    text = " ".join(t for t, _ in page["body"])
    letters = re.findall(r"[^\W\d_]", text)
    return len(HEB.findall(text)) >= HEBREW * max(1, len(letters))


def sentence(words: list[str], i: int) -> tuple[int, int]:
    """The span of running text a reader needs to see that word ``i`` is wrong.

    The print punctuates lightly and the scan loses some of what there is, so a
    full stop cannot be waited for: the span runs to the nearest sentence mark or
    to ``REACH`` words, whichever comes first. Erring short would hide the
    evidence and erring long would bury it.
    """
    lo = i
    while lo > 0 and i - lo < REACH and not STOP.search(words[lo - 1]):
        lo -= 1
    hi = i + 1
    while hi < len(words) and hi - i < REACH and not STOP.search(words[hi - 1]):
        hi += 1
    return lo, hi


def find(data: dict) -> list[dict]:
    """Every word in Kaspi's text with a foreign mark inside its letters."""
    out = []
    for p in data["pages"]:
        if not kaspi(p):
            continue
        words = " ".join(t for t, _ in p["body"]).split()
        for i, w in enumerate(words):
            if HEB.search(w) and BROKEN.search(w):
                lo, hi = sentence(words, i)
                out.append({"page": p["page"], "folio": p.get("folio"), "at": i,
                            "word": w, "lo": lo, "hi": hi,
                            "words": words[lo:hi], "mark": i - lo})
    return out


def ink(pdf: str, data: dict, hits: list[dict]) -> None:
    """Cut the band round each failure, one raster per page rather than per word."""
    seat = {p["page"]: p["at"] for p in data["pages"]}
    pages = sorted({h["page"] for h in hits})
    geo = crops.glyphs(book.read(pdf, book.cuts(pdf, pages=pages)))
    for n in pages:
        boxes, at = geo.get(n, []), seat.get(n, [])
        img = None
        for h in (h for h in hits if h["page"] == n):
            i = h["at"]
            if i >= len(at) or at[i] < 0:
                continue
            g = [x for k in crops.ink(at, i, len(boxes)) if k < len(boxes)
                 for x in boxes[k]]
            if not g:
                continue
            img = crops.raster(pdf, n) if img is None else img
            h["band"] = crops.png(crops.cut(img, g))


def figures(hits: list[dict]) -> str:
    out = []
    for h in hits:
        run = " ".join(
            f'<span class="bad">{esc(w)}</span>' if k == h["mark"] else esc(w)
            for k, w in enumerate(h["words"]))
        band = (f'<img class="band" src="{h["band"]}" alt="">'
                if h.get("band") else "")
        folio = f' · דף {h["folio"]}' if h.get("folio") else ""
        out.append(f'<figure><div class="heb">{run}</div>{band}'
                   f'<figcaption>scan p{h["page"]}{folio} · '
                   f'word {h["at"]}</figcaption></figure>')
    return "".join(out)


def build(base: str = ".", pdf: str = "") -> str:
    data = json.load(open(f"{base}/data/ensemble.json", encoding="utf-8"))
    hits = find(data)
    pages = [p for p in data["pages"] if kaspi(p)]
    total = sum(1 for p in pages for t, _ in p["body"]
                for w in t.split() if HEB.search(w))
    if pdf:
        ink(pdf, data, hits)
    shot = sum(1 for h in hits if h.get("band"))
    return f"""<!doctype html><html lang="en"><head><meta charset="utf-8">
<meta name="viewport" content="width=device-width,initial-scale=1">
<title>Words that completely failed</title><style>{CSS}</style></head>
<body><main>

<h1>Words that completely failed</h1>
<p class="lede">Not a variant, not a disagreement with another edition — a token
the edition emitted that is not a word in any spelling. Shown in its sentence,
with the ink beneath. 1848 Frankfurt, ʿAmudei Kesef.</p>

<div class="box"><p style="margin:0">A Hebrew word with a comma, a caret or a
full stop between two of its letters is wrong on its face, so this is the one
error in the volume that needs no gold, no lexicon and no vote to establish —
and therefore the only one that can be counted over the whole book instead of
over the 1,241 words the gold covers. Geresh and gershayim do not count: ‏ר״ל‎
and ‏ס׳‎ are abbreviations, and a test that did not know that reported sixty of
them as damage.</p></div>

<p><span class="num">{len(hits)}</span> of
<span class="num">{total:,}</span> Hebrew-bearing words in Kaspi's text —
<span class="num">{len(hits) / max(1, total):.2%}</span> — across
<span class="num">{len({h['page'] for h in hits})}</span> of the
<span class="num">{len(pages)}</span> Hebrew pages. Werbluner's German
introduction and his subscriber list are excluded: Tesseract reads Fraktur as
noise, and all of it would land here.</p>

<h2>The sentences</h2>
{figures(hits)}

<footer>Bands cut at 600 dpi from the Frankfurt 1848 scan, marked in red beneath
the word in question; {shot} of {len(hits)} could be located — the rest are
words no reading of the volume carries coordinates for. Generated by
<span class="k">src/broken.py</span>.</footer>
</main></body></html>"""


if __name__ == "__main__":
    base = sys.argv[1] if len(sys.argv) > 1 else "."
    pdf = sys.argv[2] if len(sys.argv) > 2 else ""
    dst = f"{base}/out/AmudeiKesef_broken.html"
    open(dst, "w", encoding="utf-8").write(build(base, pdf))
    print(f"{os.path.getsize(dst) / 1024:,.0f} kB -> {dst}", file=sys.stderr)
