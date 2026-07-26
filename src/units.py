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

The front and part-preface matter
---------------------------------
The template covers the 178 chapters. The volume also opens each of its three
parts with matter no chapter template can catch: Kaspi's own preface, his
commentary on the dedication letter and on the Guide's introduction, and — at
Parts II and III — his commentary on the part-prefaces (the twenty-five
propositions; the six-fold plan of Part III, with a Maskiyot pass of its own).
The dynamic program, forced to start at chapter 1 of each part, used to shove
that matter into the nearest chapter: the whole introduction commentary was
printed as "chapter I:1" (a unit the verifier had flagged ``disagree``, rank
106, and nobody read the flag), and the propositions hung off the tail of
I:76. ``prefaces`` recovers it instead, from two signals neither the numeral
nor the opening-lemma test uses: fixed incipits (``אמר יוסף אבן כספי``,
``התלמיד החשוב``) where the section opens by quoting its base text, and, where
one commentary flows into the next without a heading, the point at which
verbatim quotation of one Guide section stops and quotation of the next
begins — found by ``seam`` as the sentence break stranding the least
quotation on the wrong side.

Dependencies: none (Python standard library; ``quote`` is local).
"""
from __future__ import annotations

import json
import os
import re
import sys

import quote

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
# Part banners. What marks one is that it stands *alone on its line* — the
# compositor gives the head of a Part a line to itself — and that is what
# separates it from the hundreds of in-text cross-references ("פ״ג מחלק שני",
# "בתחלת חלק שני"), which are always buried in a full measure of prose.
#
# An earlier version of this test asked instead for a closing point, and it
# worked on one reading and failed on the next: the 1848 period after "חלק שני"
# comes back from the publisher's layer as "•" and from Tesseract as a stray
# ‏י‎, and no arbitration between two readings will produce a character that
# neither of them saw. Standing alone is a fact about the page rather than
# about the engine that read it, and it survives any reading.
# The word חלק cannot be spelled out either: at the head of Part III the
# scanner read ‏חלה‎, the qof's descender broken off. Allow the letters this
# face actually loses it to, and let the ordinal and the short line do the
# identifying — a line reading "something-like-חלק שלישי" and nothing else is
# a banner whatever happened to the third letter.
QOF = "[קהרדךןת]"
PART_RE = re.compile(r"(?:^|[|\n])[\s|/\\.,'\"־-]{0,8}(?:עמודי\s+כסף\s+)?"
                     r"(?<![א-ת])ח[לג]" + QOF
                     + r"\s+(ראשון|שני|שלישי)[^\n]{0,12}$", re.M)
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

def template(moreh: dict) -> list[dict]:
    """The 178 Guide chapters in order, each with its numeral and opening grams."""
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


def part_anchors(text: str) -> dict[int, tuple[int, int]]:
    """Start and end of the banner opening each Part of the Guide.

    Anchors must themselves run in order, so Part p is taken as the first
    banner after Part p-1's. Both offsets are kept: the start bounds the
    chapters of the previous part, and the end is where the part's own front
    matter — which the chapter template cannot see — begins.
    """
    seen, floor = {}, 0
    for p in (1, 2, 3):
        for m in PART_RE.finditer(text, floor):
            if PART_NO[m.group(1)] == p:
                seen[p] = (m.start(), m.end())
                floor = m.start()
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
# The front and part-preface matter
# --------------------------------------------------------------------------

# Sentence breaks as this OCR renders them: the point, the two bullets the
# 1848 period comes back as, the semicolon. Line breaks are not breaks — the
# scan's lines end mid-sentence, and a seam that may fall at any newline will
# cut a quotation in half the first time the evidence goes quiet around one.
BREAK = re.compile(r"[.•;♦]\s+")


def spans_of(text: str, lo: int, hi: int, gtext: str) -> list[tuple[int, int]]:
    """Verbatim quotations of *gtext* inside text[lo:hi], in absolute offsets."""
    if not gtext:
        return []
    cs, _ = quote.quotations(text[lo:hi], gtext)
    return [(s + lo, e + lo) for s, e in cs]


NEAR = 60        # a quotation contests its neighbourhood, not just its inches


def seam(text: str, lo: int, hi: int, atext: str, btext: str,
         marks: tuple[int, ...] = ()) -> int:
    """Where commentary on A ends and commentary on B begins, within [lo, hi).

    Kaspi signals the change of base text with nothing but a change of what he
    is quoting, so that is what is measured: every verbatim quotation of A and
    of B in the stretch is laid down, and the cut is the sentence break that
    strands the least quotation on the wrong side.

    The spans cannot be taken raw, because the two texts quote each other —
    the proofs of II:1 restate the propositions they rest on, so a comment on
    proposition six can match II:1's restatement a letter longer than the
    proposition itself. A span is therefore discounted when the rival text's
    quotations within NEAR characters of it outweigh its own length: whose
    ground a quotation stands on is decided by the neighbourhood, which does
    not shift with one letter of OCR, rather than by the span's own inches,
    which do. Falls back to *hi* when B is never quoted: no evidence, no seam.
    Between the last quotation of A and the first of B the cost is flat — a
    corridor the evidence says nothing about — and inside such a corridor a
    printed chapter heading, where one stands, is the compositor saying where
    the seam is. *marks* carries those positions; a tied cut that lands on one
    wins the tie. With no mark in the corridor the earliest tied cut wins,
    which hands the unquoted bridge to B: the words that introduce a section
    belong to it.
    """
    A = spans_of(text, lo, hi, atext)
    B = spans_of(text, lo, hi, btext)

    def mass(spans, s, e):
        return sum(min(e, y) - max(s, x) for x, y in spans if x < e and s < y)

    Bx = [(s, e) for s, e in B if mass(A, s - NEAR, e + NEAR) < e - s]
    Ax = [(s, e) for s, e in A if mass(B, s - NEAR, e + NEAR) <= e - s]
    if not Bx:
        return hi
    cuts = [m.end() for m in BREAK.finditer(text, lo, hi)] or [hi]
    return min(cuts, key=lambda c: (
        sum(min(e, c) - s for s, e in Bx if s < c)
        + sum(e - max(s, c) for s, e in Ax if e > c),
        not any(c <= m <= c + 12 for m in marks),
        c))


def cut(text: str, key: str, part: int, lo: int, hi: int, pages,
        gtext: str) -> dict:
    """One preface unit, shaped like every other unit.

    The Maskiyot split is accepted only on evidence: the label ``משכיות כסף``
    also occurs mid-prose as a cross-reference — Kaspi names his own book in
    his own preface — and a run-in label is only a label if the text after it
    still quotes the same base section. Where it does not, the chunk stands
    whole. ``via`` says ``front`` and ``score`` is null: these units are not
    template matches and must not dress as ones.
    """
    parts = split_commentaries(text[lo:hi])
    if parts["maskiyot"] and not quote.quotations(parts["maskiyot"], gtext)[0]:
        parts = {"amudei": tidy(text[lo:hi]), "maskiyot": ""}
    return {"unit": key, "part": part, "chapter": 0, "at": lo,
            "page": page_of(lo, pages), "token": "", "via": "front",
            "score": None, **parts}


def prefaces(text: str, pages, moreh: dict, tmpl, cands, chain, anchors):
    """The nine-tenths of the volume's front matter the chapter match drops.

    Returns (front units, trimmed chain, per-entry start overrides,
    per-entry end overrides). Part I: the block before the first trustworthy
    chapter entry is cut at two fixed incipits — Kaspi's own preface, then his
    commentary on the dedication letter — then at the lemma that opens his
    commentary on the Guide's introduction, then at the measured seam where
    quotation moves from the introduction to its closing section on the causes
    of contradiction. Leading chain entries that fall inside the evidence of
    that block are dropped, not kept out of politeness: the old first entry
    was "chapter I:1" scored 0.85 against an ACCEPT of 0.80, made of the
    introduction commentary, and the print simply has no I:1 commentary — a
    fact the edition now states instead of papering over.

    Parts II and III: the stretch from the part banner to the part's first
    chapter entry is the part-preface commentary; where quotation of the
    preface demonstrably spills past that entry's matched position (II:1's
    candidate landed on the preface's closing formula), the entry's start is
    pushed to the measured seam, and the previous part's last unit is ended at
    the banner rather than left to swallow the preface.
    """
    gt = {k: "\n".join(WS.sub(" ", s).strip() for s in moreh.get(k) or [])
          for k in ("letter:0:0", "pref:0:0", "intro:1:0",
                    "intro:2:0", "intro:3:0", "ch:2:1", "ch:3:1")}
    front, starts, ends = [], {}, {}

    # -- Part I ------------------------------------------------------------
    guard = cands[chain[min(3, len(chain) - 1)][0]]["pos"]
    kaspi_at = text.index("אמר יוסף אבן כספי")
    letter_at = text.index("התלמיד החשוב", kaspi_at, guard)
    mark = text.index("ענינו הראשון", letter_at, guard)
    pref_at = text.rindex("המאמר הזה", letter_at, mark)
    intro_at = seam(text, pref_at, guard, gt["pref:0:0"], gt["intro:1:0"])
    evid = max((e for _, e in spans_of(text, intro_at, guard, gt["intro:1:0"])),
               default=intro_at)
    k0 = next(k for k, (ci, _, _) in enumerate(chain)
              if cands[ci]["pos"] >= evid)
    for ci, ti, _ in chain[:k0]:
        print(f"  dropped false {tmpl[ti]['unit']} at page {cands[ci]['page']}"
              " — inside the front matter", file=sys.stderr)
    chain = chain[k0:]
    body0 = cands[chain[0][0]]["pos"]
    for key, lo, hi in (("kaspi:0:0", kaspi_at, letter_at),
                        ("letter:0:0", letter_at, pref_at),
                        ("pref:0:0", pref_at, intro_at),
                        ("intro:1:0", intro_at, body0)):
        front.append(cut(text, key, 0 if key == "kaspi:0:0" else
                         int(key.split(":")[1]) or 0, lo, hi, pages,
                         gt.get(key, "")))

    # -- Parts II and III --------------------------------------------------
    for p in (2, 3):
        if p not in anchors:
            continue
        first = next((k for k, (ci, ti, _) in enumerate(chain)
                      if tmpl[ti]["part"] == p), None)
        if first is None:
            continue
        a0, a1 = anchors[p]
        limit = (cands[chain[first + 1][0]]["pos"]
                 if first + 1 < len(chain) else len(text))
        heads = tuple(m.start()
                      for m in HEAD_RE.finditer(text, a1, limit))
        cutat = seam(text, a1, limit, gt[f"intro:{p}:0"], gt[f"ch:{p}:1"],
                     heads)
        entry = cands[chain[first][0]]
        if cutat >= limit:              # no seam evidence: trust the entry
            cutat = entry["pos"]
        elif cutat > entry["pos"]:      # preface spills past the matched head
            m = HEAD_RE.search(text, cutat, min(cutat + 40, len(text)))
            starts[first] = m.end() if m else cutat
        else:
            cutat = entry["pos"]
        if first:
            ends[first - 1] = a0
        front.append(cut(text, f"intro:{p}:0", p, a1, cutat, pages,
                         gt[f"intro:{p}:0"]))

    return front, chain, starts, ends


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
    moreh = json.load(open(corpus_path, encoding="utf-8"))["moreh"]
    text, pages = load_scan(ocr_path, BODY)
    tmpl = template(moreh)
    cands = candidates(text, pages)
    anchors = part_anchors(text)
    chain = align(cands, tmpl, {p: s for p, (s, _) in anchors.items()})
    front, chain, starts, ends = prefaces(text, pages, moreh, tmpl,
                                          cands, chain, anchors)

    units = list(front)
    for k, (ci, ti, sc) in enumerate(chain):
        start = starts.get(k, cands[ci]["body"])
        end = ends.get(k, starts.get(k + 1,
                       cands[chain[k + 1][0]]["pos"] if k + 1 < len(chain)
                       else len(text)))
        t = tmpl[ti]
        u = {"unit": t["unit"], "part": t["part"], "chapter": t["chapter"],
             "at": start, "page": cands[ci]["page"], "token": cands[ci]["tok"],
             "via": "heading" if cands[ci]["head"] else "lemma",
             "score": round(sc, 3)}
        u.update(split_commentaries(text[start:end]))
        units.append(u)
    units.sort(key=lambda u: u["at"])           # reading order, as the scan runs
    for u in units:
        del u["at"]

    covered = {u["unit"] for u in units if u["via"] != "front"}
    return {
        "source": os.path.basename(ocr_path),
        "body_pages": list(BODY),
        "candidates": len(cands),
        "matched": len(covered),
        "front": len(front),
        "template": len(tmpl),
        "coverage": round(len(covered) / len(tmpl), 3),
        "part_anchors": {str(k): page_of(v[0], pages)
                         for k, v in anchors.items()},
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
          f"/{res['template']}  coverage={res['coverage']:.0%}"
          f"  front={res['front']}", file=sys.stderr)
    print(f"part banners at scan pages {res['part_anchors']}", file=sys.stderr)
    by_part: dict[int, list[int]] = {}
    with_mask = 0
    for u in res["units"]:
        if u["via"] != "front":
            by_part.setdefault(u["part"], []).append(u["chapter"])
        with_mask += bool(u["maskiyot"])
    for p, ch in sorted(by_part.items()):
        print(f"  Part {p}: {len(ch):>3}/{PART_LEN[p]} chapters "
              f"({min(ch)}–{max(ch)})", file=sys.stderr)
    print(f"  units carrying Maskiyot Kesef: {with_mask}", file=sys.stderr)
    for u in res["units"]:
        if u["via"] == "front":
            print(f"  front: {u['unit']:11} page {u['page']:>3}  "
                  f"amudei {len(u['amudei']):>5}  maskiyot {len(u['maskiyot'])}",
                  file=sys.stderr)
