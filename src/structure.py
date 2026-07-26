#!/usr/bin/env python3
"""Recover the chapter structure of the 1848 Werbluner volume from raw OCR.

The 1848 setting opens each unit as a run-in heading:

    פרק כב.  בא.  והיא גם כן מונחת להכנס ...
    └ chapter ┘ └ lemma ┘ └ Kaspi's comment ...

so the headings are *in* the text stream, not in a separate style OCR can see.
A naive regex for "פרק + numeral" yields 474 hits, nearly all of them ordinary
prose ("בזה הפרק", "פרק שעבר").

The discriminator is not typography but *arithmetic*: real headings form a
run 1, 2, 3, … that restarts at each Part of the Guide, and they appear in
reading order. So candidates are scored by a longest-increasing-run dynamic
program with an allowance for restarts, and everything off the winning run is
discarded as prose. Verified independently against the Guide's own text via
n-gram containment (src/align.py), which needs no headings at all.

Dependencies: none (Python standard library).
"""
from __future__ import annotations

import json
import os
import re
import sys

VALUES = {c: v for c, v in zip("אבגדהוזחטיכלמנסעפצק",
                               [1, 2, 3, 4, 5, 6, 7, 8, 9, 10, 20, 30, 40, 50,
                                60, 70, 80, 90, 100])}
VALUES.update({"ך": 20, "ם": 40, "ן": 50, "ף": 80, "ץ": 90})

# Chapter counts of the Guide (Ibn Tibbon / Sefaria): I 76, II 48, III 54.
PART_LEN = {1: 76, 2: 48, 3: 54}

# "פרק" (OCR also yields פדק/פרס) + numeral, then a separator, then the lemma.
CAND = re.compile(r"(?:^|[\n.;:•·׃])\s*פ[רד][קס]\s+([א-ת]{1,4})\s*[.,:•·׃]?\s+(\S{1,24})")
PAGE_RE = re.compile(r"===== PDF3 page (\d+) =====")


def gematria(s: str) -> int | None:
    if not s or any(c not in VALUES for c in s):
        return None
    v = sum(VALUES[c] for c in s)
    # reject non-canonical spellings (e.g. יה for 15, or descending order)
    vals = [VALUES[c] for c in s]
    if vals != sorted(vals, reverse=True):
        return None
    return v or None


def candidates(text: str) -> list[dict]:
    out = []
    for m in CAND.finditer(text):
        n = gematria(m.group(1))
        if n and 1 <= n <= 76:
            out.append({"pos": m.start(), "n": n, "lemma": m.group(2).strip(".,:•·"),
                        "raw": m.group(1)})
    return out


def best_run(cands: list[dict]) -> list[dict]:
    """Longest chain that is increasing, allowing restarts at Part boundaries.

    Chain state is (part, chapter). A step either advances the chapter within
    the current part or opens the next part at chapter 1-ish. Gaps are allowed
    (OCR drops headings) but penalised, so the DP prefers dense true runs.
    """
    if not cands:
        return []
    best = [1.0] * len(cands)
    back = [-1] * len(cands)
    part = [1] * len(cands)
    for i, c in enumerate(cands):
        for j in range(i):
            p = cands[j]
            gap = c["n"] - p["n"]
            if gap > 0:                      # same part, forward
                sc = best[j] + 1.0 / gap
                np_ = part[j]
            elif c["n"] <= 3 and p["n"] >= 20 and part[j] < 3:
                sc = best[j] + 0.5           # restart: next Part of the Guide
                np_ = part[j] + 1
            else:
                continue
            if c["n"] > PART_LEN.get(np_, 76):
                continue
            if sc > best[i]:
                best[i], back[i], part[i] = sc, j, np_
    i = max(range(len(cands)), key=lambda k: best[k])
    chain = []
    while i >= 0:
        c = dict(cands[i]); c["part"] = part[i]
        chain.append(c)
        i = back[i]
    chain.reverse()
    return chain


def parse(ocr_path: str) -> dict:
    raw = open(ocr_path, encoding="utf-8").read()
    parts = PAGE_RE.split(raw)
    pages, offset, joined = [], 0, []
    for i in range(1, len(parts) - 1, 2):
        body = parts[i + 1]
        pages.append({"page": int(parts[i]), "start": offset, "end": offset + len(body)})
        joined.append(body)
        offset += len(body)
    text = "".join(joined)

    cands = candidates(text)
    chain = best_run(cands)

    def page_of(pos):
        for p in pages:
            if p["start"] <= pos < p["end"]:
                return p["page"]
        return None

    units = []
    for k, c in enumerate(chain):
        end = chain[k + 1]["pos"] if k + 1 < len(chain) else len(text)
        units.append({
            "unit": f"ch:{c['part']}:{c['n']}",
            "part": c["part"], "chapter": c["n"], "lemma": c["lemma"],
            "page": page_of(c["pos"]),
            "text": re.sub(r"\s+", " ", text[c["pos"]:end]).strip(),
        })
    return {"candidates": len(cands), "accepted": len(chain), "units": units,
            "chars": len(text)}


if __name__ == "__main__":
    base = os.path.join(os.path.dirname(__file__), "..")
    res = parse(sys.argv[1] if len(sys.argv) > 1
                else f"{base}/out/AmudeiKesef_hebrewbooks_OCR_raw.txt")
    dst = f"{base}/data/kaspi_structure.json"
    json.dump(res, open(dst, "w", encoding="utf-8"), ensure_ascii=False, indent=1)
    print(f"candidates={res['candidates']}  accepted={res['accepted']}", file=sys.stderr)
    seen = {}
    for u in res["units"]:
        seen.setdefault(u["part"], []).append(u["chapter"])
    for p, ch in sorted(seen.items()):
        print(f"  Part {p}: {len(ch)} chapters, {min(ch)}–{max(ch)}", file=sys.stderr)
    for u in res["units"][:8] + res["units"][-4:]:
        print(f"  {u['unit']:9} scan p.{u['page']:>4}  lemma={u['lemma']!r:18} "
              f"{len(u['text']):>6} chars", file=sys.stderr)
