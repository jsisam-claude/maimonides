#!/usr/bin/env python3
"""Find the words Kaspi is quoting, and where they sit in the Guide.

Kaspi comments lemma-by-lemma: he sets a few words of Maimonides, then his
remark, then the next few words. The 1848 print marks the join only by a ``וג׳``
(``etc.``) and a change of face that OCR cannot see — so the lemmata have to be
recovered from the text itself.

They are recoverable because a lemma is a *verbatim* quotation. Reduce both the
commentary and Ibn Tibbon's chapter to bare letters, then take every maximal
common substring of at least MINLEN letters: those runs are the lemmata, and
their position in the chapter is where the comment attaches. Everything shorter
is ordinary shared Hebrew and is ignored.

Two details make it work on OCR:

* finals are folded and everything but א–ת dropped, so ``וְג׳``/``ו״ג``/spacing
  damage cannot break a run;
* an index map is carried alongside, so a span found in the reduced string can
  be painted back onto the original characters — niqqud, punctuation and all.

Cost is linear in the two texts: the chapter's K-grams go into a dictionary,
the commentary is scanned once, and each hit is extended greedily.

Choosing MINLEN
---------------
The threshold is not guessed; ``calibrate()`` measures it. Each unit is run
against its own chapter (signal) and against two null models: a chapter drawn
at random, and the *neighbouring* chapter — the hardest null, since adjacent
chapters share both subject and vocabulary, and since Kaspi genuinely
cross-refers to them. Measured over the 153 recovered units:

    MINLEN   hits   random-null   adjacent-null
      10      842        23            158
      11      639        13            100
      12      499         4             67
      14      333         2             29

Twelve letters is the knee: it keeps three quarters more lemmata than 14 while
the random-null rate stays under one per cent. The true false-positive rate
lies between the two nulls, nearer the random one, because part of the
adjacent-null count is real quotation of the neighbouring chapter.

Dependencies: none (Python standard library).
"""
from __future__ import annotations

import re
from collections import defaultdict

FINALS = str.maketrans("ךםןףץ", "כמנפצ")
LETTER = re.compile(r"[א-ת]")

MINLEN = 12      # letters; below this, matches are coincidence not quotation
SEED = 8         # dictionary key length, must be <= MINLEN


def reduce(s: str) -> tuple[str, list[int]]:
    """Bare-letter form of *s*, plus the original index of each kept letter."""
    keep, idx = [], []
    for i, c in enumerate(s):
        if LETTER.match(c):
            keep.append(c)
            idx.append(i)
    return "".join(keep).translate(FINALS), idx


def quotations(comment: str, base: str) -> tuple[list[tuple[int, int]],
                                                 list[tuple[int, int]]]:
    """Maximal verbatim runs shared by *comment* and *base*.

    Returns two lists of (start, end) spans in original character offsets —
    one into the commentary, one into the base text — index-aligned, so span
    *k* of the first is the same quotation as span *k* of the second.
    """
    c, ci = reduce(comment)
    b, bi = reduce(base)
    if len(c) < MINLEN or len(b) < MINLEN:
        return [], []

    seeds = defaultdict(list)
    for i in range(len(b) - SEED + 1):
        seeds[b[i:i + SEED]].append(i)

    cspans, bspans = [], []
    i = 0
    while i <= len(c) - SEED:
        hits = seeds.get(c[i:i + SEED])
        if not hits:
            i += 1
            continue
        best = (0, 0, 0)                       # length, cstart, bstart
        for p in hits[:64]:                    # cap: a stock phrase can recur
            lo = 0
            while (i - lo > 0 and p - lo > 0 and c[i - lo - 1] == b[p - lo - 1]):
                lo += 1
            hi = SEED
            while (i + hi < len(c) and p + hi < len(b) and c[i + hi] == b[p + hi]):
                hi += 1
            if lo + hi > best[0]:
                best = (lo + hi, i - lo, p - lo)
        n, cs, bs = best
        if n >= MINLEN:
            cspans.append((ci[cs], ci[cs + n - 1] + 1))
            bspans.append((bi[bs], bi[bs + n - 1] + 1))
            i = cs + n
        else:
            i += 1
    return cspans, bspans


def merge(spans: list[tuple[int, int]]) -> list[tuple[int, int]]:
    out: list[tuple[int, int]] = []
    for s, e in sorted(spans):
        if out and s <= out[-1][1]:
            out[-1] = (out[-1][0], max(out[-1][1], e))
        else:
            out.append((s, e))
    return out


def calibrate(units_path: str, corpus_path: str,
              lengths=(10, 11, 12, 13, 14, 16)) -> list[dict]:
    """Signal-vs-null counts per MINLEN. Reproduces the table in the docstring."""
    import json
    import random

    global MINLEN, SEED
    keep = (MINLEN, SEED)
    moreh = json.load(open(corpus_path, encoding="utf-8"))["moreh"]
    units = json.load(open(units_path, encoding="utf-8"))["units"]
    chapters = [k for k in moreh if k.startswith("ch:")]
    rng = random.Random(7)

    def n(comment: str, key: str, m: int) -> int:
        global MINLEN, SEED
        MINLEN, SEED = m, min(8, m)
        return len(quotations(comment, "\n".join(moreh[key]))[0])

    rows = []
    for m in lengths:
        sig = rnd = adj = 0
        for u in units:
            txt = u["amudei"] + " " + u["maskiyot"]
            p, c = u["part"], u["chapter"]
            near = f"ch:{p}:{c+1}" if f"ch:{p}:{c+1}" in moreh else f"ch:{p}:{c-1}"
            sig += n(txt, u["unit"], m)
            rnd += n(txt, rng.choice([k for k in chapters if k != u["unit"]]), m)
            adj += n(txt, near, m)
        rows.append({"minlen": m, "hits": sig, "random_null": rnd, "adjacent_null": adj})
    MINLEN, SEED = keep
    return rows


if __name__ == "__main__":
    import os
    import sys

    base = os.path.join(os.path.dirname(os.path.abspath(__file__)), "..")
    print(f"{'MINLEN':>7} {'hits':>7} {'random':>8} {'adjacent':>9}", file=sys.stderr)
    for r in calibrate(f"{base}/data/kaspi_units.json", f"{base}/data/corpus.json"):
        print(f"{r['minlen']:>7} {r['hits']:>7} {r['random_null']:>8} "
              f"{r['adjacent_null']:>9}", file=sys.stderr)
