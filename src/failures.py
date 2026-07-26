#!/usr/bin/env python3
"""The failed tests, with the ink beside them, so the page can settle it.

Two things in this project are called a test and only one of them is a test of
the reading.

*The gold* is 1,241 words of Kaspi transcribed by hand from a modern critical
edition and never shown to the arbitration. Where the edition disagrees with it,
one of three things is true: the edition misread the 1848 print, the modern
editor read his manuscripts differently from what Frankfurt set, or the two
spell the same word differently. Only the first is an OCR failure, and the three
are indistinguishable in a percentage. They are distinguishable in a photograph,
so each disagreement is printed here beside the ink it is about.

*The unattested-word rate* is not a test of the reading at all — it asks whether
a form is in a lexicon, not whether it is the form on the page — and near the
floor it starts returning the wrong sign. Two classes of its wrong verdicts are
shown, both measured over this volume: repairs it scored as damage, and damage
it would have scored as repair.

Nothing here is an argument. Every row carries the crop, and the reader who
knows the letters can overrule every claim on the page.

Dependencies: none beyond what the crops already cost (Pillow, poppler).
"""
from __future__ import annotations

import html
import json
import sys

CSS = """
:root{--ink:#1b1a17;--pale:#6d6a63;--line:#ddd8cd;--bg:#faf8f3;
      --good:#2f6b46;--bad:#9b3226;--warn:#8a6a1f}
*{box-sizing:border-box}
body{margin:0;background:var(--bg);color:var(--ink);
     font:15px/1.65 "Iowan Old Style","Palatino Linotype",Palatino,Georgia,serif}
main{max-width:56rem;margin:0 auto;padding:3rem 1.5rem 6rem}
h1{font-size:1.7rem;font-weight:600;margin:0 0 .3rem}
h2{font-size:1.15rem;font-weight:600;margin:3.5rem 0 .4rem;
   padding-bottom:.35rem;border-bottom:1px solid var(--line)}
p{margin:.7rem 0;max-width:44rem}
.lede{color:var(--pale)}
.num{font-variant-numeric:tabular-nums}
table{border-collapse:collapse;width:100%;margin:1.4rem 0}
td,th{border-bottom:1px solid var(--line);padding:.55rem .5rem;
      vertical-align:middle;text-align:left}
th{font-size:.75rem;letter-spacing:.06em;text-transform:uppercase;
   color:var(--pale);font-weight:600;border-bottom:1px solid var(--ink)}
.heb{direction:rtl;unicode-bidi:isolate;font-size:1.15rem;
     font-family:"SBL Hebrew","Times New Roman",serif;white-space:nowrap}
.band{display:block;max-width:100%;height:auto;border:1px solid var(--line);
      border-radius:2px;background:#fff}
td.ink{width:52%}
.tag{display:inline-block;font-size:.68rem;letter-spacing:.04em;
     padding:.1rem .4rem;border-radius:2px;white-space:nowrap;
     text-transform:uppercase;font-family:ui-sans-serif,system-ui,sans-serif}
.t-print{background:#e6efe8;color:var(--good)}
.t-ocr{background:#f6e6e3;color:var(--bad)}
.t-open{background:#f4eedd;color:var(--warn)}
.k{font-family:ui-monospace,SFMono-Regular,Menlo,monospace;font-size:.8rem;
   color:var(--pale)}
.grid{display:grid;grid-template-columns:1fr 1fr;gap:1.1rem;margin:1.4rem 0}
figure{margin:0}
figcaption{font-size:.85rem;color:var(--pale);margin-top:.3rem}
.box{border:1px solid var(--line);background:#fff;border-radius:3px;
     padding:.9rem 1.1rem;margin:1.4rem 0}
.rule{margin:2.5rem 0;border:0;border-top:1px solid var(--line)}
footer{margin-top:4rem;color:var(--pale);font-size:.85rem}
"""


def esc(s: str) -> str:
    return html.escape(s or "")


def heb(s: str) -> str:
    return f'<span class="heb">{esc(s)}</span>'


def img(src: str) -> str:
    return f'<img class="band" src="{src}" alt="">' if src else "—"


TAG = {"edition": ("t-print", "print differs"),
       "gold": ("t-ocr", "misread here"),
       "none": ("t-open", "open")}


def verdict(r: dict) -> tuple[str, str]:
    """What the readers of the 1848 print say at exactly this position.

    Not a ruling — the crop is the ruling — but it is positional, which an
    earlier version of this was not. Asking whether a form appears *anywhere on
    the page* is nearly free and nearly worthless: on a page that sets ‏זה‎
    fourteen times it answers yes about a word nobody read. So the three
    readings are aligned to the backbone and asked what they have at this word,
    and the row reports that.

    Three outcomes. The readers here return the edition's form and not the
    gold's: Frankfurt and the modern editor's manuscripts most likely differ,
    and the edition read its own page correctly. A reader here returns the
    gold's form: the edition had the right reading available and did not take
    it, which is a failure of arbitration and the most useful row on the page.
    Neither: the position is genuinely unresolved and is left open.
    """
    return TAG[r.get("backs", "none")]


ETC = {"וכו", "וגו", "וכד", "וגומר"}      # ‏וכו׳‎ — "and so on"


def elisions(base: str) -> set[tuple[str, str]]:
    """Disagreements that exist because the gold abbreviates and the print does not.

    The modern editor writes ‏וכו׳‎ where Frankfurt sets the words out in full.
    The aligner has one gold token and several edition words to pair it with, so
    it pairs the marker with the first of them and charges the edition a
    substitution for a word the gold never claimed to quote — and then charges
    it again for the one or two words that follow before the two texts meet.

    Found by asking the alignment, not a heuristic: a substitution whose gold
    side is an elision marker and whose edition side is not, plus the two pairs
    downstream of it. Returned as ``(gold, edition)`` pairs, which is what the
    rows carry; the forms involved are distinctive enough here that the join is
    exact, and a row this misidentifies would be visible in its own crop.

    Four such pairs, and two of debris. It is a small number and it is reported
    as one — the point is not the size but that the gold and the print are doing
    different things at those six places, and no amount of reading the scan
    correctly would close them.
    """
    import gold as G                                            # noqa: E402
    import ensemble                                             # noqa: E402

    final = json.load(open(f"{base}/data/ensemble.json", encoding="utf-8"))
    book = [w for p in final["pages"] for t, _ in p["body"]
            for w in G.words(t, apparatus=False)]
    out: set[tuple[str, str]] = set()
    for g in json.load(open(f"{base}/data/gold.json", encoding="utf-8")):
        want = G.words(g["text"])
        if G.presence(want, book) < G.FOUND:
            continue
        lo, hi = G.locate(want, book)
        if hi <= lo:
            continue
        seg = book[lo:hi]
        pairs = list(ensemble.align(want, seg))
        for k, (i, j) in enumerate(pairs):
            if i is None or j is None or want[i] == seg[j]:
                continue
            if want[i] in ETC and seg[j] not in ETC:
                out.add((want[i], seg[j]))
                out.update((want[x], seg[y]) for x, y in pairs[k + 1:k + 3]
                           if x is not None and y is not None and want[x] != seg[y])
    return out


def photograph(base: str, pdf: str, rows: list[dict]) -> dict[str, dict]:
    """Cut the ink for every disagreement, including the ones with no coordinates.

    The backbone is the only reading of this volume that carries geometry, so a
    word the backbone never read has ``at == -1`` and no box to crop. Six of the
    seventy-eight disagreements are of that kind, and dropping them would quietly
    photograph only the failures that are easy to photograph — which is the one
    bias a sheet like this cannot afford, since a word no reader placed is more
    likely to be wrong than one three readers placed.

    They are croppable anyway. The crop is a *band* — a strip of the line with
    the neighbours in it — so the strip running from the last positioned word
    before to the first positioned word after must contain the missing word. The
    red rule then spans that strip rather than the word, and the row says so.
    """
    import book, crops                                          # noqa: E402

    data = json.load(open(f"{base}/data/ensemble.json", encoding="utf-8"))
    at = {p["page"]: p["at"] for p in data["pages"]}
    pages = sorted({r["page"] for r in rows})
    geo = crops.glyphs(book.read(pdf, book.cuts(pdf, pages=pages)))

    out: dict[str, dict] = {}
    for n in pages:
        boxes, seat = geo.get(n, []), at.get(n, [])
        img = None
        for r in (r for r in rows if r["page"] == n):
            i = r["tok"]
            if i >= len(seat):
                continue
            if seat[i] >= 0:
                span, sure = crops.ink(seat, i, len(boxes)), True
            else:                                   # between its placed neighbours
                lo = next((seat[j] for j in range(i - 1, -1, -1) if seat[j] >= 0), None)
                hi = next((seat[j] for j in range(i + 1, len(seat)) if seat[j] >= 0), None)
                if lo is None or hi is None:
                    continue
                span, sure = range(lo, max(lo + 1, hi)), False
            g = [x for k in span if k < len(boxes) for x in boxes[k]]
            if not g:
                continue
            img = crops.raster(pdf, n) if img is None else img
            out[f"{n}:{i}"] = {"band": crops.png(crops.cut(img, g)), "sure": sure}
    return out


def gold_rows(rows: list[dict], ink: dict, elide: set = frozenset()) -> str:
    out = []
    for r in rows:
        cls, tag = verdict(r)
        k = f"{r['page']}:{r['tok']}"
        cell = ink.get(k, {})
        saw = " · ".join(dict.fromkeys(r.get("at_all") or [])) or "—"
        loose = ("" if cell.get("sure", True) else
                 "<div class='k'>the backbone did not read this word — the rule "
                 "marks the strip it must lie in, not the word</div>")
        if (r["gold"], r["book"]) in elide:
            cls, tag = "t-print", "gold abbreviates"
        # What the edition actually set, not the form it was compared by. The
        # comparison folds finals and drops points and geresh so that ‏החיבורים‎
        # and ‏החיבורימ‎ cannot count as a difference; printing that folded token
        # in a column headed "read here" shows the reader a spelling no edition
        # contains and invites them to call it an error.
        out.append(
            f'<tr><td class="ink">{img(cell.get("band", ""))}{loose}</td>'
            f"<td>{heb(r.get('set') or r['book'])}"
            f"<div class='k'>this edition · {esc(r['why'])}</div>"
            f"<div class='k' style='margin-top:.3rem'>readers here</div>"
            f"<div class='heb' style='font-size:.95rem;white-space:normal'>{esc(saw)}</div></td>"
            f"<td>{heb(r['gold'])}<div class='k'>modern edition</div></td>"
            f'<td><span class="tag {cls}">{tag}</span>'
            f"<div class='k'>scan p{r['page']}</div></td></tr>")
    return ("<table><tr><th>the ink, 1848 Frankfurt</th><th>read here</th>"
            "<th>gold<div class='k' style='text-transform:none;letter-spacing:0'>"
            "as compared: finals folded, points dropped</div></th>"
            "<th>evidence at this word</th></tr>"
            + "".join(out) + "</table>")


def weld_figs(items: list[dict]) -> str:
    out = []
    for w in items:
        out.append(f"<figure>{img(w['band'])}<figcaption>the backbone returned "
                   f"{heb(w['was'])} — {len(w['was'].split())} words. Welded to "
                   f"{heb(w['now'])}, which no lexicon attests, so the test "
                   f"scored the repair as damage.</figcaption></figure>")
    return f'<div class="grid">{"".join(out)}</div>'


def split_rows(items: list[dict]) -> str:
    out = []
    for s in items:
        out.append(f"<tr><td>{heb(s['was'])}</td><td>{heb(s['now'])}</td>"
                   f"<td class='k'>scan p{s['page']}</td></tr>")
    return ("<table><tr><th>one word, as printed</th><th>two words the lexicon "
            "would accept</th><th></th></tr>" + "".join(out) + "</table>")


def build(base: str = ".", pdf: str = "") -> str:
    rows = [r for r in json.load(open(f"{base}/data/gold_wrong.json",
                                      encoding="utf-8"))
            if r["gold"] and r["book"]]
    ink = json.load(open(f"{base}/data/gold_ink.json", encoding="utf-8"))
    if pdf and not all(f"{r['page']}:{r['tok']}" in ink for r in rows):
        ink = photograph(base, pdf, rows)
        json.dump(ink, open(f"{base}/data/gold_ink.json", "w", encoding="utf-8"),
                  ensure_ascii=False)
    weld = json.load(open(f"{base}/data/weld_ink.json", encoding="utf-8"))
    proxy = json.load(open(f"{base}/data/proxy_wrong.json", encoding="utf-8"))
    elide = elisions(base)
    cut = sum(1 for r in rows if (r["gold"], r["book"]) in elide)
    ens = json.load(open(f"{base}/data/ensemble.json", encoding="utf-8"))
    set_ = {p["page"]: " ".join(t for t, _ in p["body"]).split() for p in ens["pages"]}
    for r in rows:
        w = set_.get(r["page"], ())
        r["set"] = w[r["tok"]] if r["tok"] < len(w) else ""
    shown = [r for r in rows if f"{r['page']}:{r['tok']}" in ink]
    # Keyed on the verdict itself, not on its label. An earlier version counted
    # by the printed wording, so renaming a tag left the prose confidently
    # reporting zero of a class the table below it was showing nineteen of.
    tally = {k: 0 for k in TAG}
    for r in rows:
        tally[r.get("backs", "none")] += 1

    return f"""<!doctype html><html lang="en"><head><meta charset="utf-8">
<meta name="viewport" content="width=device-width,initial-scale=1">
<title>The failed tests</title><style>{CSS}</style></head><body><main>

<h1>The failed tests</h1>
<p class="lede">Every disagreement between this edition and the held-out gold,
photographed; and the places where the lexical quality test returned the wrong
sign. 1848 Frankfurt, ʿAmudei Kesef.</p>

<h2>1 · Where the edition and the gold disagree</h2>
<p>The gold is 1,241 words transcribed by hand from the 2025 critical edition
(מכון לעידוד לימוד הגות ודעת, בני ברק תשפ״ה) and withheld from every stage of the
arbitration. The edition scores <span class="num">92.75 %</span> against it; the
best single reader, the one that looked at the scan, scores
<span class="num">93.39 %</span>.</p>
<p>Of the <span class="num">90</span> words counted wrong,
<span class="num">{len(rows)}</span> are substitutions — the edition read a word
and read it differently. The rest are boundary effects at the ends of the
located window. Below, all
<span class="num">{len(shown)}</span> substitutions whose ink could be located
on the page.</p>
<div class="box"><p style="margin:0">The gold is <em>not</em> a transcription of
this scan. It is a different edition of the same text, made from manuscripts.
So a disagreement is not automatically a misreading, and the tally below is
<strong>not</strong> a verdict — it is where the evidence outside the photograph
points. Readers of the print back the edition and never show the gold's form in
<span class="num">{tally['edition']}</span> of the
<span class="num">{len(rows)}</span> cases; the gold's form is visible on the
page in <span class="num">{tally['gold']}</span>;
<span class="num">{tally['none']}</span> are open. If the first group is
what it looks like, the true reading accuracy is meaningfully above 92.75 % and
the modern editor and Frankfurt simply differ. <strong>Check the crops.</strong>
</p></div>
<p>The <span class="num">{tally['gold']}</span> rows marked
<span class="tag t-ocr">misread here</span> are the useful ones: at each of them
a reader of this scan returned the gold's word and the arbitration passed it
over. They are the whole of the remaining measurable optical error, and they are
where the next round of work goes.</p>
<p>A further <span class="num">{cut}</span> are not disagreements at all. The
modern editor abbreviates with ‏וכו׳‎ where Frankfurt sets the passage out in
full; the aligner has one gold word and several printed ones to pair it with, so
it pairs the marker with the first and charges a substitution for a word the
gold never claimed to quote — then charges again for the words that follow until
the two texts meet. They are marked <span class="tag t-print">gold
abbreviates</span> below, and the crop shows the print doing nothing wrong.</p>
{gold_rows(shown, ink, elide)}

<hr class="rule">

<h2>2 · Where the quality test returned the wrong sign</h2>
<p>The unattested-word rate asks whether a form appears in a lexicon of clean
Hebrew. It cannot ask whether it is the form on the page, and at this level of
quality — <span class="num">3.43 %</span> over Kaspi's text, against a floor of
<span class="num">1.1–3.8 %</span> measured on born-digital text — that
difference is the whole difference.</p>

<h2 style="font-size:1rem;border:0;margin-bottom:0">
2a · Repairs the test scored as damage</h2>
<p>The publisher's text layer scatters loosely-set words into fragments. Welding
them back is character-identical — the letters do not change and another reader
of the same ink read them as one token — but each weld converts several short
attested fragments into one long word the lexicon may not hold. The test counts
that as a loss. It happens
<span class="num">{len(proxy['weld'])}</span> times in this volume, including
the title of the book being edited.</p>
{weld_figs(weld)}

<h2 style="font-size:1rem;border:0;margin-bottom:0">
2b · Damage the test would have scored as repair</h2>
<p>Run the same reasoning backwards. Hebrew is dense with short words, so almost
any form can be cut somewhere into two the lexicon attests — and every such cut
lowers the unattested rate. The rule that did this shipped, fired
<span class="num">280</span> times, and
<span class="num">275</span> of those were a space no reader of the page had put
there. The bare lexical test would license
<span class="num">{len(proxy['split'])}</span>. Every row below is one word in
the print.</p>
{split_rows(proxy['split'][:30])}
<p class="lede">…and {len(proxy['split']) - 30:,} more.</p>

<hr class="rule">
<h2>What this means for the number</h2>
<p>The lexical test is not broken as a coarse instrument: it ranked the four
readers correctly and correctly identified that the one which looked at the scan
was the best of them. What it can no longer do is adjudicate a change, because
near the floor its sign is unreliable in both directions — it voted against
three fixes this cycle that the gold confirmed were improvements. Everything
above the resolution of the gold is now invisible to it, and the gold covers one
region of one of the two commentaries.</p>
<p>The honest statement of the edition's quality is therefore two numbers and a
caveat: <span class="num">92.75 %</span> word accuracy against a modern critical
edition over 1,241 words, which is a <em>lower</em> bound because some of the
disagreements are textual rather than optical; and
<span class="num">3.43 %</span> unattested forms over the whole of Kaspi's text,
which is at the floor of what that measurement can see.</p>

<footer>Crops cut at 600 dpi from the Frankfurt 1848 scan, marked in red beneath
the word in question. Generated by <span class="k">src/failures.py</span>.
</footer>
</main></body></html>"""


if __name__ == "__main__":
    base = sys.argv[1] if len(sys.argv) > 1 else "."
    pdf = sys.argv[2] if len(sys.argv) > 2 else ""   # only needed to cut fresh ink
    out = f"{base}/out/AmudeiKesef_failures.html"
    open(out, "w", encoding="utf-8").write(build(base, pdf))
    print(f"file: {out}")
