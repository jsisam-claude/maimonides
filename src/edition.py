#!/usr/bin/env python3
"""Assemble the edition: the Guide at the centre, its commentators around it.

This is the *Miqraot Gedolot* arrangement applied to the ``Moreh Nevukhim``.
The base text (Ibn Tibbon's Hebrew, held verbatim from Sefaria) runs down the
middle; Kaspi's two commentaries — recovered from the 1848 Werbluner print by
src/units.py — stand to its right, where a Hebrew reader's eye lands first;
the five classical commentators stand to its left.

Three things are done here that a plain transcription cannot do:

*Lemmatisation.* The 1848 print marks Kaspi's lemmata only by a change of
face, which OCR cannot see. src/quote.py recovers them as maximal verbatim
runs shared with Ibn Tibbon; this module turns each recovered lemma into a
paragraph break, restoring the lemma/comment rhythm the typography carried.

*Binding.* Every lemma is also located in the Guide, so a lemma and the words
it quotes are two ends of one link: touch either and both light up. Kaspi's
remark is therefore anchored to a position in the base text, not merely to a
chapter.

*Confidence, shown.* Each unit carries the matcher's score, the route it was
found by, the verdict of the independent validator (src/verify.py) and the
share of its words that any Hebrew text attests (src/ocrqual.py). None of it
is hidden: unattested words are underlined where they stand, so the reader
sees the damage rather than being told about it in a preface.

Output is one self-contained HTML file with no network access and no external
assets. The corpus (~7 MB of JSON) is gzipped and base64'd into a data island
and inflated in the browser by ``DecompressionStream`` — a platform API, so
the zero-dependency rule holds on both sides.

Dependencies: none (Python standard library).
"""
from __future__ import annotations

import base64
import bisect
import gzip
import json
import os
import re
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import ensemble                                 # noqa: E402
import ocrqual                                  # noqa: E402
import quote                                    # noqa: E402
import units as U                               # noqa: E402

MAXSCORE = U.W_NUM + U.W_LEM + U.W_HEAD + U.W_INIT

WITNESSES = [("efodi", "אפודי"), ("shemtov", "שם טוב"), ("crescas", "קרשקש"),
             ("narboni", "נרבוני"), ("abarbanel", "אברבנאל")]

PART_NAME = {1: "חלק ראשון", 2: "חלק שני", 3: "חלק שלישי"}
FRONT = [("kaspi:0:0", "הקדמת המפרש — אמר יוסף אבן כספי", 0),
         ("letter:0:0", "אגרת המחבר לר׳ יוסף בן יהודה", 0),
         ("pref:0:0", "פתיחה", 0),
         ("intro:1:0", "הקדמה — סיבות הסתירה", 1),
         ("intro:2:0", "הקדמה לחלק שני — כ״ה ההקדמות", 2),
         ("intro:3:0", "הקדמה לחלק שלישי", 3)]
PART_LEN = {1: 76, 2: 48, 3: 54}

WS = re.compile(r"[ \t]+")


# ── text → HTML ───────────────────────────────────────────────────────────────

def esc(s: str) -> str:
    return s.replace("&", "&amp;").replace("<", "&lt;").replace(">", "&gt;")


# A span is (start, end, kind, n). Kinds: "q" = quotation of the base text,
# "x" = word attested nowhere in the clean corpus, "guide" = a word inside a
# quotation that the collation against Ibn Tibbon mended or argued with,
# "note" = a word nothing else marks but which the edition has an image of.
# "note" is last because it is the weakest thing the edition can say about a
# word — that it has nothing to say, only ink to show — and any other mark
# says more.
#
# The fourth field carries a quotation id for "q" and, for everything else, a
# handle to the word in the arbitrated book (index + 1, so that 0 means "not
# placed"). `footnotes` turns those handles into printed note numbers, once the
# overlaps have been resolved and it is known which spans survive.
PRIORITY = {"q": 0, "most": 1, "seen": 1, "lex": 1, "fix": 1, "keep": 1,
            "doubt": 1, "x": 1, "guide": 1, "note": 2}
Span = tuple

# What the reader is shown, and in what order of doubt. `agree` and `guide` are
# deliberately absent: a word every reading returned, or one collated against
# Ibn Tibbon and found to agree, is set plain, because marking three quarters
# of a page tells the eye nothing. The marks are for the quarter that is not
# settled — to which the rules in `build` add, one by one, the words that carry
# evidence whatever their provenance says.
SHOWN = ("most", "seen", "lex", "fix", "keep", "doubt")


def resolve(spans: list[Span]) -> list[Span]:
    """Drop conflicting spans, lower-priority first; return in reading order.

    Two spans conflict when they overlap in part, because one of them would
    have to be cut in half to print both and half a mark is not a mark. A span
    lying wholly inside a quotation is not that case, and used to be treated as
    though it were: the quotation won, the mark inside it was dropped, and with
    it went the note it carried. Two hundred and thirty-two corrections
    disappeared that way — every one of them inside a lemma, which is precisely
    where this edition's collation does its work, so the pass that produced the
    most emendations was the one whose emendations the reader could not see.

    A mark inside a quotation is what a critical edition looks like. It nests,
    and `paint` prints it nested.
    """
    keep: list[Span] = []
    for sp in sorted(spans, key=lambda s: (PRIORITY[s[2]], s[0])):
        if any(sp[0] < e and s < sp[1]
               and not (k == "q" and s <= sp[0] and sp[1] <= e
                        and e - s > sp[1] - sp[0])
               for s, e, k, _ in keep):
            continue
        keep.append(sp)
    keep.sort(key=lambda sp: (sp[0], -sp[1]))   # container before contained
    return keep


def paint(text: str, spans: list[Span]) -> str:
    """Escape *text*, wrapping each resolved span in its mark-up.

    A marked word that has been given a note number carries the number after
    it, in the body of the line rather than in a margin: the apparatus sits at
    the foot of the commentary it belongs to, and the reader has to be able to
    get from the word to it and back.

    Spans arrive sorted container-first, so a span whose end falls inside its
    predecessor is a span inside it, and is painted into its body.
    """
    out, prev, i = [], 0, 0
    while i < len(spans):
        s, e, kind, n = spans[i]
        j = i + 1
        while j < len(spans) and spans[j][1] <= e:
            j += 1
        out.append(esc(text[prev:s]))
        body = (esc(text[s:e]) if j == i + 1 else
                paint(text[s:e], [(a - s, b - s, k, m)
                                  for a, b, k, m in spans[i + 1:j]]))
        if kind == "q":
            out.append('<span class="q" data-q="%d">%s</span>' % (n, body))
        else:
            out.append('<u class="%s">%s</u>' % (kind, body))
            if n:
                out.append('<sup class="fn">%d</sup>' % n)
        prev, i = e, j
    out.append(esc(text[prev:]))
    return "".join(out)


WORD = re.compile(r"\S+")


class Book:
    """The arbitrated book as one word sequence, indexed by trigram so that a
    chapter can find itself in it without being told where to look.

    Three parallel lists, not a list of records: the trigram index and the
    placement search read `word` and nothing else, several hundred thousand
    times, and every word of this book is looked at whether or not anything is
    ever asked about it.
    """

    __slots__ = ("word", "why", "crop", "alt", "was", "index", "stats")

    def __init__(self, pages: list[dict], crop: dict | None = None):
        crop = crop or {}
        self.word: list[str] = []
        self.why: list[str] = []
        self.crop: list[str | None] = []
        self.alt: list[list] = []      # the readings this word was chosen over
        self.was: list[str] = []       # ...and what it said before a repair
        for p in pages:
            img = crop.get(str(p["page"]), {})
            alt, was = p.get("alt", {}), p.get("was", {})
            for i, (t, w) in enumerate(p["body"]):
                self.word.append(ocrqual.fold("".join(ocrqual.LETTERS.findall(t))))
                self.why.append(w)
                self.crop.append(img.get(str(i)))
                self.alt.append(alt.get(str(i), ()))
                self.was.append(was.get(str(i), ""))
        self.index: dict[tuple[str, str, str], list[int]] = {}
        for i in range(len(self.word) - 2):
            k = tuple(self.word[i:i + 3])
            if all(k):
                self.index.setdefault(k, []).append(i)


def provenance(base: str, crops: bool = True) -> Book:
    """Every word of the arbitrated book in order, with the test that chose it
    and, where the edition is still unsure of it, a picture of the ink — unless
    *crops* is false, which is how the chat-sized build asks for the apparatus
    without the photographs. It asks here rather than stripping them afterwards
    because the note numbers are set into the text: a build that dropped the
    pictures later would have to renumber both the notes and the marks that
    point at them, and the one thing worse than an apparatus with no evidence
    is an apparatus whose numbers are off by one.

    `ensemble.py` decides each word and records why; `units.py` then cuts the
    book into chapters and tidies the text, and the reasons do not survive the
    cut. Rather than thread them through — which would make the structural pass
    carry a payload it has no use for — they are matched back on here, where
    they are wanted.

    The crops are keyed the same way, by page and by position within the page,
    because that is the coordinate `ensemble.py` already keeps for every word:
    they join the reasons without a second alignment, which is the whole reason
    `Token.at` exists. An edition built without `data/crops.json` is the same
    edition with its footnotes off, so its absence is not an error.
    """
    data = json.load(open(f"{base}/data/ensemble.json", encoding="utf-8"))
    crop = {}
    if crops:
        try:
            crop = json.load(open(f"{base}/data/crops.json", encoding="utf-8"))
        except FileNotFoundError:
            pass
    book = Book(data["pages"], crop)
    # Everything the arbitration and the repair pass measured about themselves,
    # carried to the method panel so that what the edition claims about its own
    # workings is read off the run that produced it and not retyped from the
    # last one. `pages` is the book and is already unpacked; the rest is a few
    # dozen numbers.
    book.stats = {k: v for k, v in data.items() if k != "pages"}
    return book


def chain(pairs: list[tuple[int, int]]) -> list[tuple[int, int]]:
    """The longest run of matches that can all be true at once.

    A match says "the unit's word *i* is the book's word *h*". Any set of them
    that is a real correspondence must be increasing in both — text does not
    run backwards — so the largest increasing subsequence is the largest
    self-consistent reading of the evidence, and every match outside it is
    coincidence. Patience sorting, O(n log n).

    *pairs* arrive sorted by *i* ascending and, within one *i*, by *h*
    descending, so no two candidates for the same unit word can both be taken.
    """
    tails: list[int] = []
    idx: list[int] = []
    back: list[int] = []
    for n, (_, h) in enumerate(pairs):
        p = bisect.bisect_left(tails, h)
        back.append(idx[p - 1] if p else -1)
        if p == len(tails):
            tails.append(h)
            idx.append(n)
        else:
            tails[p], idx[p] = h, n
    out = []
    n = idx[-1] if idx else -1
    while n >= 0:
        out.append(pairs[n])
        n = back[n]
    return out[::-1]


def trace(txt: str, book: Book, look: int = 48, cap: int = 64) -> dict[int, int]:
    """Where each word of a unit sits in the arbitrated book, by text offset.

    It hands back the position rather than what is stored at it, because more
    than one thing is stored at it now — why the word was chosen, and whether
    the scan of it was cut out — and a function that returns one of them forces
    its caller to find the place again to ask about the other. Finding the
    place is the work this function does; returning less than that throws it
    away.

    The unit's words *are* the book's words in the same order, minus the ones
    `units.tidy` swept up as printer's dirt — so this is a placement problem,
    not an alignment: find where each word sits in the book.

    Two earlier versions walked forward from a guessed starting point, and both
    failed the same way. A short common word occurs hundreds of times in any
    window wide enough to absorb the error in the guess; the cursor takes the
    wrong one, and from then on every true match is *behind* it, so the walk
    never recovers and a whole chapter comes out unexplained. Re-anchoring on
    trigrams after a run of misses helped and did not fix it, because the
    re-anchor was itself a local guess made from the bad position.

    So nothing here is guessed. Every trigram of the unit that occurs in the
    book proposes a placement — three consecutive words fix a position in a
    quarter of a million almost uniquely — and `chain` keeps the largest set of
    those proposals that can be simultaneously true. That set is decided by the
    whole unit at once, so a single wrong match cannot mislead it, and the
    stretches between two anchors are short enough that a bounded local search
    closes them. Where a word still cannot be placed it is simply absent from
    the result, which is the right failure: an unexplained word is shown plain
    rather than shown wrong.

    Trigrams occurring more than *cap* times are stock phrases and are dropped;
    they carry no location and would only cost time.
    """
    words = [(m.start(), ocrqual.fold("".join(ocrqual.LETTERS.findall(m.group()))))
             for m in WORD.finditer(txt)]
    words = [(s, w) for s, w in words if w]

    pairs: list[tuple[int, int]] = []
    for i in range(len(words) - 2):
        hits = book.index.get(tuple(w for _, w in words[i:i + 3]), ())
        if hits and len(hits) <= cap:
            pairs += [(i, h) for h in reversed(hits)]
    fix = dict(chain(pairs))

    out: dict[int, int] = {}
    k: int | None = None
    for i, (at, w) in enumerate(words):
        if i in fix:
            k = fix[i]
        elif k is None:
            continue
        else:
            hi = min(len(book.word), k + look)
            lo = max(0, k - 4)
            j = next((x for x in range(lo, hi) if book.word[x] == w), None)
            if j is None and len(w) > 3:
                j = next((x for x in range(lo, hi) if w in book.word[x]), None)
            if j is None:
                continue
            k = j
        out[at] = k
        k += 1
    return out


# The witnesses, and the letter each one signs its readings with — in two
# registers that must not be confused, which is why they are one table with a
# line drawn through it rather than two tables.
#
# ‏ע‎, ‏ש‎ and ‏ט‎ are instruments and not manuscripts, and the apparatus has to
# say so: all of them read the same physical object, the Frankfurt print of
# 1848, so a disagreement between them is about legibility and never about
# transmission. Calling that a textual apparatus would tell the reader that
# this edition has collated witnesses it has not seen.
#
# ‏ת‎ is the other kind, and the only one here. Kaspi's lemmata are Ibn Tibbon's
# Guide, so where a lemma differs from the Guide the difference is not about
# ink at all: it is Kaspi quoting the manuscript in front of him, or the
# Frankfurt compositor spelling as he spelled. Nobody misread anything. That is
# a variant in the old sense, the first in this apparatus, and it is signed
# with a letter of its own so that no reader takes it for a smudge.
SIGLA = {"eye": "ע", "layer": "ש", "tesseract": "ט", "guide": "ת"}
OPTICAL = ("eye", "layer", "tesseract")
SLACK = 1     # letters of length a rival reading of one word may differ by


def variants(lemma: str, alt, lex: set[str]) -> list[tuple[str, str]]:
    """The rejected readings worth printing, of the ones this word rejected.

    Twenty-six thousand words of the volume were read two ways or more, and an
    apparatus that printed all of them would be a machine log with a lemma
    attached. Nearly all of that is one of two things that are not variants.

    The first is a known defect. ‏עוד‎ read as ‏עור‎ is Tesseract failing at the
    ‏ד‎/‏ר‎ pair, which `repair.py` measured on this very scan and found seventy-
    two times; the reader who is told about it learns about Tesseract, not about
    Kaspi. The second is worse: where the aligner slipped, two readings that face
    each other are not readings of one word at all — ‏ומשכיות‎ against ‏מודי‎ —
    and setting them side by side asserts a disagreement that never happened.

    What is left after both is the case the reader can use, and the test for it
    is not a threshold but the argument the whole ensemble rests on: three of the
    four instruments cannot read, they can only recognise shapes, and where they
    differ from the one reader who knows Hebrew it is the machines that are
    blind. So a rejected reading earns its place when *the eye* is what was
    rejected, and when what it read could stand in that ink — a Hebrew word,
    within a letter of the lemma's length, since a reader mistaking a letter
    returns a word of about that size and the aligner slipping does not.

    366 of these in the volume, against 26,719 disagreements. The rest are not
    suppressed, only unprinted: `data/ensemble.json` carries every one.

    None of that reasoning applies to the Guide. A reading rejected in favour
    of the page is not a machine's guess at a shape but Ibn Tibbon's text
    disagreeing with Kaspi's quotation of it, and the two questions an optical
    variant has to answer — could the ink have looked like that, is this even
    the same word — are not questions about it. It is printed whenever it
    exists. There are only some hundreds, and each one is the edition declining
    to overwrite the page with a better-known book.
    """
    n = len(ensemble.bare(lemma))
    return [(f, SIGLA["guide"]) if s == ensemble.GUIDE else (f, SIGLA.get(s, s))
            for f, s in alt
            # A Guide reading with no letters in it is a dash or a bracket the
            # Sefaria text sets where this print sets a word. That is an
            # editorial mark in another edition, not a reading of anything, and
            # ‏ט‎ ] ‏–‎ ת is an apparatus entry that says nothing at all.
            if (s == ensemble.GUIDE and ensemble.bare(f)) or
            (s == "eye" and 2 <= len(ensemble.bare(f)) <= n + SLACK
             and len(ensemble.bare(f)) >= n - SLACK and ensemble.ok(f, lex))]


def footnotes(spans: list[Span], text: str, book: Book,
              lex: set[str]) -> tuple[list[Span], list]:
    """Number the marked words the edition has something to say about.

    Every span arriving here that is not a quotation holds a handle to the word
    it marks in the arbitrated book, and three things may be known about it:
    what the eye read instead, what the word said before the repair pass altered
    it, and what the ink looks like. A word with none of them keeps its underline
    and nothing else — the underline already says the edition is unsure, and a
    note that repeats that in more words is not an apparatus.

    A correction is always reported. Everything else in this edition is a
    reading of the page, but a repair is the editor's own hand, and the one
    obligation an edition cannot trade away for brevity is to say where it has
    altered what it found. That is why `Token.was` exists.

    Numbering happens after the overlaps are resolved and never before. A span
    that loses an overlap is not printed, and a number spent on it would either
    vanish from the text while remaining in the apparatus — every note after it
    then pointing one word wrong — or survive as a number against nothing. The
    surviving spans are the only ones that can be counted, so they are counted
    here, where they are known.
    """
    out: list[Span] = []
    notes: list[list] = []
    for s, e, kind, n in spans:
        if kind != "q" and n:
            # The word as this edition prints it, escaped here rather than in
            # the browser: the apparatus reaches the DOM by innerHTML.
            # A correction is only a correction if the reader can see one. The
            # spans arrive from two sources with different extents — a lexical
            # flag covers the whole token, punctuation and all, while a
            # provenance mark covers the letters — so a repair that shows
            # through one may be invisible under the other, and an entry
            # reading ‏הא.דם‎ ] תוקן מ־‏הא.דם‎ asserts a change against the
            # evidence of its own line.
            img, was = book.crop[n - 1] or "", book.was[n - 1]
            was = "" if was == text[s:e] else was
            var = variants(text[s:e], book.alt[n - 1], lex)
            if img or was or var:
                notes.append([esc(text[s:e]), img, esc(was),
                              [[esc(f), g] for f, g in var]])
                n = len(notes)
            elif kind == "guide":
                # This mark exists only to carry a note, and there is none:
                # the crop was stripped for a chat-sized build, or the rival
                # reading did not earn its place. An underline whose whole
                # meaning is "see below" and which has no below is worse than
                # no underline. The other kinds stand on their own — they say
                # the edition is unsure — so they keep theirs.
                continue
            else:
                n = 0
        out.append((s, e, kind, n))
    return out, notes


def snap(text: str, span: tuple[int, int]) -> tuple[int, int]:
    """Grow a span outward to whole words.

    A lemma is found as the longest run of letters two texts share, and a run
    of letters does not know where words end: `‏ולזה ראיתי שאמש‎` is a real
    match that stops four letters into ‏שאמשול‎. Printed, that is a highlight
    with a torn edge. Worse, it is a span that overlaps the word's own mark
    without containing it, and an overlap is the one thing `resolve` cannot
    nest — so the note on that word was dropped, and the reader was told
    nothing about a correction the edition had made. Three of the five
    corrections still going unreported were this and nothing else.

    Growing rather than shrinking, because a citation of part of a word is a
    citation of the word: Kaspi wrote it whole and Ibn Tibbon wrote it whole,
    and only the substring search saw a fragment. Two lemmata that collide once
    grown are resolved by the same greedy rule that resolved them before.
    """
    s, e = span
    while s > 0 and not text[s - 1].isspace():
        s -= 1
    while e < len(text) and not text[e].isspace():
        e += 1
    return s, e


def pair(comment: str, base: str) -> list[tuple[tuple[int, int], tuple[int, int]]]:
    """Quotation pairs, longest first, kept only where both sides are free.

    quote.quotations already returns disjoint spans on the commentary side,
    but a stock phrase can land twice in the chapter. Resolving greedily by
    length keeps the pairing a bijection, which is what the two-way highlight
    depends on.

    Which lemmata survive is settled first, on the spans as found, and only
    then is each edge grown out to its word. Growing first and resolving after
    let a long lemma eat a short neighbour and cost twenty-two links, and the
    trade is not close: a torn edge costs one footnote, a dropped lemma costs
    the reader the tie between a citation and the sentence it cites. So the
    growth is per edge and strictly opportunistic — taken where the room is
    free, declined where it is not — and cannot change what was kept.
    """
    cs, bs = quote.quotations(comment, base)
    keep: list[tuple[tuple[int, int], tuple[int, int]]] = []
    for c, b in sorted(zip(cs, bs), key=lambda t: t[0][0] - t[0][1]):
        if any(c[0] < e and s < c[1] for (s, e), _ in keep):
            continue
        if any(b[0] < e and s < b[1] for _, (s, e) in keep):
            continue
        keep.append((c, b))
    for i, side in ((0, comment), (1, base)):
        room = sorted(p[i] for p in keep)
        for j, p in enumerate(keep):
            k = room.index(p[i])
            lo = room[k - 1][1] if k else 0
            hi = room[k + 1][0] if k + 1 < len(room) else len(side)
            s, e = snap(side, p[i])
            grown = (s if s >= lo else p[i][0], e if e <= hi else p[i][1])
            keep[j] = (grown, p[1]) if i == 0 else (p[0], grown)
    keep.sort(key=lambda t: t[0][0])
    return keep


def clip(text: str, spans: list[Span]) -> list[Span]:
    """Split spans at newlines so none straddles a paragraph."""
    out = []
    for s, e, kind, q in spans:
        a = s
        while True:
            nl = text.find("\n", a, e)
            if nl < 0:
                if a < e:
                    out.append((a, e, kind, q))
                break
            if a < nl:
                out.append((a, nl, kind, q))
            a = nl + 1
    return out


def paragraphs(text: str, spans: list[Span]) -> str:
    """Paint *text*, then break it into <p> at every newline."""
    html = paint(text, resolve(clip(text, spans)))
    return "".join("<p>%s</p>" % p for p in html.split("\n") if p.strip())


def lemmatised(text: str, spans: list[Span]) -> str:
    """Paint a commentary, starting a new paragraph at each lemma."""
    if not text.strip():
        return ""
    spans = resolve(spans)
    cuts = sorted({0, len(text)} | {s for s, _, k, _ in spans if k == "q"})
    out = []
    for a, b in zip(cuts, cuts[1:]):
        inner = [(s - a, e - a, k, q) for s, e, k, q in spans if a <= s and e <= b]
        chunk = paint(text[a:b], inner).strip()
        if chunk:
            out.append("<p>%s</p>" % chunk)
    return "".join(out)


def plain(segments: list[str]) -> str:
    return "".join("<p>%s</p>" % esc(WS.sub(" ", s).strip())
                   for s in segments if s and s.strip())


# ── assembly ─────────────────────────────────────────────────────────────────

def order() -> list[str]:
    keys = ["kaspi:0:0", "letter:0:0", "pref:0:0"]
    for p in (1, 2, 3):
        keys.append("intro:%d:0" % p)
        keys += ["ch:%d:%d" % (p, c) for c in range(1, PART_LEN[p] + 1)]
    return keys


def gershayim(n: int) -> str:
    """Hebrew numeral as it is set in print: ב׳, ט״ו, ע״ו."""
    s = U.numeral(n)
    return s + "׳" if len(s) == 1 else s[:-1] + "״" + s[-1]


def label(key: str) -> str:
    for k, lab, _ in FRONT:
        if k == key:
            return lab
    _, p, c = key.split(":")
    return "%s · פרק %s" % (PART_NAME[int(p)], gershayim(int(c)))


def build(base: str, crops: bool = True) -> dict:
    corpus = json.load(open(f"{base}/data/corpus.json", encoding="utf-8"))
    kaspi = json.load(open(f"{base}/data/kaspi_units.json", encoding="utf-8"))
    verify = json.load(open(f"{base}/data/verification.json", encoding="utf-8"))

    kby = {u["unit"]: u for u in kaspi["units"]}
    vby = {r["unit"]: r for r in verify["rows"]}
    moreh = corpus["moreh"]

    lex = ocrqual.lexicon(*(" ".join(sum(w.values(), [])) for w in corpus.values()))
    book = provenance(base, crops)

    units, quoted, noted, flagged, tokens = {}, 0, 0, 0, 0
    # `altered` is the audit of `mended`: every word in a printed unit whose
    # reading this edition changed, counted from the book rather than from the
    # notes. The apparatus claims to report all of them, and a claim an edition
    # makes about its own method is the one claim it can actually check. When
    # the two last differed they differed by 425, and the page said otherwise.
    mended = rival = inked = textual = altered = 0
    for key in order():
        segs = moreh.get(key) or []
        gtext = "\n".join(WS.sub(" ", s).strip() for s in segs)
        rec: dict = {"g": "", "a": "", "m": "", "n": {}, "w": {}}

        u = kby.get(key)
        if u:
            gspans: list[Span] = []
            qid, bad, tot = 0, 0, 0
            for field in ("amudei", "maskiyot"):
                txt = WS.sub(" ", u[field]).strip()
                spans: list[Span] = []
                for (cs, ce), (bs, be) in pair(txt, gtext):
                    qid += 1
                    spans.append((cs, ce, "q", qid))
                    gspans.append((bs, be, "q", qid))
                sus, b, t = ocrqual.suspects(txt, lex)
                bad, tot = bad + b, tot + t
                at = trace(txt, book)
                why = {s: book.why[k] for s, k in at.items()}
                spans += [(m.start(), m.end(), why[m.start()], at[m.start()] + 1)
                          for m in WORD.finditer(txt)
                          if why.get(m.start()) in SHOWN]
                # An unattested word every reading agreed on is a third thing:
                # not a disagreement the ensemble settled badly, but ink all
                # three read the same way and no clean text uses. Some are
                # Kaspi's own vocabulary and some are damage, and the edition
                # is not entitled to say which, so it says exactly that.
                spans += [(s, e, "x", at.get(s, -1) + 1) for s, e in sus
                          if why.get(s) not in SHOWN]
                # And a fourth: a word nothing above marks, because the readings
                # agreed and the lexicon is satisfied — but the reader who
                # looked at the page was not, and hedged over it. The edition
                # makes no claim there at all. It only prints the ink.
                spans += [(m.start(), m.end(), "note", at[m.start()] + 1)
                          for m in WORD.finditer(txt)
                          if why.get(m.start()) not in SHOWN
                          and m.start() in at and book.crop[at[m.start()]]]
                # And a fifth, which is the one an edition may not leave out.
                # A word settled by the collation is set plain like the rest of
                # its lemma — but plain is not the same as unreported, and this
                # is where the collation lives, so this is where its emendations
                # and its rejected readings are. Added last so that it never
                # displaces a mark that says more; dropped again in `footnotes`
                # if it turns out to have nothing to carry.
                spans += [(m.start(), m.end(), "guide", at[m.start()] + 1)
                          for m in WORD.finditer(txt)
                          if why.get(m.start()) not in SHOWN
                          and m.start() in at
                          and (book.was[at[m.start()]] or book.alt[at[m.start()]])]
                altered += sum(1 for m in WORD.finditer(txt)
                               if m.start() in at
                               and book.was[at[m.start()]] not in ("", m.group()))
                spans, notes = footnotes(resolve(spans), txt, book, lex)
                if notes:
                    rec["n"][field[0]] = notes
                rec[field[0]] = lemmatised(txt, spans)
            quoted += qid
            noted += sum(len(v) for v in rec["n"].values())
            mended += sum(1 for v in rec["n"].values() for x in v if x[2])
            rival += sum(1 for v in rec["n"].values() for x in v
                         if any(g != SIGLA["guide"] for _, g in x[3]))
            textual += sum(1 for v in rec["n"].values() for x in v
                           if any(g == SIGLA["guide"] for _, g in x[3]))
            inked += sum(1 for v in rec["n"].values() for x in v if x[1])
            flagged, tokens = flagged + bad, tokens + tot
            rec["g"] = paragraphs(gtext, gspans)
            rec["p"] = u["page"]
            rec["s"] = u["score"]
            rec["r"] = u["via"]
            rec["o"] = round(1.0 - bad / tot, 3) if tot else None
            v = vby.get(key, {})
            rec["v"] = v.get("verdict")
            rec["vr"] = v.get("rank")
            rec["va"] = v.get("argmax")
        else:
            rec["g"] = plain(segs)

        for wid, _ in WITNESSES:
            seg = corpus[wid].get(key)
            if seg:
                rec["w"][wid] = plain(seg)
        units[key] = rec

    add = [{"label": a.get("label") or "הוספות המגיה מכ״י מינכן",
            "page": a.get("page"),
            "html": plain(re.split(r"\n{2,}", a["text"]))}
           for a in kaspi.get("addenda", [])]

    have = {u["unit"] for u in kaspi["units"]}
    missing = {p: [c for c in range(1, PART_LEN[p] + 1)
                   if "ch:%d:%d" % (p, c) not in have] for p in (1, 2, 3)}

    return {
        "order": order(),
        "labels": {k: label(k) for k in order()},
        "units": units,
        "addenda": add,
        "wit": WITNESSES,
        "meta": {
            "matched": kaspi["matched"], "total": sum(PART_LEN.values()),
            "front": kaspi.get("front", 0),
            "coverage": kaspi["coverage"], "quotes": quoted, "notes": noted,
            "mended": mended, "rival": rival, "inked": inked,
            "textual": textual, "altered": altered, "sigla": SIGLA,
            "witnessed": book.stats.get("witnessed"),
            "conf": sum(len(v) for v in book.stats.get("confusions", {}).values()),
            "conftop": book.stats.get("conftop", []),
            "fixed": book.stats.get("fixed"),
            "collated": book.stats.get("collated"),
            "anchors": kaspi["part_anchors"], "missing": missing,
            "verify": verify["summary"], "maxscore": round(MAXSCORE, 2),
            "lexicon": len(lex), "flagged": flagged, "tokens": tokens,
            "minlen": quote.MINLEN,
        },
    }


def worklist(data: dict, dst: str, n: int = 40) -> None:
    """The units a human should adjudicate first, worst OCR at the top."""
    rows = [(k, u) for k, u in data["units"].items() if u.get("o") is not None]
    rows.sort(key=lambda t: (t[1]["o"], -(t[1].get("s") or 0)))
    m = data["meta"]
    out = [
        "# Adjudication worklist",
        "",
        "Units ranked by the share of word-forms that no clean Hebrew text in the",
        f"corpus attests ({m['lexicon']:,} forms). A low figure means the scan, the OCR,",
        "or both need a human eye. Consult the scan page given in the last column;",
        "the same page numbers index `out/AmudeiKesef_hebrewbooks_OCR_raw.txt`.",
        "",
        f"Across the {m['matched']} recovered units, {m['flagged']:,} of {m['tokens']:,} tokens "
        f"({m['flagged']/max(1,m['tokens']):.1%}) are unattested.",
        "",
        "| # | chapter | attested | evidence | validator | scan page |",
        "|--:|---------|---------:|---------:|-----------|----------:|",
    ]
    verdict = {"agree": "agrees", "near": "top-3", "disagree": "dissents",
               "short": "too short", None: "—"}
    for i, (k, u) in enumerate(rows[:n], 1):
        out.append("| %d | %s | %.0f%% | %s | %s | %s |"
                   % (i, data["labels"][k], 100 * u["o"],
                      "%.2f/%.2f" % (u["s"], MAXSCORE) if u["s"] else "front",
                      verdict.get(u.get("v"), "—"), u["p"]))
    open(dst, "w", encoding="utf-8").write("\n".join(out) + "\n")


# ── page ─────────────────────────────────────────────────────────────────────

PAGE = r"""<!doctype html>
<html lang="he" dir="rtl"><head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width,initial-scale=1">
<title>מורה נבוכים עם עמודי כסף ומשכיות כסף</title>
<style>
:root{
  --paper:#f7f3ea; --ink:#1e1a16; --rule:#d8cfbd; --dim:#8a7f6c;
  --hot:#c8531f; --lemma:#8a5a12; --mark:#f3e2b8; --pane:#fdfbf6;
}
*{box-sizing:border-box}
html,body{margin:0;height:100%}
body{
  background:var(--paper); color:var(--ink);
  font-family:"Frank Ruehl CLM","Taamey Frank CLM","David CLM","Noto Serif Hebrew",
              "Times New Roman",serif;
  font-size:17px; line-height:1.75;
  display:flex; flex-direction:column;
}
header{border-bottom:1px solid var(--rule);background:var(--pane);flex:0 0 auto}
.bar{display:flex;align-items:center;gap:.75rem;padding:.4rem .9rem;flex-wrap:wrap}
.bar+.bar{border-top:1px solid #e9e2d3}
h1{font-size:1.05rem;margin:0;font-weight:600;letter-spacing:.01em}
h1 small{color:var(--dim);font-weight:400;font-size:.8em;margin-inline-start:.5rem}
button,select,input{font:inherit;color:inherit;background:transparent;
  border:1px solid var(--rule);border-radius:3px;padding:.1rem .5rem;cursor:pointer}
button:hover{background:#efe8d8}
button[aria-pressed=true]{background:var(--ink);color:var(--paper);border-color:var(--ink)}
input{cursor:text;min-width:11rem}
.grow{flex:1}
#chips{display:flex;gap:.2rem;overflow-x:auto;padding:.35rem .9rem;scrollbar-width:thin}
#chips b{font-weight:600;color:var(--dim);padding:0 .35rem;align-self:center;
  font-size:.8rem;white-space:nowrap}
.chip{border:1px solid transparent;border-radius:3px;padding:.05rem .38rem;
  font-size:.85rem;min-width:1.9rem;text-align:center;color:var(--dim)}
.chip.has{color:var(--ink);border-color:var(--rule);background:#fff}
.chip.on{background:var(--ink);color:var(--paper);border-color:var(--ink)}

main{flex:1;min-height:0;display:grid;grid-template-columns:1fr 1.25fr 1fr;gap:0}
/* A build carrying no classical witnesses hides that pane and gives its
   measure to the two texts that remain, rather than leaving a column empty.
   Hidden and not removed: the renderer writes to it unconditionally, and a
   renderer that has to ask which build it is in is a renderer with a bug. */
body.duo main{grid-template-columns:1fr 1.3fr}
body.duo #left{display:none}
.pane{overflow:auto;padding:1.1rem 1.4rem 4rem;border-inline-start:1px solid var(--rule)}
.pane:first-child{border:0}
#centre{background:var(--pane)}
.pane h2{position:sticky;top:-1.1rem;margin:-1.1rem -1.4rem 1rem;
  padding:.45rem 1.4rem;background:inherit;border-bottom:1px solid var(--rule);
  font-size:.82rem;font-weight:600;letter-spacing:.06em;color:var(--dim);
  text-transform:none;z-index:2}
#right{background:var(--paper)} #left{background:var(--paper)}
h3{font-size:.8rem;letter-spacing:.05em;color:var(--dim);margin:1.6rem 0 .3rem;
  border-bottom:1px dotted var(--rule);padding-bottom:.15rem;font-weight:600}
h3:first-of-type{margin-top:0}
p{margin:0 0 .55rem;text-align:justify;text-justify:inter-word}
#centre p{font-size:1.06rem;line-height:1.95}
.work p{font-size:.95rem;line-height:1.7}
.work{margin-bottom:1.2rem}
.q{border-bottom:1px solid #d9c48d;cursor:pointer}
#right .q,#centre .q{color:var(--lemma)}
.q.hot{background:var(--mark);border-bottom-color:var(--hot);color:var(--hot)}
mark{background:var(--mark);color:inherit}
u.x,u.doubt,u.keep,u.fix,u.lex,u.most,u.seen,u.guide{text-underline-offset:.22em;
    text-decoration-thickness:1px}
u.x,u.doubt{text-decoration:underline wavy #c0392b8c}
u.keep{text-decoration:underline wavy #c9822a99}
u.fix{text-decoration:underline dashed #2a7ac999}
u.lex{text-decoration:underline dotted #7a6a4a99}
u.most{text-decoration:underline dotted #9aa89a99}
u.seen{text-decoration:underline dotted #6a8a9a99}
/* The textual register, and the only mark in the volume that is not about
   legibility. Solid rather than dotted or wavy — nothing here is uncertain;
   the page is read and the Guide is read and they differ — and in the lemma's
   own colour, because it lives inside a lemma and belongs to it. */
u.guide{text-decoration:underline solid #b98f4a80}
u.note{text-decoration:none}
body.clean u.x,body.clean u.doubt,body.clean u.keep,body.clean u.fix,
body.clean u.lex,body.clean u.most,body.clean u.seen,
body.clean u.guide{text-decoration:none}
.why{display:flex;flex-wrap:wrap;gap:.1rem 1rem;font-size:.72rem;
     color:var(--dim);margin:.5rem 0 0}
.why u{text-decoration-thickness:1px;text-underline-offset:.22em}

/* The apparatus: the reading this edition prints, then — after the bracket that
   every critical edition uses for the purpose — what it was corrected from and
   what the eye read instead, each rejected reading signed with its instrument.
   The ink comes last, because it is the evidence and not the claim.

   The image is sized to the line it sits in rather than to its own pixel
   dimensions — the crops come off the page at 600 dpi and differ in width by a
   factor of five, and a row of them at native size reads as a ransom note. */
sup.fn{font-size:.6em;line-height:0;color:var(--hot);font-variant-numeric:tabular-nums;
  padding-inline-start:.08em;font-weight:600}
.notes{display:flex;flex-wrap:wrap;gap:.2rem 1.1rem;margin:.7rem 0 0;padding-top:.45rem;
  border-top:1px dotted var(--rule);font-size:.78rem;color:var(--dim)}
.notes span{display:inline-flex;align-items:baseline;gap:.28rem;white-space:nowrap}
.notes b{color:var(--hot);font-weight:600;font-size:.9em;
  font-variant-numeric:tabular-nums}
.notes q{quotes:none;color:var(--ink)}
.notes s{text-decoration:none;color:var(--rule);padding-inline:.1rem}
.notes em{font-style:normal}
.notes em.was::before{content:'תוקן מ־';color:var(--dim);font-size:.9em;
  padding-inline-end:.15rem}
.notes sub{font-size:.78em;vertical-align:baseline;color:var(--hot);
  padding-inline-start:.1rem}
.notes img{height:1.15rem;width:auto;background:#fff;padding:1px;align-self:center;
  border:1px solid var(--rule);border-radius:2px}
body.clean sup.fn,body.clean .notes,body.nonotes sup.fn{display:none}

.badge{font-size:.72rem;border:1px solid var(--rule);border-radius:2rem;
  padding:.02rem .5rem;color:var(--dim);white-space:nowrap}
.badge.agree{border-color:#5d7a4a;color:#456034}
.badge.near{border-color:#b08a2a;color:#8a6a12}
.badge.disagree{border-color:#a8412a;color:#8d3320}
.empty{color:var(--dim);font-style:italic;font-size:.9rem}

dialog{border:1px solid var(--rule);background:var(--pane);color:var(--ink);
  max-width:44rem;padding:1.4rem 1.7rem;line-height:1.8;border-radius:3px}
dialog::backdrop{background:#1e1a1666}
dialog h4{margin:1.1rem 0 .3rem;font-size:.95rem}
dialog h4:first-child{margin-top:0}
dialog p{font-size:.95rem}
dialog b{color:var(--hot);font-weight:600}   /* the sigla, in the legend */
dialog em{font-style:normal;color:var(--dim)}
#hits{max-height:60vh;overflow:auto}
#hits div{padding:.35rem 0;border-bottom:1px dotted var(--rule);cursor:pointer;font-size:.9rem}
#hits div:hover{background:#efe8d8}
#hits i{color:var(--dim);font-style:normal;font-size:.8rem;margin-inline-start:.4rem}
@media (max-width:1100px){main{grid-template-columns:1fr}
  .pane{height:auto;overflow:visible;border-inline-start:0;border-top:1px solid var(--rule)}
  body{height:auto;display:block} main{display:block}}
@media print{
  body{height:auto;display:block;background:#fff}
  header,#chips,.noprint{display:none}
  main{display:grid;grid-template-columns:1fr 1.3fr 1fr}
  body.duo main{grid-template-columns:1fr 1.4fr}
  .pane{overflow:visible;height:auto}
  .q{border:0;color:inherit} .q.hot{background:none}
}
</style></head><body>
<header>
 <div class="bar">
  <h1>מורה נבוכים <small>עם עמודי כסף ומשכיות כסף לר׳ יוסף אבן כספי</small></h1>
  <span class="grow"></span>
  <span id="cite" class="badge"></span>
  <span id="ocr" class="badge"></span>
  <span id="conf" class="badge"></span>
  <input id="qbox" placeholder="חיפוש בכל הכרך…">
  <button id="about">על המהדורה</button>
 </div>
 <div class="bar">
  <button id="prev">→ הקודם</button><button id="next">הבא ←</button>
  <span id="here" style="font-weight:600"></span>
  <span class="grow"></span>
  <span id="toggles"></span>
 </div>
 <div id="chips"></div>
</header>
<main>
 <section class="pane" id="right"><h2>ר׳ יוסף אבן כספי</h2><div id="kaspi"></div></section>
 <section class="pane" id="centre"><h2>מורה נבוכים — תרגום ר׳ שמואל אבן תיבון</h2><div id="guide"></div></section>
 <section class="pane" id="left"><h2>מפרשים</h2><div id="wit"></div></section>
</main>
<dialog id="dlg"><div id="dlgbody"></div>
 <p style="margin-top:1.2rem"><button onclick="dlg.close()">סגירה</button></p></dialog>
<script type="application/octet-stream" id="data">__DATA__</script>
<script>
const $=(s,r=document)=>r.querySelector(s), $$=(s,r=document)=>[...r.querySelectorAll(s)];
let D, cur, hidden=new Set(), pin=null, idx=null;

(async()=>{
  // The corpus travels gzipped and base64'd. Hebrew in UTF-8 costs two bytes a
  // letter before gzip ever sees it; where the build has folded those bytes
  // into one — data-map carries the alphabet it used — the text comes back
  // one byte per character and is unfolded here.
  //
  // The codes begin at A0, not at 80, because "latin1" in the Encoding
  // Standard is a label for *windows-1252*, and that is the identity map only
  // from A0 up: bytes 80-9F decode to typographic punctuation and five of them
  // to U+FFFD. A payload folded into that range inflates without error, renders
  // without complaint, and is quietly the wrong text.
  const el=$('#data'), b64=el.textContent.trim(), map=el.dataset.map||'';
  let json;
  try{
    const bin=Uint8Array.from(atob(b64),c=>c.charCodeAt(0));
    const buf=await new Response(new Blob([bin]).stream()
          .pipeThrough(new DecompressionStream('gzip'))).arrayBuffer();
    json=new TextDecoder(map?'latin1':'utf-8').decode(buf);
    if(map) json=json.replace(/[\u00a0-\u00ff]/g,c=>map[c.charCodeAt(0)-160]);
  }catch(e){
    document.body.innerHTML='<p style="padding:2rem">הדפדפן אינו תומך ב־DecompressionStream.</p>';
    return;
  }
  D=JSON.parse(json);
  if(!D.wit.length) document.body.classList.add('duo');   // hide, don't remove: render() still writes there
  if(!D.meta.notes) document.body.classList.add('nonotes'); // ...and likewise a build with no scan crops
  chips(); toggles();
  /* the volume opens as the book does: on Kaspi's own preface */
  show(location.hash.slice(1)||(D.units['kaspi:0:0']&&D.units['kaspi:0:0'].a
       ?'kaspi:0:0':'ch:1:1'));
  addEventListener('hashchange',()=>show(location.hash.slice(1)));
})();

function chips(){
  const c=$('#chips');
  const add=(txt,key,cls)=>{const b=document.createElement('button');
    b.className='chip '+cls; b.textContent=txt; b.dataset.k=key;
    b.onclick=()=>location.hash=key; c.append(b); };
  const grp=t=>{const b=document.createElement('b'); b.textContent=t; c.append(b)};
  grp('פתיחה');
  for(const k of D.order) if(!k.startsWith('ch:')&&!k.startsWith('intro'))
    add(D.labels[k].split(' ')[0],k,has(k));
  for(const p of [1,2,3]){
    grp(['','א','ב','ג'][p]);
    add('הק׳','intro:'+p+':0',has('intro:'+p+':0'));
    for(const k of D.order.filter(k=>k.startsWith('ch:'+p+':')))
      add(k.split(':')[2],k,has(k));
  }
}
const has=k=>D.units[k]&&D.units[k].a?'has':'';

/* The apparatus under one commentary. A note is
      [lemma, ink, corrected-from, [[rejected reading, siglum], …]]
   and prints in that order behind the bracket a critical edition puts after its
   lemma: what this edition reads, then what it altered, then what a reader of
   the ink read instead, then the ink itself — the photograph last, because it
   is the evidence and not the claim. Any of the last three may be missing; a
   word with none of them was never given a number.

   The bracket is written ']' and appears as '[', because it is a neutral
   character in a right-to-left line and Unicode mirrors it. That is the glyph
   Hebrew critical editions print, and getting it by the bidi algorithm rather
   than by choosing the other bracket means it stays right if a note ever runs
   left to right.

   Everything here was escaped by the build — the image is a base64 data URL and
   every reading went through esc() — because the apparatus reaches the document
   as innerHTML. */
const note=(x,i)=>'<span><b>'+(i+1)+'</b><q>'+x[0]+'</q><s>]</s>'
  +(x[2]?'<em class="was">'+x[2]+'</em>':'')
  +x[3].map(v=>'<em>'+v[0]+'<sub>'+v[1]+'</sub></em>').join('')
  +(x[1]?'<img src="'+x[1]+'" alt="">':'')+'</span>';
const apparatus=n=>!n||!n.length?'':'<div class="notes">'+n.map(note).join('')+'</div>';

function toggles(){
  const t=$('#toggles');
  const mk=(id,name)=>{const b=document.createElement('button');
    b.textContent=name; b.setAttribute('aria-pressed','true');
    b.onclick=()=>{hidden.has(id)?hidden.delete(id):hidden.add(id);
      b.setAttribute('aria-pressed',String(!hidden.has(id))); render()};
    t.append(b)};
  mk('amudei','עמודי כסף'); mk('maskiyot','משכיות כסף');
  for(const [id,name] of D.wit) mk(id,name);
  const b=document.createElement('button');
  b.textContent='סימון שגיאות'; b.setAttribute('aria-pressed','true');
  b.onclick=()=>{document.body.classList.toggle('clean');
    b.setAttribute('aria-pressed',String(!document.body.classList.contains('clean')))};
  t.append(b);
}

function show(k){
  if(!D.units[k]) k='ch:1:1';
  cur=k; pin=null;
  $('#here').textContent=D.labels[k];
  $$('.chip').forEach(c=>c.classList.toggle('on',c.dataset.k===k));
  const on=$('.chip.on'); if(on) on.scrollIntoView({inline:'center',block:'nearest'});
  render();
  $$('.pane').forEach(p=>p.scrollTop=0);
  if(location.hash.slice(1)!==k) history.replaceState(null,'',' #'+k);
}

function render(){
  const u=D.units[cur];
  $('#guide').innerHTML=u.g||'<p class="empty">—</p>';
  let h='';
  const n=u.n||{};
  if(u.a&&!hidden.has('amudei'))  h+='<div class="work"><h3>עמודי כסף</h3>'+u.a+apparatus(n.a)+'</div>';
  if(u.m&&!hidden.has('maskiyot'))h+='<div class="work"><h3>משכיות כסף</h3>'+u.m+apparatus(n.m)+'</div>';
  $('#kaspi').innerHTML=h||'<p class="empty">אין פירוש כספי לפרק זה בדפוס פרנקפורט תר״ח.</p>';
  let w='';
  for(const [id,name] of D.wit) if(u.w[id]&&!hidden.has(id))
    w+='<div class="work"><h3>'+name+'</h3>'+u.w[id]+'</div>';
  $('#wit').innerHTML=w||'<p class="empty">—</p>';

  $('#cite').textContent=u.p?('פרנקפורט תר״ח, דף '+u.p):'—';
  const o=$('#ocr');
  o.textContent=u.o==null?'':('מלים מאושרות '+Math.round(u.o*100)+'%');
  o.className='badge '+(u.o==null?'':u.o>=.9?'agree':u.o>=.8?'near':'disagree');
  o.style.display=u.o==null?'none':'';
  const c=$('#conf');
  if(u.s){ c.className='badge '+(u.v||''); c.textContent=
    'ראיות '+u.s.toFixed(2)+'/'+D.meta.maxscore+
    ' · '+({heading:'כותרת',lemma:'ציטוט'}[u.r]||u.r)+
    ' · '+({agree:'אימות מסכים',near:'אימות קרוב',disagree:'אימות חולק',
            short:'קצר מדי לאימות'}[u.v]||'ללא אימות');
  } else if(u.a){ /* front matter: cut at a fixed incipit or a measured
    quotation seam, not matched by the chapter template — so no template
    score, and the verifier's verdict is the only claim made for it */
    c.className='badge '+(u.v||''); c.textContent='שער הספר · '+
    ({agree:'אימות מסכים',near:'אימות קרוב',disagree:'אימות חולק',
      short:'קצר מדי לאימות'}[u.v]||'ללא אימות');
  } else { c.className='badge'; c.textContent='טקסט בסיס בלבד'; }

  for(const s of $$('.q')){
    s.onmouseenter=()=>light(s.dataset.q,true);
    s.onmouseleave=()=>{if(!pin) light(s.dataset.q,false)};
    s.onclick=()=>{ if(pin) light(pin,false);
      pin=(pin===s.dataset.q)?null:s.dataset.q;
      if(pin){light(pin,true);
        const t=$$('#guide .q').find(x=>x.dataset.q===pin);
        if(t) t.scrollIntoView({block:'center',behavior:'smooth'});}};
  }
}
const light=(q,on)=>$$('.q[data-q="'+q+'"]').forEach(e=>e.classList.toggle('hot',on));

const step=d=>{const i=D.order.indexOf(cur); const j=i+d;
  if(j>=0&&j<D.order.length) location.hash=D.order[j]};
$('#prev').onclick=()=>step(-1); $('#next').onclick=()=>step(1);
addEventListener('keydown',e=>{
  if(e.target.tagName==='INPUT'){ if(e.key==='Escape') e.target.blur(); return }
  if(e.key==='ArrowRight') step(-1);
  else if(e.key==='ArrowLeft') step(1);
  else if(e.key==='/'){e.preventDefault(); $('#qbox').focus()}
});

/* search: index built once, on demand, from the rendered strings */
const strip=h=>h.replace(/<[^>]*>/g,' ').replace(/[֑-ׇ]/g,'')
                 .replace(/[׳״'"׳״]/g,'');
const fold=s=>s.replace(/ך/g,'כ').replace(/ם/g,'מ').replace(/ן/g,'נ')
               .replace(/ף/g,'פ').replace(/ץ/g,'צ');
function index(){
  if(idx) return idx;
  idx=[];
  for(const k of D.order){ const u=D.units[k];
    const put=(w,h)=>{ if(h) idx.push([k,w,fold(strip(h))]) };
    put('מורה',u.g); put('עמודי כסף',u.a); put('משכיות כסף',u.m);
    for(const [id,name] of D.wit) put(name,u.w[id]);
  }
  return idx;
}
$('#qbox').addEventListener('keydown',e=>{ if(e.key!=='Enter') return;
  const q=fold(strip(e.target.value)).trim(); if(q.length<2) return;
  const hits=[];
  for(const [k,w,t] of index()){
    let i=t.indexOf(q);
    while(i>=0&&hits.length<400){
      hits.push([k,w,t.slice(Math.max(0,i-45),i+q.length+45)]);
      i=t.indexOf(q,i+q.length);
    }
  }
  const body=$('#dlgbody');
  body.innerHTML='<h4>‏'+hits.length+' תוצאות עבור «'+q+'»</h4><div id="hits"></div>';
  const box=$('#hits');
  for(const [k,w,s] of hits.slice(0,300)){
    const d=document.createElement('div');
    d.innerHTML=s.replace(q,'<mark>'+q+'</mark>')+'<i>'+D.labels[k]+' · '+w+'</i>';
    d.onclick=()=>{location.hash=k; dlg.close()};
    box.append(d);
  }
  dlg.showModal();
});

$('#about').onclick=()=>{
  const m=D.meta, v=m.verify;
  const miss=[1,2,3].map(p=>'חלק '+['','א','ב','ג'][p]+': '+
      (m.missing[p].length?m.missing[p].join(', '):'—')).join('<br>');
  $('#dlgbody').innerHTML=`
  <h4>מה יש כאן</h4>
  <p>טקסט המורה — תרגום ר׳ שמואל אבן תיבון, לפי מהדורת ספריא (רשות הרבים).
  פירושי ר׳ יוסף אבן כספי — <i>עמודי כסף</i> ו<i>משכיות כסף</i> — הוצאו בזיהוי
  תווים מדפוס ש״ז ווערבלונר, פרנקפורט תר״ח (1848), והושבו למקומם בספר המורה
  בדרך אלגוריתמית. ${D.wit.length
    ? 'אפודי, שם טוב, קרשקש, נרבוני ואברבנאל — ספריא.'
    : 'מהדורה מצומצמת: המורה וכספי בלבד. חמשת המפרשים הקלאסיים הושמטו כדי '
      + 'שהקובץ ייכנס לשיחה; המילון שלפיו נמדדת איכות הזיהוי עדיין נבנה מכולם.'}</p>
  <h4>איך שוחזר המבנה</h4>
  <p>הדפוס אינו מסמן את הפרקים אלא בכותרת רצה בגוף השורה, ולעתים קרובות
  אינו מסמן כלל. לכל אחד ממאה שבעים ושמונה פרקי המורה נבנתה &quot;תבנית&quot;:
  מספר הפרק באותיות, ופתיחת הפרק לפי אבן תיבון. כל מועמד בסריקה נמדד מול
  התבניות בשני אותות בלתי־תלויים — דמיון לוונשטיין משוקלל לשגיאות זיהוי
  אופייניות (ד/ר, ב/כ, ה/ח/ת), וחפיפת מחרוזות־שלוש בין הסביבה לפתיחה — ותכנות
  דינמי מונוטוני בחר את ההשמה הכוללת הטובה ביותר. נמצאו
  ${m.matched} מתוך ${m.total} פרקים (${Math.round(m.coverage*100)}%).</p>
  <p>שערי הכרך — הקדמת כספי עצמו, פירושו לאגרת ולפתיחה, ופירושי ההקדמות לשלושת
  החלקים (${m.front||0} יחידות) — אינם פרקים ואין להם תבנית, ובמהדורה קודמת של
  קובץ זה נבלעו בפרקים הסמוכים: פירוש הפתיחה כולו נדפס כ&quot;פרק א׳&quot; של
  החלק הראשון, וכ״ה ההקדמות נתלו בזנב פא״ו. הם נחתכים עתה בפתיחים קבועים
  (&quot;אמר יוסף אבן כספי&quot;) ובתפר הנמדד במקום שבו פוסק הציטוט מחיבור אחד
  ומתחיל בציטוט הבא, והבדיקה העצמאית שלהלן מאשרת כל אחד מהם מול חיבורו. פירוש
  לפרק א׳ של החלק הראשון אין בדפוס תר״ח, והמהדורה אומרת זאת במקומו.</p>
  <h4>איך נבדק</h4>
  <p>בדיקה עצמאית השוותה כל יחידה שהתקבלה אל כל חלקי המורה — הפרקים, האגרת,
  הפתיחה וההקדמות — בעזרת מדד קוסינוס
  על מחרוזות־ארבע משוקללות ב־idf — אות שהמנוע הראשון לא ראה כלל.
  ${v.agree} מתוך ${v.scored} (${Math.round(v.agree_rate*100)}%) קיבלו את אותה
  התשובה במקום הראשון, ${Math.round(v.top3_rate*100)}% בשלושת הראשונים;
  ${v.short} יחידות קצרות מכדי להצביע. התווית שבראש העמוד מציגה את פסק הבדיקה
  לפרק הנוכחי — אין כאן הסתרה של אי־ודאות.</p>
  <h4>הלמות</h4>
  <p>הדפוס מבחין בין דברי המורה לדברי כספי בשינוי אות בלבד, וזיהוי התווים אינו
  רואה זאת. הלמות שוחזרו כאן כמחרוזות משותפות מרביות (${m.minlen} אותיות ומעלה)
  בין הפירוש ובין פרק אבן תיבון; ${m.quotes} כאלה נמצאו. הסף אינו משוער אלא
  נמדד: כל יחידה הורצה גם מול פרק אקראי וגם מול הפרק הסמוך, והסף נבחר במקום
  שבו הרעש יורד מתחת לאחוז. כל למה פותחת פסקה בפירוש ומקושרת למקומה בטקסט —
  מעבר עכבר מדליק את שני הצדדים, הקשה מקבעת וגוללת אל המקום במורה.</p>
  <h4>איפה הזיהוי נכשל</h4>
  <p>מילון של ${m.lexicon.toLocaleString('he')} צורות מילים נבנה מן הטקסטים
  הנקיים שבכרך עצמו — אבן תיבון וחמשת המפרשים — והוא באותו רובד לשון ובאותה
  כתיב שבו כתב כספי. כל מלה בפירוש שאינה מאושרת בו (גם לאחר קילוף מוקדמות
  וה־בכלמ״ש) מסומנת בקו גלי במקומה: ${m.flagged.toLocaleString('he')} מתוך
  ${m.tokens.toLocaleString('he')} (${(100*m.flagged/m.tokens).toFixed(1)}%).
  אין כאן תיקון אלא הצבעה — הקורא רואה את הפגם ולא רק שומע עליו. אפשר לכבות
  את הסימון בכפתור «סימון שגיאות».</p>
  <h4>מנין באה כל מלה</h4>
  <p>ארבע קריאות של אותו דף — שכבת הטקסט של המוציא לאור, שתי הרצות של טסראקט
  ברזולוציות ובמצבי פילוח שונים, וקריאה רביעית שנעשתה בעין מתוך הסריקה עצמה —
  הועמדו זו מול זו מלה במלה. מלה שכל הקריאות החזירו במשווה, או שבתוך למה
  הסכימה עם אבן תיבון, נדפסת חלקה — לסמן שלושה רבעים מן העמוד אינו אומר לעין
  דבר; כל מלה שנחלקו עליה נושאת את סימן ההכרעה שהביא אותה לכאן:</p>
  <div class="why">
   <span><u class="most">מלה</u> — רוב הקוראים</span>
   <span><u class="seen">מלה</u> — הקריאה שבעין, כנגד חילוף אות שהמכונות
    נכשלות בו כאחת</span>
   <span><u class="lex">מלה</u> — רק קריאה אחת היא מלה עברית</span>
   <span><u class="fix">מלה</u> — תוקנה לפי טבלת החילופים של הכרך</span>
   <span><u class="keep">מלה</u> — כמה קריאות אפשריות; נשמרה הראשונה</span>
   <span><u class="doubt">מלה</u> — אף קריאה אינה מלה</span>
   <span><u class="guide">מלה</u> — בתוך למה; הושוותה לאבן תיבון</span>
  </div>
  <p>טבלת החילופים אינה שאולה מספרות הזיהוי אלא נלמדה מן ההכרעה עצמה. כל מלה
  שנקראה בשתי דרכים מוסרת את הקריאות שנדחו, ובכל מקום שבו הקריאה שנתקבלה היא
  מלה עברית והנדחית אינה מלה כלל, הנדחית היא שיבוש של המתקבלת מעצם הגדרתה —
  אין כאן שיפוט על לשונו של כספי, שהרי צורה שאינה צורה אין עליה מה לשפוט.
  ${(m.witnessed||0).toLocaleString('he')} זוגות כאלה, כולם המכשיר הזה נכשל
  בדיו הזאת, ומהם ${(m.conf||0).toLocaleString('he')} חילופי אותות
  — ${(m.conftop||[]).map(([a,b,n])=>'‏'+a+'‎ במקום ‏'+b+'‎ '+n.toLocaleString('he')+
  ' פעם').join(', ')}. ${(m.fixed||0).toLocaleString('he')} מלים תוקנו לפיה.</p>
  <p>קודם לכן נלמדה הטבלה ממקום אחר: מן ההשוואה לאבן תיבון, כלומר מן ההבדלים
  שבין שתי מהדורות של ספר בן המאה הארבע־עשרה. אלה אינם שיבושי סריקה אלא מסירה,
  והטבלה שיצאה משם לימדה על גלגולי המורה ולא על הסורק — ובסף של עשר עדויות לא
  לימדה כלום, שהרי לא הגיע לשם ולו זוג אחד. הכלל היחיד במהדורה שנשען על אותו סף
  מעולם לא פעל אפוא, ותיאורו נדפס כאן כאילו פעל. עכשיו הוא פועל.</p>
  <p>תיקון מתקבל רק כשהוא יחיד; מלה שכל הקריאות
  הסכימו עליה נשארת כמות שהיא גם אם אינה במילון, שאם לא כן היה המהדיר מנרמל
  את לשונו של כספי במקום למסור אותה.</p>
  <p>גם המדד הזה נבדק: כשמוציאים מפרש שלם מן המילון ומעבירים את הטקסט הנקי שלו
  באותה בדיקה, שיעור הסימון הוא 1.1%–3.8% בלבד. כלומר כשתי נקודות אחוז הן
  חידוש לשוני רגיל, וכעשרים ושתיים הן פגם סריקה — מלה מסומנת כאן היא בקירוב
  פי עשרה יותר טעות זיהוי מאשר צורה נדירה.</p>
  <h4>מה שנשאר בספק — הדיו עצמה</h4>
  <p>שלוש הקריאות הראשונות כולן מכונה, ומכונה נכשלת בדרכים דומות: מלים שהדפוס
  מטביע בבירור גמור — ‏בהקדמה‎, ‏משתתף‎, ‏מאמינים‎ — חזרו משלושתן משובשות באותו
  אופן, וכל שלב שנבנה מעליהן ירש את הכישלון, שהרי אין אחד מהם רואה את הדף.
  לפיכך נוספה קריאה רביעית שנעשתה בהבטה בסריקה עצמה, והיא נכנסה להכרעה ככל
  קריאה אחרת — בלי זכות בכורה ובלי זכות וטו. כוחה אינו בסמכות אלא באי־תלות:
  טעויותיה אינן טעויותיהן, ולכן הסכמה בינה לבין אחת מהן היא ראיה.</p>
  <p>מה שנותר בספק אחרי כן הוא ברובו שמות פרטיים, שמות מקומות ויהודית־אשכנזית
  של שער תר״ח — ‏ווערבלונר‎, ‏דלייפצג‎, ‏דמיין‎ — מלים שאין מילון עברי שיאשר
  אותן משום שאינן עבריות. על אלה אין למהדורה מה להוסיף, ולהעמיד פנים שיש לה
  היה המעשה הבלתי־הגון היחיד שבידה לעשות. תחת זאת היא אומרת מה קראה, מה דחתה
  ומה שינתה, ומדפיסה את הדיו בצדה.</p>
  <h4>חילופי הקריאות שבשוליים</h4>
  <p>כל מלה מסומנת נושאת מספר קטן, ובשולי הפירוש באה הערה בסדר הנהוג במהדורות
  ביקורתיות: הקריאה הנדפסת כאן, סוגר, ואחריו מה שיש למהדורה לומר עליה.
  ${(m.notes||0).toLocaleString('he')} הערות בכרך.</p>
  <p><em>תוקן מ־</em> מציין שהמהדורה שינתה את מה שמצאה, ואחריו בא הנוסח שלפני
  התיקון. ${(m.mended||0).toLocaleString('he')} תיקונים כאלה בפירושים שנדפסו
  כאן, והם כל התיקונים שיש: המהדורה סופרת אותם מן הספר ולא מן ההערות, ומדפיסה
  כאן את שני המספרים — ${(m.altered||0).toLocaleString('he')} שונו,
  ${(m.mended||0).toLocaleString('he')} מדווחים${m.altered===m.mended?'':
  ', וההפרש '+(m.altered-m.mended).toLocaleString('he')+' הוא פגם'}. כל שאר
  ההערות הן קריאה של הדף, אבל תיקון הוא ידו של המהדיר, וזו החובה האחת שאין
  מהדורה רשאית לוותר עליה מפני הקיצור.</p>
  <p>עד לא כבר הטענה הזאת לא היתה נכונה. ארבע מאות עשרים וחמישה תיקונים לא
  הגיעו אל הדף — רובם משום שנעשו בתוך למה, וסימן שנפל בתוך למה נדחה מפני
  הלמה ונעלם עמו — כלומר דווקא המקום שבו עושה המהדורה את רוב מלאכתה היה המקום
  שממנו לא דיווחה דבר. עכשיו הסימן יושב בתוך הלמה ולא במקומה.</p>
  <p>אחריו באות הקריאות שנדחו, כל אחת חתומה באות מי שהחזיר אותה. שתי מערכות
  הן, ואין לערבבן:</p>
  <p><b>ע</b> הקריאה שבעין, <b>ש</b> שכבת הטקסט של המוציא לאור, <b>ט</b>
  טסראקט — סימני מכשירים ולא סימני כתבי־יד. שלושתם קראו אותו עצם עצמו, דפוס
  פרנקפורט תר״ח, ולפיכך מחלוקת ביניהם היא ענין של קריאוּת ולא של מסירה;
  מהדורה שתקרא לזה חילופי נוסחאות תספר לקורא שצירפה עדים שלא ראתה.</p>
  <p><b>ת</b> אבן תיבון — וזה הדבר האחר. הלמות של כספי הן המורה בתרגום אבן
  תיבון, ובמקום שלמה נבדלת מן המורה אין הדבר נוגע לדיו כלל: כספי מצטט את כתב
  היד שלפניו, או שהמסדר בפרנקפורט כותב ‏המושאלים‎ במקום ‏המשאלים‎. איש לא טעה
  בקריאה. זה חילוף נוסח במובן הישן, הראשון והיחיד במהדורה זו, ולפיכך ניתן לו
  סימן משלו. ${(m.textual||0).toLocaleString('he')} כאלה, וכל אחד מהם הוא
  המהדורה מסרבת להחליף את מה שכתוב בדף בספר מוכר יותר.</p>
  <p>${(m.collated||0).toLocaleString('he')} מלים בתוך למות נבדלות מאבן תיבון
  ונשארו כמות שהן. מהדורה קודמת החליפה את כולן בשקט — ‏ר״ל‎ של כספי נעשה שם
  ‏אל‎ — וזו טעות של מין אחר לגמרי מטעות סריקה: לא קריאה מוטעית של הדף אלא
  הדפסת נוסח של ספר אחד תחת שמו של אחר.</p>
  <p>לא כל דחייה של מכשיר נדפסת, ולא מטעמי קיצור. רוב המחלוקות בין הקוראים
  אינן חילוף אלא כשל מוכר של מכונה — ‏עוד‎ שנקרא ‏עור‎ הוא הכשל ב־ד/ר,
  ${((m.conftop||[]).find(([a,b])=>a==='ר'&&b==='ד')||[0,0,0])[2]
  .toLocaleString('he')} פעמים בסריקה הזאת, והדפסתו מלמדת על טסראקט ולא על
  כספי. נדפסת דחייה כזאת רק כשהקריאה שבעין היא שנדחתה, וכשמה שקראה יכול היה
  לעמוד באותה דיו: מלה עברית, שתי אותיות ומעלה, באורך הלמה עד כדי אות.
  ${(m.rival||0).toLocaleString('he')} כאלה. השאר אינן מוסתרות אלא אינן
  מודפסות — קובץ ההכרעה שבמאגר מוסר את כולן, לכל מלה בכרך. על דחייה של אבן
  תיבון אין סינון כזה: אין שם שאלה מה יכלה הדיו להיראות, ולכן היא נדפסת
  תמיד.</p>
  ${m.inked ? `<p>אחרון בהערה בא חיתוך הסריקה של אותה מלה בלבד — לא שורה ולא
  הקשר, שההקשר כבר לפניך — ${m.inked.toLocaleString('he')} חיתוכים כאלה. הוא בא
  אחרון משום שהוא הראיה ולא הטענה. אין כאן טענה אלא ראיה, והקורא שופט בעצמו.</p>`
  : `<p>מהדורה זו נושאת את דברי חילופי הקריאות ולא את הדיו עצמה: חיתוכי הסריקה
  הם רוב משקלו של הקובץ, ומה שנחתך כאן כדי שייכנס לשיחה הוא הם ולא הקריאות.
  מלה שכל שהיה למהדורה לומר עליה הוא תמונתה אינה נושאת כאן מספר כלל — מספר
  המפנה אל ראיה שאינה בקובץ גרוע ממחיקתו. התמונות במהדורה המלאה.</p>`}
  <p>כל ההערות נכבות בכפתור «סימון שגיאות».</p>
  <h4>פרקים שלא נמצאו בדפוס</h4>
  <p style="font-size:.88rem">${miss}</p>
  <h4>מקלדת</h4>
  <p>← הפרק הבא · → הפרק הקודם · / חיפוש</p>`;
  dlg.showModal();
};
</script></body></html>
"""


def main() -> None:
    base = os.path.join(os.path.dirname(os.path.abspath(__file__)), "..")
    data = build(base)
    raw = json.dumps(data, ensure_ascii=False, separators=(",", ":")).encode()
    blob = base64.b64encode(gzip.compress(raw, 9)).decode()
    dst = os.path.abspath(f"{base}/out/MorehNevukhim_KaspiEdition.html")
    open(dst, "w", encoding="utf-8").write(PAGE.replace("__DATA__", blob))
    work = os.path.abspath(f"{base}/out/ocr_worklist.md")
    worklist(data, work)

    m = data["meta"]
    print(f"units      : {len(data['units'])} ({m['matched']}/{m['total']} with Kaspi)",
          file=sys.stderr)
    print(f"lemmata    : {m['quotes']} quotation links "
          f"(MINLEN={m['minlen']})", file=sys.stderr)
    print(f"lexicon    : {m['lexicon']:,} word-forms; "
          f"{m['flagged']:,}/{m['tokens']:,} tokens unattested "
          f"({m['flagged']/max(1,m['tokens']):.1%})", file=sys.stderr)
    print(f"payload    : {len(raw)/1e6:.2f} MB json -> {len(blob)/1e6:.2f} MB base64",
          file=sys.stderr)
    print(f"file       : {dst} ({os.path.getsize(dst)/1e6:.2f} MB)", file=sys.stderr)
    print(f"worklist   : {work}", file=sys.stderr)


if __name__ == "__main__":
    main()
