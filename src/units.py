#!/usr/bin/env python3
"""Recover the unit structure of the 1848 Werbluner volume by *template match*.

Why not heading discovery
-------------------------
The 1848 setting opens each unit as a run-in heading — chapter number, lemma,
then Kaspi's comment, all in one paragraph:

    פרק כב.  בא.  והיא גם כן מונחת להכנס …

A regex for "פרק + numeral" therefore yields 512 hits, most of them ordinary
prose ("בזה הפרק", "פרק שעבר"), and the true headings are damaged by OCR
(``פרק חי`` for ה, ``פרק ן.`` for ו, ``פרק 2`` for ז, ``פרק י"ךף.`` for י"ד).
Discovery — find the headings, then read off their numbers — loses both ways.

What this module does instead
-----------------------------
We already know the answer sheet.  The Guide has exactly 76 + 48 + 54 chapters
and we hold Ibn Tibbon's text of every one of them.  So we do not *discover*
structure; we *match* the scan against a template of 178 known units, scoring
each candidate heading on two independent signals:

  numeral  weighted edit distance to the canonical Hebrew numeral, with the
           substitution cost reduced for the pairs this typeface + Tesseract
           actually confuse (ד/ר/ך, ב/כ, ה/ח/ת, ג/נ, ו/י/ן …);

  lemma    Kaspi's run-in lemma is a verbatim quotation of the Guide chapter's
           opening words, so 3-gram containment of the text right after the
           heading against Ibn Tibbon's chapter is high for the true chapter
           and near baseline for every other.

The two signals fail independently: OCR damage to the numeral does not touch
the lemma, and a chapter whose opening Kaspi paraphrases still carries its
number.  A monotonic dynamic program then picks the assignment maximising
total score subject to the constraints that both the scan position and the
chapter index increase — so an ambiguous heading is pinned by its neighbours.

Structural finding
------------------
Werbluner does not print the two commentaries in sequence.  For each Guide
chapter he prints ʿAmudei Kesef, then a run-in ``משכיות כסף:`` label, then
Maskiyot Kesef on the same chapter.  Each recovered unit is split on that
label, so the edition can lay the two commentaries out as the book intends.

Dependencies: none (Python standard library).
"""
from __future__ import annotations

import json
import os
import re
import sys

# --------------------------------------------------------------------------
# Hebrew numerals
# --------------------------------------------------------------------------

ONES = " אבגדהוזחט"
TENS = " יכלמנסעפצ"


def numeral(n: int) -> str:
    """Canonical Hebrew numeral, letters only (15/16 written טו/טז)."""
    if n == 15:
        return "טו"
    if n == 16:
        return "טז"
    t, o = divmod(n, 10)
    return (TENS[t] if t else "") + (ONES[o] if o else "")


# Substitution pairs Tesseract actually produces on this face, with their cost.
# Everything else costs a full 1.0.
_CHEAP = {
    0.10: [("כ", "ך"), ("מ", "ם"), ("נ", "ן"), ("פ", "ף"), ("צ", "ץ")],
    0.35: [("ד", "ר"), ("ד", "ך"), ("ר", "ך"), ("ב", "כ"), ("ב", "ם"),
           ("כ", "ם"), ("ה", "ח"), ("ח", "ת"), ("ה", "ת"), ("ה", "ן"),
           ("ג", "נ"), ("ג", "ז"), ("ו", "י"), ("ו", "ן"), ("ו", "ז"),
           ("י", "ן"), ("ט", "ס"), ("ט", "ם"), ("ס", "ם"), ("ע", "צ"),
           ("ל", "ג"), ("ש", "ם"), ("ם", "ס")],
}
SUB = {}
for cost, pairs in _CHEAP.items():
    for a, b in pairs:
        SUB[(a, b)] = SUB[(b, a)] = cost

STRIP = re.compile(r"[^א-ת]")


def sub_cost(a: str, b: str) -> float:
    return 0.0 if a == b else SUB.get((a, b), 1.0)


def numeral_sim(observed: str, target: str) -> float:
    """1.0 = exact; 0.0 = nothing in common. Weighted Levenshtein, normalised."""
    a, b = STRIP.sub("", observed), target
    if not a or not b:
        return 0.0
    prev = [float(j) for j in range(len(b) + 1)]
    for i, ca in enumerate(a, 1):
        cur = [float(i)]
        for j, cb in enumerate(b, 1):
            cur.append(min(prev[j] + 1.0,             # delete
                           cur[j - 1] + 1.0,          # insert
                           prev[j - 1] + sub_cost(ca, cb)))
        prev = cur
    return max(0.0, 1.0 - prev[-1] / max(len(a), len(b)))


# --------------------------------------------------------------------------
# Lemma signal
# --------------------------------------------------------------------------

FINALS = str.maketrans("ךםןףץ", "כמנפצ")
NONLETTER = re.compile(r"[^א-ת]")
G = 3


def norm(s: str) -> str:
    return NONLETTER.sub("", s.translate(FINALS))


def grams(s: str, n: int = G) -> set[str]:
    return {s[i:i + n] for i in range(len(s) - n + 1)}


def containment(small: set[str], big: set[str]) -> float:
    return len(small & big) / len(small) if small else 0.0


# --------------------------------------------------------------------------
# Scan
# --------------------------------------------------------------------------

PAGE_RE = re.compile(r"===== PDF3 page (\d+) =====")
# A heading candidate: "פרק" (or the four spellings OCR gives it) not glued to
# a preceding letter — that excludes the far commoner prefixed forms הפרק/בפרק
# — followed by a short token that ought to be the numeral.
HEAD_RE = re.compile(r"(?<![א-ת])פ[רדחב][קסה]\s+(\S{1,7})(?=\s)")
# Was the match at the start of a line or OCR column? Genuine headings are.
LINE_START = re.compile(r"[|\n][\s|.,:;/\\'\"-]*$")
# Werbluner's run-in label opening the second commentary.
MASKIYOT_RE = re.compile(r"מש[כב]יו?ת\s*[כב]סף\s*[:;.,'\"]?")
# Part banners. Werbluner sets these as their own line, closed by punctuation
# ("| חלק שני. |"), which distinguishes them from the hundreds of in-text
# cross-references ("פ״ג מחלק שני", "בתחלת חלק שני").
PART_RE = re.compile(r"(?:^|[|\n])[\s|ו/\\.,'\"-]{0,8}חלק\s+(ראשון|שני|שלישי)\s*[.:;,]")
PART_NO = {"ראשון": 1, "שני": 2, "שלישי": 3}

PART_LEN = {1: 76, 2: 48, 3: 54}

# The volume, established by reading the scan: p.7 errata; pp.8–142 the two
# commentaries interleaved; pp.143–149 Werbluner's addenda from MS Munich
# ("אמר המגיה: בסוף ספר עמודי כסף כ״י מינכען…", printed folio 146) with his own
# bracketed chapter headings, closing with Kaspi's בקשה; pp.150–170 the
# editor's German/Latin introduction, bound at the front of an RTL volume and
# so scanned last. Only the first range is a running commentary on the Guide.
BODY = (8, 142)
ADDENDA = (143, 149)


def load_scan(path: str, span=None) -> tuple[str, list[tuple[int, int, int]]]:
    raw = open(path, encoding="utf-8").read()
    segs = PAGE_RE.split(raw)
    pages, buf, off = [], [], 0
    for i in range(1, len(segs) - 1, 2):
        n, body = int(segs[i]), segs[i + 1]
        if span and not (span[0] <= n <= span[1]):
            continue
        pages.append((n, off, off + len(body)))
        buf.append(body)
        off += len(body)
    return "".join(buf), pages


def page_of(pos: int, pages) -> int | None:
    for n, a, b in pages:
        if a <= pos < b:
            return n
    return None


# --------------------------------------------------------------------------
# Template
# --------------------------------------------------------------------------

def template(corpus_path: str) -> list[dict]:
    """The 178 Guide chapters in order, each with its numeral and opening grams."""
    moreh = json.load(open(corpus_path, encoding="utf-8"))["moreh"]
    out = []
    for part in (1, 2, 3):
        for ch in range(1, PART_LEN[part] + 1):
            body = moreh.get(f"ch:{part}:{ch}")
            if not body:
                continue
            opening = norm(" ".join(body))[:260]
            out.append({"part": part, "chapter": ch, "unit": f"ch:{part}:{ch}",
                        "num": numeral(ch), "open": grams(opening)})
    return out


# --------------------------------------------------------------------------
# Candidates and scoring
# --------------------------------------------------------------------------

WINDOW = 90          # letters of scan text after a candidate, used as the lemma
STRIDE = 110          # spacing of the blind windows that back up the headings
W_NUM, W_LEM, W_HEAD, W_INIT = 1.0, 1.6, 0.30, 0.25
ACCEPT = 0.80        # minimum combined score for a match to be believed


def candidates(text: str, pages) -> list[dict]:
    """Every place a unit could begin.

    Two kinds, scored by the same function so the dynamic program can trade
    them off. Heading candidates carry a numeral; blind windows carry none and
    must earn their place on the lemma signal alone — which is what recovers
    the units whose ``פרק`` the scanner lost entirely.
    """
    out, seen = [], set()
    for m in HEAD_RE.finditer(text):
        out.append({"pos": m.start(), "body": m.end(), "tok": m.group(1),
                    "head": True,
                    "init": bool(LINE_START.search(text[max(0, m.start() - 10):m.start()]))})
        seen.add(m.start() // STRIDE)
    for p in range(0, len(text), STRIDE):
        if p // STRIDE in seen:
            continue
        out.append({"pos": p, "body": p, "tok": "", "head": False, "init": False})
    out.sort(key=lambda c: c["pos"])
    for c in out:
        c["tail"] = grams(norm(text[c["body"]:c["body"] + 4 * WINDOW])[:WINDOW])
        c["page"] = page_of(c["pos"], pages)
    return out


def part_anchors(text: str) -> dict[int, int]:
    """Character offset at which each Part of the Guide begins in the scan.

    Anchors must themselves run in order, so Part p is taken as the first
    banner after Part p-1's.
    """
    seen, floor = {}, 0
    for p in (1, 2, 3):
        for m in PART_RE.finditer(text, floor):
            if PART_NO[m.group(1)] == p:
                seen[p] = floor = m.start()
                break
    return seen


def score_matrix(cands, tmpl):
    rows = []
    for c in cands:
        bonus = (W_HEAD if c["head"] else 0.0) + (W_INIT if c["init"] else 0.0)
        rows.append([W_NUM * numeral_sim(c["tok"], t["num"])
                     + W_LEM * containment(c["tail"], t["open"]) + bonus
                     for t in tmpl])
    return rows


def align(cands, tmpl, anchors):
    """Monotonic DP: choose a strictly increasing chapter for a subset of the
    candidates, maximising total score. Candidates may be skipped (prose), and
    chapters may be skipped (heading lost to OCR)."""
    S = score_matrix(cands, tmpl)
    P, C = len(cands), len(tmpl)
    if not P or not C:
        return []

    # Hard windows from the Part banners: a candidate before Part p's banner
    # cannot belong to Part p.
    lo = [0] * P
    for i, c in enumerate(cands):
        for p in (3, 2):
            if p in anchors and c["pos"] >= anchors[p]:
                lo[i] = next(k for k, t in enumerate(tmpl) if t["part"] == p)
                break

    # M[i][j] = best chain using candidates < i and chapters < j, as a running
    # 2-D prefix maximum. This turns the naive O(P²C²) search into O(PC).
    NEG = float("-inf")
    back = {}
    Mv = [[0.0] * (C + 1) for _ in range(P + 1)]
    Ma = [[(-1, -1)] * (C + 1) for _ in range(P + 1)]

    for i in range(P):
        for j in range(C):
            v = NEG
            if j >= lo[i] and S[i][j] >= ACCEPT:
                v = Mv[i][j] + S[i][j]
                back[(i, j)] = Ma[i][j]
            # roll the prefix maximum forward
            cand = ((v, (i, j)) if v > NEG else (NEG, (-1, -1)))
            top, arg = Mv[i][j + 1], Ma[i][j + 1]
            if Mv[i + 1][j] > top:
                top, arg = Mv[i + 1][j], Ma[i + 1][j]
            if cand[0] > top:
                top, arg = cand
            Mv[i + 1][j + 1], Ma[i + 1][j + 1] = top, arg

    chain = []
    node = Ma[P][C]
    while node != (-1, -1):
        i, j = node
        chain.append((i, j, S[i][j]))
        node = back[(i, j)]
    chain.reverse()
    return chain


# --------------------------------------------------------------------------
# Split each unit into the two commentaries
# --------------------------------------------------------------------------

WS = re.compile(r"\s+")
JUNK = re.compile(r"[|\\/<>*+%~^={}\[\]_]+")


def tidy(s: str) -> str:
    return WS.sub(" ", JUNK.sub(" ", s)).strip(" .,:;-·")


def split_commentaries(chunk: str) -> dict:
    m = MASKIYOT_RE.search(chunk)
    if not m:
        return {"amudei": tidy(chunk), "maskiyot": ""}
    return {"amudei": tidy(chunk[:m.start()]), "maskiyot": tidy(chunk[m.end():])}


# --------------------------------------------------------------------------

ADD_HEAD = re.compile(r"[\[(]\s*(פ[רדחב][קסה]ים?[^\]\)\n]{0,18})[\])]")


def addenda(ocr_path: str) -> list[dict]:
    """Werbluner's supplement: chapters he found only in the Munich manuscript,
    which he heads with his own bracketed rubrics ([פרק ו'], [פרקים משני])."""
    text, pages = load_scan(ocr_path, ADDENDA)
    marks = [(m.start(), m.end(), m.group(1).strip()) for m in ADD_HEAD.finditer(text)]
    out = []
    for k, (s, e, label) in enumerate(marks):
        end = marks[k + 1][0] if k + 1 < len(marks) else len(text)
        out.append({"label": label, "page": page_of(s, pages), "text": tidy(text[e:end])})
    if not marks:
        out.append({"label": "", "page": pages[0][0] if pages else None,
                    "text": tidy(text)})
    return out


def build(ocr_path: str, corpus_path: str) -> dict:
    text, pages = load_scan(ocr_path, BODY)
    tmpl = template(corpus_path)
    cands = candidates(text, pages)
    anchors = part_anchors(text)
    chain = align(cands, tmpl, anchors)

    units = []
    for k, (ci, ti, sc) in enumerate(chain):
        start = cands[ci]["body"]
        end = cands[chain[k + 1][0]]["pos"] if k + 1 < len(chain) else len(text)
        t = tmpl[ti]
        u = {"unit": t["unit"], "part": t["part"], "chapter": t["chapter"],
             "page": cands[ci]["page"], "token": cands[ci]["tok"],
             "via": "heading" if cands[ci]["head"] else "lemma",
             "score": round(sc, 3)}
        u.update(split_commentaries(text[start:end]))
        units.append(u)

    covered = {u["unit"] for u in units}
    return {
        "source": os.path.basename(ocr_path),
        "body_pages": list(BODY),
        "candidates": len(cands),
        "matched": len(units),
        "template": len(tmpl),
        "coverage": round(len(covered) / len(tmpl), 3),
        "part_anchors": {str(k): page_of(v, pages) for k, v in anchors.items()},
        "units": units,
        "addenda": addenda(ocr_path),
    }


if __name__ == "__main__":
    base = os.path.join(os.path.dirname(__file__), "..")
    res = build(sys.argv[1] if len(sys.argv) > 1
                else f"{base}/out/AmudeiKesef_hebrewbooks_OCR_raw.txt",
                f"{base}/data/corpus.json")
    dst = f"{base}/data/kaspi_units.json"
    json.dump(res, open(dst, "w", encoding="utf-8"), ensure_ascii=False, indent=1)
    print(f"candidates={res['candidates']}  matched={res['matched']}"
          f"/{res['template']}  coverage={res['coverage']:.0%}", file=sys.stderr)
    print(f"part banners at scan pages {res['part_anchors']}", file=sys.stderr)
    by_part: dict[int, list[int]] = {}
    with_mask = 0
    for u in res["units"]:
        by_part.setdefault(u["part"], []).append(u["chapter"])
        with_mask += bool(u["maskiyot"])
    for p, ch in sorted(by_part.items()):
        print(f"  Part {p}: {len(ch):>3}/{PART_LEN[p]} chapters "
              f"({min(ch)}–{max(ch)})", file=sys.stderr)
    print(f"  units carrying Maskiyot Kesef: {with_mask}", file=sys.stderr)
