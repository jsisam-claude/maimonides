#!/usr/bin/env python3
"""Independently test the unit assignment produced by src/units.py.

The matcher decided each unit from two narrow signals: the OCR'd chapter
numeral, and 3-gram containment over the 90 letters immediately after the
heading. This module re-decides every unit from a signal the matcher never
saw — the *whole* commentary text against the *whole* Guide chapter, on
4-grams — and reports how often the two agree. Agreement is evidence; it is
not proof, but two methods this different are unlikely to fail the same way.

Why plain containment is not enough
-----------------------------------
|unit ∩ chapter| / |unit| rewards long chapters: Guide I:73 shares more grams
with any Hebrew page than I:26 does simply because it contains more Hebrew.
Run naively it maps every page of the volume onto I:73, II:29 or III:49 — the
three longest chapters, which is exactly what a first attempt did.

Inverse document frequency alone does not cure it — it reweights the terms but
leaves the numerator growing with chapter size. Cosine similarity over
tf-idf-weighted gram vectors does, because the chapter's own norm sits in the
denominator. Measured on this corpus: raw containment ranks the true chapter
first for 4 % of units, cosine for 73 %.

Dependencies: none (Python standard library).
"""
from __future__ import annotations

import json
import math
import os
import re
import sys
from collections import Counter

N = 4
FINALS = str.maketrans("ךםןףץ", "כמנפצ")
NONLETTER = re.compile(r"[^א-ת]")


def norm(s: str) -> str:
    return NONLETTER.sub("", s.translate(FINALS))


def grams(s: str, n: int = N) -> set[str]:
    return {s[i:i + n] for i in range(len(s) - n + 1)}


def chapters(corpus_path: str):
    """Every Guide section a unit could be a commentary on.

    The front matter — letter, introduction, part prefaces — is in the pool
    with the chapters. It was once left out on the argument that only chapters
    are template-matched, and that is exactly how a unit made of introduction
    commentary got to wear the verdict "disagree, argmax I:73" instead of the
    verdict that would have named the mistake: its best match was a section
    the verifier was never shown.
    """
    moreh = json.load(open(corpus_path, encoding="utf-8"))["moreh"]
    keys = sorted(moreh,
                  key=lambda k: (int(k.split(":")[1]), int(k.split(":")[2]),
                                 k.split(":")[0]))
    return [(k, grams(norm(" ".join(moreh[k])))) for k in keys]


def idf(chs) -> dict[str, float]:
    df: Counter = Counter()
    for _, g in chs:
        df.update(g)
    total = len(chs)
    return {g: math.log(total / c) for g, c in df.items()}


def cosine(doc: set[str], ch: set[str], w: dict[str, float], ch_norm: float) -> float:
    """Cosine between two idf-weighted binary gram vectors."""
    num = sum(w.get(g, 0.0) ** 2 for g in doc & ch)
    dn = math.sqrt(sum(w.get(g, 0.0) ** 2 for g in doc)) * ch_norm
    return num / dn if dn else 0.0


def run(units_path: str, corpus_path: str, out_path: str) -> dict:
    res = json.load(open(units_path, encoding="utf-8"))
    chs = chapters(corpus_path)
    w = idf(chs)
    norms = [math.sqrt(sum(w[g] ** 2 for g in g_)) for _, g_ in chs]
    index = {k: i for i, (k, _) in enumerate(chs)}

    rows, agree, top3, scored = [], 0, 0, 0
    for u in res["units"]:
        if u["unit"] not in index:                # Kaspi's own preface: no
            continue                              # Guide text to check against
        text = norm(u["amudei"] + " " + u["maskiyot"])
        if len(text) < 300:                       # too short to vote on
            rows.append({"unit": u["unit"], "verdict": "short",
                         "chars": len(text)})
            continue
        g = grams(text)
        ranked = sorted(((cosine(g, c, w, norms[i]), k)
                         for i, (k, c) in enumerate(chs)), reverse=True)
        best, second = ranked[0], ranked[1]
        picked = next(s for s, k in ranked if k == u["unit"])
        rank = [k for _, k in ranked].index(u["unit"]) + 1
        scored += 1
        agree += rank == 1
        top3 += rank <= 3
        rows.append({"unit": u["unit"], "page": u["page"], "chars": len(text),
                     "rank": rank, "score": round(picked, 4),
                     "argmax": best[1], "argmax_score": round(best[0], 4),
                     "margin": round(best[0] - second[0], 4),
                     "verdict": "agree" if rank == 1 else
                                ("near" if rank <= 3 else "disagree"),
                     "distance": abs(index[best[1]] - index[u["unit"]])})

    summary = {"scored": scored, "agree": agree, "top3": top3,
               "agree_rate": round(agree / max(1, scored), 3),
               "top3_rate": round(top3 / max(1, scored), 3),
               "short": sum(1 for r in rows if r["verdict"] == "short")}
    json.dump({"summary": summary, "rows": rows}, open(out_path, "w", encoding="utf-8"),
              ensure_ascii=False, indent=1)
    return {"summary": summary, "rows": rows}


if __name__ == "__main__":
    base = os.path.join(os.path.dirname(__file__), "..")
    r = run(f"{base}/data/kaspi_units.json", f"{base}/data/corpus.json",
            f"{base}/data/verification.json")
    s = r["summary"]
    print(f"scored {s['scored']} units  (skipped {s['short']} under 300 letters)",
          file=sys.stderr)
    print(f"  independent method picks the same chapter : {s['agree']} "
          f"({s['agree_rate']:.0%})", file=sys.stderr)
    print(f"  within top 3                              : {s['top3']} "
          f"({s['top3_rate']:.0%})", file=sys.stderr)
    bad = [x for x in r["rows"] if x["verdict"] == "disagree"]
    print(f"  disagreements: {len(bad)}", file=sys.stderr)
    for x in sorted(bad, key=lambda x: -x["distance"])[:12]:
        print(f"    {x['unit']:9} p{x['page']:>4} {x['chars']:>6}ch  "
              f"rank={x['rank']:<3} argmax={x['argmax']:9} "
              f"(+{x['margin']:.3f})", file=sys.stderr)
