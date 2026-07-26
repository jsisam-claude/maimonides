#!/usr/bin/env python3
"""Align the ʿAmudei Kesef / Maskiyot Kesef scan onto the Guide's chapters.

Kaspi's commentary is not chapter-tagged in any machine-readable way: the 1848
headings are set in a display face that OCR renders unreliably (474 raw hits for
"פרק", almost all of them ordinary prose). Rather than parse headings, this
module aligns by *content*: Kaspi quotes the Guide constantly, and we now hold
the Guide verbatim (Ibn Tibbon, Sefaria).

Method
------
1. Normalise both sides: strip niqqud/cantillation, fold final forms, drop
   everything that is not a Hebrew letter. This absorbs most OCR damage, since
   Tesseract's errors here are letter substitutions (ד/ר, כ/ב, ת/ח) inside
   otherwise well-segmented words.
2. Represent each Guide chapter and each scan page as a set of character
   4-grams. Containment — |page ∩ chapter| / |page| — tolerates the ~15–20 %
   of tokens OCR gets wrong, because a wrong letter only spoils the four grams
   touching it.
3. Both sequences run in the same order, so the assignment is monotonic.
   A Needleman–Wunsch-style DP over (page, chapter) with a non-decreasing
   constraint therefore beats greedy best-match: a page whose own score is
   ambiguous is pinned by its neighbours.

The volume contains both commentaries in sequence, i.e. it traverses the Guide
twice. The traversal split is detected first, and each half is aligned
independently.

Dependencies: none (Python standard library).
"""
from __future__ import annotations

import json
import os
import re
import sys
from collections import defaultdict

N = 4
FINALS = str.maketrans("ךםןףץ", "כמנפצ")
NONLETTER = re.compile(r"[^א-ת]")
PAGE_RE = re.compile(r"===== PDF3 page (\d+) =====")


def norm(s: str) -> str:
    return NONLETTER.sub("", s.translate(FINALS))


def grams(s: str, n: int = N) -> set[str]:
    return {s[i:i + n] for i in range(len(s) - n + 1)}


def load_pages(path: str) -> list[tuple[int, str]]:
    raw = open(path, encoding="utf-8").read()
    parts = PAGE_RE.split(raw)
    out = []
    for i in range(1, len(parts) - 1, 2):
        out.append((int(parts[i]), norm(parts[i + 1])))
    return [(p, grams(t)) for p, t in out if len(t) > 400]


def load_chapters(corpus_path: str) -> list[tuple[str, set[str]]]:
    corpus = json.load(open(corpus_path, encoding="utf-8"))
    moreh = corpus["moreh"]

    def sort_key(k):
        kind, p, c = k.split(":")
        rank = {"letter": 0, "tibbon": 1, "pref": 2, "intro": 3, "ch": 4}.get(kind, 9)
        return (int(p), rank, int(c))

    keys = sorted((k for k in moreh if k.startswith(("ch:", "intro:", "pref:", "letter:"))),
                  key=sort_key)
    return [(k, grams(norm(" ".join(moreh[k])))) for k in keys]


def containment(pg: set[str], ch: set[str]) -> float:
    return len(pg & ch) / len(pg) if pg else 0.0


def monotonic_align(pages, chapters, band=None):
    """DP: assign each page a chapter index, non-decreasing. Returns [idx]."""
    P, C = len(pages), len(chapters)
    if not P or not C:
        return []
    score = [[containment(pg, ch) for _, ch in chapters] for _, pg in pages]
    # best[i][j] = best total score for pages 0..i with page i at chapter j
    NEG = float("-inf")
    best = [[NEG] * C for _ in range(P)]
    back = [[0] * C for _ in range(P)]
    best[0] = score[0][:]
    for i in range(1, P):
        run = NEG
        arg = 0
        for j in range(C):
            if best[i - 1][j] > run:
                run, arg = best[i - 1][j], j
            if run == NEG:
                continue
            best[i][j] = run + score[i][j]
            back[i][j] = arg
    j = max(range(C), key=lambda x: best[P - 1][x])
    path = [j]
    for i in range(P - 1, 0, -1):
        j = back[i][j]
        path.append(j)
    path.reverse()
    return path, score


def find_split(pages, chapters):
    """Locate the ʿAmudei→Maskiyot boundary: the page after which the best-match
    chapter index falls back hardest."""
    best_ch = [max(range(len(chapters)), key=lambda j: containment(pg, chapters[j][1]))
               for _, pg in pages]
    drops = [(best_ch[i] - best_ch[i + 1], i + 1) for i in range(len(best_ch) - 1)]
    drop, idx = max(drops) if drops else (0, len(pages))
    return idx if drop > len(chapters) // 4 else len(pages)


def run(ocr_path, corpus_path, out_path):
    pages = load_pages(ocr_path)
    chapters = load_chapters(corpus_path)
    print(f"pages={len(pages)}  guide units={len(chapters)}", file=sys.stderr)

    split = find_split(pages, chapters)
    print(f"ʿAmudei/Maskiyot split after scan page index {split}"
          f" (scan p.{pages[split-1][0] if split<=len(pages) else '?'})", file=sys.stderr)

    result = {}
    for label, chunk, offset in (("amudei", pages[:split], 0),
                                 ("maskiyot", pages[split:], split)):
        if not chunk:
            continue
        path, score = monotonic_align(chunk, chapters)
        for i, j in enumerate(path):
            pno = chunk[i][0]
            result[str(pno)] = {"work": label, "unit": chapters[j][0],
                                "score": round(score[i][j], 3)}
    json.dump(result, open(out_path, "w", encoding="utf-8"),
              ensure_ascii=False, indent=1)

    # coverage report
    by_unit = defaultdict(list)
    for p, r in result.items():
        by_unit[(r["work"], r["unit"])].append(int(p))
    mean = sum(r["score"] for r in result.values()) / max(1, len(result))
    print(f"aligned {len(result)} pages onto {len(by_unit)} Guide units; "
          f"mean containment {mean:.3f}", file=sys.stderr)
    return result


if __name__ == "__main__":
    base = os.path.join(os.path.dirname(__file__), "..")
    run(sys.argv[1] if len(sys.argv) > 1 else f"{base}/out/AmudeiKesef_hebrewbooks_OCR_raw.txt",
        f"{base}/data/corpus.json",
        f"{base}/data/alignment.json")
