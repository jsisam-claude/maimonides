#!/usr/bin/env python3
"""Normalise the Sefaria export into one flat, addressable corpus.

Sefaria ships each work as nested JSON whose shape varies per title
(`{"Part 1": {"Introduction": [...], "": [[chapter], ...]}}` and friends).
This module flattens every witness onto a single citation key so the Guide and
its commentaries can be laid out side by side:

    ("letter", 0, n)      the dedicatory epistle to R. Joseph b. Judah
    ("pref",   0, n)      the prefatory remarks / introduction
    ("intro",  p, n)      the introduction to Part p
    ("ch",     p, c)      Part p, chapter c

Output: data/corpus.json — {"moreh": {...}, "efodi": {...}, ...}
Dependencies: none (Python standard library).
"""
from __future__ import annotations

import json
import os
import re
import sys

DATA = os.path.join(os.path.dirname(__file__), "..", "data")

WITNESSES = {
    "moreh": "Moreh_Nevuchim__translated_by_Ibn_Tibon.json",
    "efodi": "efodi.json",
    "shemtov": "shem_tov.json",
    "crescas": "crescas.json",
    "narboni": "narboni.json",
    "abarbanel": "abarbanel.json",
}

# Section names Sefaria uses, mapped onto our three front-matter buckets.
FRONT = {
    "Letter to R Joseph son of Judah": "letter",
    "Prefatory Remarks": "pref",
    "Introduction": "pref",
    "Introduction of Ibn Tibon": "tibbon",
}

TAG = re.compile(r"<[^>]+>")
WS = re.compile(r"[ \t ]+")


def clean(s) -> str:
    if not isinstance(s, str):
        return ""
    return WS.sub(" ", TAG.sub("", s)).strip()


def _paras(node) -> list[str]:
    """Flatten an arbitrarily nested list of strings into clean paragraphs."""
    if isinstance(node, str):
        c = clean(node)
        return [c] if c else []
    if isinstance(node, list):
        out = []
        for x in node:
            out.extend(_paras(x))
        return out
    return []


def flatten(text) -> dict[str, list[str]]:
    """Return {citation_key: [paragraphs]} for one witness's `text` blob."""
    out: dict[str, list[str]] = {}

    def put(key, node):
        p = _paras(node)
        if p:
            out[key] = p

    for section, body in (text or {}).items():
        m = re.fullmatch(r"Part (\d+)(?: Introduction)?", section)
        if section in FRONT:
            put(f"{FRONT[section]}:0:0", body)
        elif m:
            part = int(m.group(1))
            if section.endswith("Introduction"):
                put(f"intro:{part}:0", body)
            elif isinstance(body, dict):
                for sub, node in body.items():
                    if sub in ("Introduction", "Foreword"):
                        put(f"intro:{part}:0", node)
                    else:  # the unnamed bucket holds the chapter array
                        for i, ch in enumerate(node, 1):
                            put(f"ch:{part}:{i}", ch)
            elif isinstance(body, list):
                for i, ch in enumerate(body, 1):
                    put(f"ch:{part}:{i}", ch)
        else:
            put(f"other:0:0", body)
    return out


def build() -> dict:
    corpus = {}
    for sigil, fname in WITNESSES.items():
        path = os.path.join(DATA, fname)
        if not os.path.exists(path):
            print(f"  skip {sigil}: missing {fname}", file=sys.stderr)
            continue
        blob = json.load(open(path, encoding="utf-8"))
        corpus[sigil] = flatten(blob.get("text"))
    return corpus


def stats(corpus: dict) -> None:
    for k, v in corpus.items():
        chars = sum(len(p) for ps in v.values() for p in ps)
        chapters = sum(1 for key in v if key.startswith("ch:"))
        print(f"  {k:10} keys={len(v):4}  chapters={chapters:4}  chars={chars:,}")


if __name__ == "__main__":
    c = build()
    stats(c)
    dst = os.path.join(DATA, "corpus.json")
    json.dump(c, open(dst, "w", encoding="utf-8"), ensure_ascii=False, separators=(",", ":"))
    print(f"wrote {dst}  ({os.path.getsize(dst):,} bytes)")
