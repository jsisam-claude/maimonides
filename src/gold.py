#!/usr/bin/env python3
"""A printed edition of Kaspi as a witness, and the first true measure of this one.

Everything this edition has claimed about its own accuracy so far has been a
proxy. "Three point one two percent of words are attested nowhere in a clean
Hebrew corpus" is a statement about a lexicon, not about the page: it counts the
errors that happen to produce non-words and is blind to every error that
produces a different real word — ‏רבר‎ for ‏דבר‎ is caught, ‏הרב‎ for ‏הרג‎ is
not. The floor calibration bounds how much of the residue is Kaspi's own
vocabulary rather than damage, but no amount of that arithmetic turns a proxy
into a measurement. For that you need a text someone has already got right.

The fourth PDF is one. It is the front matter of a modern typeset edition of the
Guide with its commentators, and among the commentators, on six of its pages, is
‏עמודי כסף‎ over the Epistle to the Student and the opening of the Introduction —
the same words this edition read off a photograph of the 1848 Frankfurt print,
set from manuscripts by an editor with the manuscripts in front of him. Roughly
eleven hundred words. Against them the OCR can be scored the way OCR is supposed
to be scored: word for word, against a known answer.

Two honest qualifications, because the number is worthless without them.

*It is an upper bound on error, not the error.* Werbluner set his 1848 text from
Munich 264 and Leipzig 14; the modern editor had those and Paris 700 and
Petersburg C47, and says so. Where the two differ, some of the difference is
this edition misreading the scan and some is the two editors reading different
manuscripts. Nothing here can separate them, so every disagreement is charged to
the OCR. The true rate is better than the reported one by however much of the
gap is Werbluner's.

*It measures one region.* Eleven hundred words at the front of a
seventy-thousand-word volume, and the front matter is the best-printed part of
any book. Extrapolating this rate to the whole is exactly the mistake the proxy
measure was introduced to avoid making.

What the PDF does not do is hand its text over. The commentary blocks are set in
five legacy Hebrew fonts that map the alphabet onto Latin code points, so a text
extractor reads them as accented Latin and leaves them in visual order. Two
different mis-decodings appear, depending on whether the font declared WinAnsi
or MacRoman, and both are the same underlying CP1255 bytes: re-encode to the
declared charset, decode as CP1255, reverse the run. The publisher used one of
those fonts for the Guide's lemmata inside the commentary and real Unicode for
the commentator's own words, which is an accident worth having — the lemma/
comment split of the printed page survives into the extraction for free, and
this module keeps it.

Dependencies: none beyond `pdftotext`, which the pipeline already uses.
"""
from __future__ import annotations

import json
import os
import re
import subprocess
import sys
import unicodedata
from collections import Counter

import ensemble
import ocrqual

HEB = re.compile(r"[֐-׿]")
HEADS = {"אפודי", "שם טוב", "קרשקש", "נרבוני", "אברבנאל",
         "עמודי כסף", "משכיות כסף"}
WORKS = {"עמודי כסף": "amudei", "משכיות כסף": "maskiyot"}

# The two ways poppler mis-reads a CP1255 byte stream, in the order to try them.
# Which one applies is a property of the font, not of the page, so a line can
# hold both; deciding per run costs nothing and gets the mixed lines right.
CHARSETS = ("cp1252", "mac_roman", "latin-1")


def unfold(run: str) -> str | None:
    """One legacy run, back to Hebrew, or None if it was never legacy at all.

    The run is put back into the bytes it came from and read as CP1255, then
    reversed: poppler applies the bidirectional algorithm to text it believes is
    Hebrew and leaves everything else in the order the page stored it, which for
    a right-to-left page is visual. A run that yields no Hebrew letters was some
    other accented Latin — a footnote marker, a stray glyph — and is refused
    rather than guessed at.
    """
    for enc in CHARSETS:
        try:
            out = run.encode(enc).decode("cp1255")
        except (UnicodeEncodeError, UnicodeDecodeError):
            continue
        if HEB.search(out):
            return out[::-1]
    return None


def runs(line: str) -> list[tuple[str, bool]]:
    """Split a line into stretches of Hebrew and stretches of legacy font.

    Punctuation and digits belong to whichever stretch they touch — they carry
    no evidence of their own about which font set them — so the line is cut only
    where a Hebrew letter meets a legacy letter. Everything neutral rides along
    with the run it follows, and a line that opens neutral joins the first run
    that declares itself.
    """
    kind: list[bool | None] = []
    for c in line:
        if HEB.match(c):
            kind.append(False)
        elif ord(c) > 0x7F and unicodedata.category(c)[0] in "LSP":
            kind.append(True)
        else:
            kind.append(None)
    last = None
    for i, k in enumerate(kind):          # neutrals take the previous verdict
        if k is None:
            kind[i] = last
        else:
            last = k
    for i in range(len(kind) - 1, -1, -1):   # ...and a leading run, the next
        if kind[i] is None:
            kind[i] = kind[i + 1] if i + 1 < len(kind) else False
    out: list[tuple[str, bool]] = []
    for c, k in zip(line, kind):
        if out and out[-1][1] == k:
            out[-1] = (out[-1][0] + c, k)
        else:
            out.append((c, bool(k)))
    return out


def blocks(text: str) -> dict[str, list[str]]:
    """The page's commentaries, each under the heading the publisher gave it."""
    out: dict[str, list[str]] = {}
    head = None
    for line in text.splitlines():
        line = line.strip("‪‫‬ ").rstrip()
        if line in HEADS:
            head = line
            out.setdefault(head, [])
        elif head is not None:
            out[head].append(line)
    return out


def page(pdf: str, n: int) -> str:
    """One page as the extractor gives it, with the bidi controls removed."""
    txt = subprocess.run(["pdftotext", "-f", str(n), "-l", str(n), pdf, "-"],
                         capture_output=True, text=True, check=True).stdout
    return "".join(c for c in txt if unicodedata.category(c) != "Cf")


RUNNING = "מורה הנבוכים"      # the running head every page of the body carries


def read(pdf: str, last: int = 0) -> list[dict]:
    """Kaspi's two commentaries wherever this volume prints them.

    Each entry is one page's block: the commentator's own words in order, and
    the lemmata that were set among them, kept apart because they are evidence
    of different things. The comment is the text to be measured against; the
    lemma is Ibn Tibbon, which this edition already has perfectly and does not
    need a second copy of — but which tells it *where* in the Guide the block
    belongs, and that it does need.

    The title page names both commentaries and prints neither, so a rule is
    needed that tells a heading from a table of contents. The volume supplies
    one: every page of the body carries a running head, and the front matter
    carries none. Taking the body to begin where the running head does costs a
    line and is a fact about this book rather than a guess about where its
    contents list ends.
    """
    last = last or int(subprocess.run(["pdfinfo", pdf], capture_output=True,
                                      text=True, check=True).stdout
                       .split("Pages:")[1].split()[0])
    first = next((n for n in range(1, last + 1) if RUNNING in page(pdf, n)), 1)
    out: list[dict] = []
    for n in range(first, last + 1):
        for head, lines in blocks(page(pdf, n)).items():
            if head not in WORKS:
                continue
            said: list[str] = []
            cited: list[str] = []
            for line in lines:
                for run, legacy in runs(line):
                    if not legacy:
                        said.append(run)
                    elif (heb := unfold(run)) is not None:
                        cited.append(heb)
            body = " ".join(said)
            if HEB.search(body):
                out.append({"page": n, "work": WORKS[head],
                            "text": re.sub(r"\s+", " ", body).strip(),
                            "lemma": [re.sub(r"\s+", " ", c).strip()
                                      for c in cited]})
    return out


# ---------------------------------------------------------------- measurement

# Either orientation: the extractor does not mirror brackets on a right-to-left
# line, so an editor's aside arrives as ‏)ע"פ עובדיה א, יא(‎ with the parentheses
# the wrong way round. Matching a bracket of either kind, then anything that is
# not one, then a bracket of either kind, reads both without having to decide
# which way this particular PDF turned them.
EDITORIAL = re.compile(r"[()][^()]*[()]")


def words(text: str, apparatus: bool = True) -> list[str]:
    """The comparable form of a text: letters only, finals folded.

    Where the text is the printed edition's, its editor's parenthetical
    source-notes come out first — ‏(ע"פ עובדיה א, יא)‎ and the like. They are not
    Kaspi and they are not in the 1848 print, so scoring this edition on its
    failure to have read them measures nothing; left in, they were also drifting
    the alignment for a dozen words afterwards and costing far more than the
    words themselves. Werbluner's own bracketed remarks stay in on this side,
    where they can only appear as insertions, which the accuracy figure does not
    reward.
    """
    if apparatus:
        text = EDITORIAL.sub(" ", text)
    return [ocrqual.fold(w) for w in ocrqual.WORD.findall(
        ocrqual.NIQQUD.sub("", text))]


def locate(want: list[str], hay: list[str],
           look: tuple[int, ...] = (3, 2)) -> tuple[int, int]:
    """Where in *hay* the gold passage sits, by the rarest thing it says.

    A trigram that occurs once in the gold and once in the haystack is an anchor
    whether or not the words around it were read correctly, and the anchors
    together bound the passage: it runs from a little before the earliest to a
    little after the latest. Without this the alignment would have to consider
    every position in a seventy-thousand-word volume for a passage a thousand
    long, which is both slow and wrong — it would match the wrong chapter
    wherever that chapter shared enough vocabulary.

    Trigrams first and pairs only if trigrams fail. Against the arbitrated text
    trigrams are plentiful; against raw Tesseract, where one word in five is
    damaged, an intact run of three is rare and an intact pair is not. The fall
    back is to the weaker anchor rather than to no anchor, and it is only ever
    used to bound a window that the alignment then has to justify word by word.

    The anchors are not all believed. A passage of Kaspi sits at one offset in
    the volume, so every true anchor reports the same difference between where
    the words are and where they were expected; a phrase that happens to be
    unique in both texts and to occur in a different chapter reports a wildly
    different one. Taking the extremes of all anchors let one such coincidence
    stretch a two-hundred-word window to fifty thousand — the alignment then ran
    for minutes and would have been meaningless if it had finished. So the
    offsets are clustered and only the largest agreeing group is used, which is
    both faster and the correct reading of the evidence: a lone anchor
    contradicted by forty others is wrong.
    """
    for n in look:
        index: dict[tuple, list[int]] = {}
        for i in range(len(hay) - n + 1):
            index.setdefault(tuple(hay[i:i + n]), []).append(i)
        hits = [(i, index[k][0]) for i in range(len(want) - n + 1)
                if len(index.get(k := tuple(want[i:i + n]), ())) == 1]
        hits = agreed(hits, len(want))
        if hits:
            lo = min(j - i for i, j in hits)
            hi = max(j + (len(want) - i) for i, j in hits)
            pad = ensemble.BAND
            return max(0, lo - pad), min(len(hay), hi + pad)
    return 0, 0


def agreed(hits: list[tuple[int, int]], span: int) -> list[tuple[int, int]]:
    """The largest group of anchors that place the passage in the same place.

    Two anchors agree when the offsets they imply differ by less than the length
    of the passage itself: within a passage, words shift by insertions and
    deletions but not by more than the passage is long, and beyond it they are
    talking about different pages.
    """
    if not hits:
        return []
    by = sorted(hits, key=lambda h: h[1] - h[0])
    best: list[tuple[int, int]] = []
    i = 0
    for j in range(len(by)):
        while (by[j][1] - by[j][0]) - (by[i][1] - by[i][0]) > span:
            i += 1
        if j - i + 1 > len(best):
            best = by[i:j + 1]
    return best


FOUND = 0.5        # below this a passage is not in the volume at all — see below


def presence(want: list[str], hay: list[str]) -> float:
    """The best any window of *hay* can match *want*, ignoring order.

    Two very different things arrive at this module looking identical: a passage
    the readers mangled, and a passage that was never printed in the book they
    read. Both score near zero, and folding the second into an accuracy figure
    charges a missing source to the OCR. The Frankfurt volume is ‏עמודי כסף‎
    alone — its folios run 1 to 151 without a reset — so the opening of
    ‏משכיות כסף‎, which the modern edition prints, is simply not there to be read.

    Alignment cannot tell them apart, because it is only ever shown the window
    `locate` chose and can say nothing about the rest of the volume. This can:
    slide a window the length of the passage across the whole book and ask how
    many of the passage's words are inside it, order disregarded. Order is
    dropped on purpose — it is a test of whether the *material* is present, and
    a reading that scrambles a line still holds its words.

    The threshold is not chosen a priori; it is read off the distribution. The
    eight gold passages come back at 0.19 for the one that is absent and 0.66 to
    0.92 for the seven that are present. Nothing lands between, and a half is the
    middle of that gap.

    Incremental, so the cost is one pass over the volume rather than one per
    window: a word leaving the window loses a match only if the window was not
    already holding a surplus of it, and a word entering gains one only if it is
    still short.
    """
    if not want or len(hay) < len(want):
        return 0.0
    n = len(want)
    need, have = Counter(want), Counter(hay[:n])
    hit = best = sum(min(v, have[k]) for k, v in need.items())
    for i in range(n, len(hay)):
        old, new = hay[i - n], hay[i]
        if old == new:
            continue
        if have[old] <= need[old]:
            hit -= 1
        have[old] -= 1
        have[new] += 1
        if have[new] <= need[new]:
            hit += 1
        best = max(best, hit)
    return best / n


def score(want: list[str], got: list[str]) -> dict:
    """Word accuracy of *got* against the known *want*, plus what it got wrong.

    Insertions are counted as errors and not as a separate category. An OCR that
    invents a word has damaged the text exactly as much as one that misreads it,
    and an accuracy figure that quietly excludes inventions is the figure every
    OCR vendor quotes.
    """
    pairs = ensemble.align(want, got)
    right, wrong = 0, []
    for i, j in pairs:
        a = want[i] if i is not None else ""
        b = got[j] if j is not None else ""
        if a and a == b:
            right += 1
        elif a or b:
            wrong.append((a, b))
    return {"words": len(want), "right": right,
            "rate": right / max(1, len(want)), "wrong": wrong}


def measure(base: str, gold: list[dict]) -> dict:
    """Score every witness, and this edition, over the region the gold covers.

    All four are scored on the same words — the window the gold passage occupies
    in the arbitrated book — so the numbers are comparable to each other. They
    are not comparable to the unattested-word rates quoted elsewhere, which are
    measured over the whole volume; that is the same contamination this project
    has already been caught by once.

    A passage the volume does not contain is reported as coverage and kept out of
    the accuracy totals. What is being measured here is how well the scan was
    read, and a text that was never on the scan cannot be read well or badly; the
    honest report of it is that the source is short, which is a fact about the
    edition worth stating in its own row rather than one buried in a percentage.
    """
    final = json.load(open(f"{base}/data/ensemble.json", encoding="utf-8"))
    book = [w for p in final["pages"] for t, _ in p["body"]
            for w in words(t, apparatus=False)]
    # The layer is stored as the backbone, page by page and line by line, and
    # the other three as plain text per page. Flattening the first here rather
    # than teaching `ensemble.reading` a second shape keeps that function what
    # it is — the reader of a Tesseract pass.
    other = {"layer": {p["page"]: " ".join(ln for ln, _ in p["body"])
                       for p in json.load(open(f"{base}/data/book_layer.json",
                                               encoding="utf-8"))["pages"]},
             "eye": ensemble.reading(f"{base}/data/book_eyes.json"),
             "tesseract": ensemble.reading(f"{base}/data/book_tess.json")}
    out: dict = {"passages": [], "absent": [], "total": {}}
    tot: dict[str, list[int]] = {}
    for g in gold:
        want = words(g["text"])
        seen = presence(want, book)
        if seen < FOUND:
            out["absent"].append({"page": g["page"], "work": g["work"],
                                  "words": len(want), "presence": seen})
            continue
        lo, hi = locate(want, book)
        if hi <= lo:
            continue
        row = {"page": g["page"], "work": g["work"], "at": [lo, hi],
               "presence": seen, "this": score(want, book[lo:hi])}
        for name, reading in other.items():
            # Each witness is searched only on the scan pages the window covers.
            # Which pages those are is not visible in the window — the arbitrated
            # book carries the page of every word, so ask it — and the passage is
            # then located inside them the same way it was located in the book. A
            # witness the anchors cannot find is left unscored rather than scored
            # against whatever text happened to be on the page.
            hay = words(" ".join(reading.get(p, "")
                                 for p in pagespan(final, lo, hi)),
                        apparatus=False)
            a, b = locate(want, hay)
            if b > a:
                row[name] = score(want, hay[a:b])
        out["passages"].append(row)
        for k, v in row.items():
            if isinstance(v, dict):
                a, b = tot.setdefault(k, [0, 0])
                tot[k] = [a + v["right"], b + v["words"]]
    out["total"] = {k: {"right": a, "words": b, "rate": a / max(1, b)}
                    for k, (a, b) in tot.items()}
    return out


def pagespan(final: dict, lo: int, hi: int) -> list[int]:
    """Which scan pages the book positions *lo*..*hi* were printed on."""
    out, k = [], 0
    for p in final["pages"]:
        n = sum(len(words(t, apparatus=False)) for t, _ in p["body"])
        if k < hi and k + n > lo:
            out.append(p["page"])
        k += n
    return out


def main() -> None:
    base = sys.argv[1] if len(sys.argv) > 1 else "."
    pdf = sys.argv[2]
    gold = read(pdf)
    json.dump(gold, open(f"{base}/data/gold.json", "w", encoding="utf-8"),
              ensure_ascii=False)
    n = sum(len(words(g["text"])) for g in gold)
    print(f"{len(gold)} passages, {n:,} words of Kaspi in print", file=sys.stderr)

    got = measure(base, gold)
    json.dump(got, open(f"{base}/data/gold_score.json", "w", encoding="utf-8"),
              ensure_ascii=False)
    order = ["tesseract", "layer", "eye", "this"]
    name = {"tesseract": "Tesseract alone", "layer": "PDF text layer",
            "eye": "read by eye", "this": "this edition"}
    print(f"\n  {'witness':18} {'words':>7} {'right':>7} {'accuracy':>9}",
          file=sys.stderr)
    for k in order:
        if k in got["total"]:
            t = got["total"][k]
            print(f"  {name[k]:18} {t['words']:>7,} {t['right']:>7,} "
                  f"{t['rate']:>8.2%}", file=sys.stderr)
    for a in got["absent"]:
        print(f"\n  not in the volume: {a['work']} p{a['page']}, "
              f"{a['words']:,} words, best overlap {a['presence']:.2f} "
              f"— scored by nobody, and not counted above", file=sys.stderr)
    print(f"\n  {len(got['passages'])} of {len(gold)} passages measured; "
          f"per-passage presence "
          + ", ".join(f"{p['presence']:.2f}" for p in got["passages"]),
          file=sys.stderr)


if __name__ == "__main__":
    main()
