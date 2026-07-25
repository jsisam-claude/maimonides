#!/usr/bin/env python3
"""Recover logical-order Hebrew from a PDF text layer whose fonts carry no
ToUnicode CMap.

The problem
-----------
`מורה נבוכים … דפי דוגמה.pdf` embeds two legacy Hebrew Type-1 fonts. Neither
declares a ToUnicode map, so poppler falls back to the font's built-in
encoding and emits the raw cp1255 bytes reinterpreted as a Latin script:

    font A  ->  bytes read back as latin-1     'äðä éðîî'
    font B  ->  bytes read back as mac_roman   '˜¯Ù ‡Ò'

Underneath, both are plain cp1255 (ISO-8859-8 Hebrew). Round-tripping the
mis-decode therefore restores the true text with stdlib codecs only:

    s.encode('latin-1' | 'mac_roman').decode('cp1255')

A second, independent defect: glyphs inside a run come back in *visual*
(display) order, so each word reads backwards. Word order is preserved.

Deciding the flip
-----------------
Rather than hardcode "always reverse", each line is scored both ways against a
lexicon. The lexicon is harvested from the *same document*: ~58k characters of
the PDF are set in modern fonts that do have ToUnicode and decode cleanly.
The document thus supplies its own ground truth, and the decoder needs no
word list, no model and no third-party package.

Dependencies: none (Python standard library).
"""
from __future__ import annotations

import re
import sys
import unicodedata
from collections import Counter

HEB = re.compile(r"[֐-׿]")
NIQQUD = re.compile(r"[֑-ׇ]")
# Characters each mis-decode can produce. Disjoint enough to identify the font.
MAC_ONLY = set("‡·„‰ˆ‰ÈÍÎÏÌÓÔÒÚÙÛ˘˙˜¯ÊËÁÂÌı‚–")
LAT_ONLY = set("àáâãäåæçèéêëìíîïðñòóôõö÷øùú")

CODECS = (("mac_roman", MAC_ONLY), ("latin-1", LAT_ONLY))


def is_mojibake(s: str) -> bool:
    return sum(1 for c in s if ord(c) > 127 and not HEB.match(c)) >= 3


def pick_codec(s: str) -> str | None:
    """Choose the mis-decode that explains this run's characters."""
    best, best_hits = None, 0
    for name, charset in CODECS:
        hits = sum(1 for c in s if c in charset)
        if hits > best_hits:
            best, best_hits = name, hits
    return best


def demojibake(s: str) -> str:
    codec = pick_codec(s)
    if not codec:
        return s
    try:
        return s.encode(codec, errors="strict").decode("cp1255")
    except (UnicodeEncodeError, UnicodeDecodeError):
        # Mixed run: convert character by character, leave the rest alone.
        out = []
        for c in s:
            try:
                out.append(c.encode(codec).decode("cp1255"))
            except (UnicodeEncodeError, UnicodeDecodeError):
                out.append(c)
        return "".join(out)


# --------------------------------------------------------------------------
# Lexicon harvested from the correctly-encoded part of the same document.
# --------------------------------------------------------------------------

def build_lexicon(clean_text: str) -> Counter:
    lex: Counter = Counter()
    for w in re.findall(r"[א-ת]{2,}", NIQQUD.sub("", clean_text)):
        lex[w] += 1
    return lex


def _score(words: list[str], lex: Counter) -> float:
    """Fraction of tokens present in the lexicon, weighted by length."""
    num = den = 0
    for w in words:
        if len(w) < 2:
            continue
        den += len(w)
        if w in lex:
            num += len(w)
    return num / den if den else 0.0


def orient(text: str, lex: Counter) -> str:
    """Return the reading (as-is / per-word flipped) that scores higher."""
    words = text.split()
    plain = [NIQQUD.sub("", w) for w in words]
    flipped = [w[::-1] for w in plain]
    if _score(flipped, lex) > _score(plain, lex):
        return " ".join(w[::-1] for w in words)
    return text


def decode_line(line: str, lex: Counter) -> str:
    return orient(demojibake(line), lex) if is_mojibake(line) else line


def decode_document(text: str) -> tuple[str, dict]:
    clean = "\n".join(l for l in text.split("\n") if not is_mojibake(l))
    lex = build_lexicon(clean)
    out, fixed = [], 0
    for line in text.split("\n"):
        if is_mojibake(line):
            out.append(decode_line(line, lex))
            fixed += 1
        else:
            out.append(line)
    return "\n".join(out), {"lexicon_types": len(lex), "lines_repaired": fixed}


if __name__ == "__main__":
    raw = open(sys.argv[1], encoding="utf-8").read()
    fixed, stats = decode_document(raw)
    dst = sys.argv[2] if len(sys.argv) > 2 else None
    (open(dst, "w", encoding="utf-8") if dst else sys.stdout).write(
        unicodedata.normalize("NFC", fixed)
    )
    print(f"{stats}", file=sys.stderr)
