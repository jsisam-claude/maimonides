#!/usr/bin/env python3
"""Flag the words in the OCR that no Hebrew text has ever attested.

The 1848 scan is good but not clean, and the damage is not evenly spread: a
tight paragraph may be flawless while the next carries a line of nonsense from
a smudged forme. A reader of a critical edition is entitled to know which is
which, so this module scores it.

The test is lexical, and the lexicon costs nothing to build: the edition
already holds ~3.5 M characters of clean Hebrew — Ibn Tibbon plus the five
classical commentators — in the same register, century and orthography as
Kaspi. A word-form attested there is almost certainly read correctly; one that
is not is either OCR damage or a genuinely rare form, and both deserve a mark.

Two refinements keep the false-alarm rate down:

* Hebrew glues its particles on, so ``ובמחשבתו`` may be absent while
  ``מחשבתו`` is common. Up to two leading letters drawn from וה־בכלמש are
  stripped before the lookup fails.
* Final forms are folded, since a final kaf misread as a medial one is a
  typographic, not a lexical, error.

Anything carrying a Latin letter or a digit is damage by definition — the
volume is set entirely in Hebrew type.

How specific is the flag?
-------------------------
``calibrate()`` answers it by holding each clean witness out of its own
lexicon and flagging it as though it were OCR. Clean fourteenth-century
philosophical Hebrew, unseen by the lexicon that judges it, scores:

    Ibn Tibbon 3.8 %   Efodi 1.2 %   Shem Tov 1.1 %
    Crescas 2.1 %      Narboni 2.4 % Abarbanel 2.3 %

against 24.3 % for the Kaspi OCR. So roughly two points of the flag rate are
the ordinary novelty of a Hebrew vocabulary and twenty-two are scanning
damage: a word underlined here is about ten times more likely to be a
misreading than a rare form.

Dependencies: none (Python standard library).
"""
from __future__ import annotations

import re

FINALS = str.maketrans("ךםןףץ", "כמנפצ")
NIQQUD = re.compile(r"[֑-ׇ]")
LETTERS = re.compile(r"[א-ת]+")
FOREIGN = re.compile(r"[A-Za-z0-9]")
TOKEN = re.compile(r"\S+")
PREFIX = set("והבכלמש")

# Hebrew marks an abbreviation by putting gershayim before its last letter —
# ‏ר״ל‎, ‏אע״פ‎, ‏הרמב״ם‎ — and the type-case, the scan and the modern editor's
# keyboard between them offer six glyphs for the two marks. `LETTERS` is a run
# of letters and stops at any of them, which is right for reducing a word to
# its bare letters and wrong for counting words: it makes ‏ר״ל‎ two tokens, and
# two thousand of the volume's sixty are abbreviations. Every stream that
# compares this edition to another was therefore counting an abbreviation twice
# on one side, drifting the alignment by a word at each of them — which is how
# a real misreading of ‏ר״ל‎ as ‏אל‎ came to be filed as a difference of edition.
#
# The mark is only read as gershayim where it stands in gershayim's one legal
# position — before the final letter, and nothing after. That proviso is not
# tidiness: Ibn Tibbon's text on Sefaria uses the same ASCII glyph as an opening
# quotation mark with the article glued to it, ‏ה"חכמים‎, and a pattern that
# merged on the mark alone swallowed eighty-two of those into one non-word and
# put a full point on the floor measurement. Position tells the two apart with
# no list of anything.
GERESH = "׳״'\"’”"
MARKS = str.maketrans({"'": "׳", "’": "׳", '"': "״", "”": "״"})
WORD = re.compile(rf"[א-ת]+(?:[{re.escape(GERESH)}][א-ת](?![א-ת]))?")
INNER = re.compile(r"(?<=[א-ת])׳(?=[א-ת])")     # a geresh here is a misread ״
ABBREV = re.compile(r"^[א-ת]+״[א-ת]$")


def fold(word: str) -> str:
    """The comparable form: finals folded, and one glyph per mark.

    A single geresh between two letters is not a spelling — geresh ends a word,
    gershayim divides one — so ‏ר׳ל‎ is ‏ר״ל‎ with a stroke lost, and folding it
    that way is the same kind of statement as folding a final kaf: a rule of the
    orthography, not a guess about the ink.
    """
    return INNER.sub("״", word.translate(FINALS).translate(MARKS))


MAQAF = "־-‐‑‒–—"        # a token joined by one of these is two words on purpose


def pieces(text: str) -> list[str] | None:
    """The word's letters, if something is wedged between them that cannot be.

    ‏הא.דם‎ is not a spelling of ‏האדם‎ and no reading of any scan makes it one:
    Hebrew puts nothing inside a word but letters and, in an abbreviation,
    gershayim before the last letter. So the test needs no lexicon and no vote —
    re-read the token with `WORD`, which encodes exactly that rule, and if it
    comes back as more than one word while the token itself holds no space,
    whatever divided them is damage.

    Returns the pieces, or None if the token is sound. A token holding a maqaf
    is sound by definition: there the division is the compositor's.
    """
    if any(c in text for c in MAQAF):
        return None
    part = WORD.findall(NIQQUD.sub("", text))
    return part if len(part) > 1 else None


def lexicon(*texts) -> set[str]:
    """Every word-form attested in the clean texts, folded to bare letters."""
    lex: set[str] = set()
    for t in texts:
        lex.update(fold(w) for w in WORD.findall(NIQQUD.sub("", t)))
    return lex


def attested(word: str, lex: set[str]) -> bool:
    """Has any clean Hebrew text ever written this form?

    An abbreviation shaped the way Hebrew shapes abbreviations is taken as
    written, whether or not the corpus happens to contain it. The corpus does
    contain sixteen hundred of them and still misses twenty-eight per cent of
    the volume's — ‏בכ״י‎, ‏פי״ג‎, ‏פמ״ה‎, Werbluner citing a manuscript and a
    chapter — because abbreviation is productive: any phrase can be abbreviated,
    so no list of the ones that have been is evidence that the rest are damage.
    What is evidence is the shape, and the shape is a rule — gershayim before
    the final letter — which ‏כס״כו‎, a genuinely broken token, does not meet.
    """
    if word in lex or ABBREV.match(word):
        return True
    for k in (1, 2):                       # strip agglutinated particles
        if len(word) > k + 1 and all(c in PREFIX for c in word[:k]) \
                and word[k:] in lex:
            return True
    return False


def suspects(text: str, lex: set[str]) -> tuple[list[tuple[int, int]], int, int]:
    """Spans of unattested tokens, plus (suspect count, token count)."""
    spans, bad, total = [], 0, 0
    for m in TOKEN.finditer(text):
        raw = m.group()
        if FOREIGN.search(raw):
            spans.append(m.span())
            bad += 1
            total += 1
            continue
        letters = WORD.findall(NIQQUD.sub("", raw))
        if not letters:
            continue
        total += 1
        if not all(attested(fold(w), lex) for w in letters):
            spans.append(m.span())
            bad += 1
    return spans, bad, total


def quality(text: str, lex: set[str]) -> float:
    """Share of tokens attested in the lexicon. 1.0 = nothing suspect."""
    _, bad, total = suspects(text, lex)
    return 1.0 - bad / total if total else 1.0


def calibrate(corpus_path: str) -> list[dict]:
    """Flag rate on clean text held out of its own lexicon. See the docstring."""
    import json

    corpus = json.load(open(corpus_path, encoding="utf-8"))
    flat = {w: " ".join(sum(d.values(), [])) for w, d in corpus.items()}
    rows = []
    for w in flat:
        lex = lexicon(*(t for o, t in flat.items() if o != w))
        _, bad, total = suspects(flat[w], lex)
        rows.append({"witness": w, "flagged": bad, "tokens": total,
                     "rate": round(bad / total, 4), "lexicon": len(lex)})
    return rows


if __name__ == "__main__":
    import os
    import sys

    base = os.path.join(os.path.dirname(os.path.abspath(__file__)), "..")
    print(f"{'held out':<12}{'flagged':>9}{'tokens':>10}{'rate':>8}{'lexicon':>10}",
          file=sys.stderr)
    for r in calibrate(f"{base}/data/corpus.json"):
        print(f"{r['witness']:<12}{r['flagged']:>9,}{r['tokens']:>10,}"
              f"{r['rate']:>7.1%}{r['lexicon']:>10,}", file=sys.stderr)
