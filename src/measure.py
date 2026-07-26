#!/usr/bin/env python3
"""What each stage of the reading was worth, measured the same way every time.

An edition that claims to have improved its text owes the reader the number,
the method, and the floor beneath the number. This module produces all three.

*The number.* For every reading of the 1848 print, the share of word-forms that
no clean Hebrew text in the corpus attests. That is not an error rate — a rare
but correct word counts against it — but it is the only figure available
without a hand transcription to collate against, and it is applied identically
to every reading, so the differences between them are real even where the
absolute value is not.

*The method.* Two decisions matter, and both were mistakes at first.

The German and Latin matter — the title page, the subscriber list, Werbluner's
Fraktur introduction — is 18 of the 170 pages and scores 99-100 % unattested
against a Hebrew lexicon, because it is not Hebrew. Left in, it dominates the
aggregate and every stage looks equally bad. A page counts here only if it is
more than 60 % Hebrew.

Werbluner's notes are set in Rashi semi-cursive, which Tesseract's square-script
model cannot read and does not decline to read: it returns a substitution
cipher. Measuring Kaspi's commentary means measuring the zone above the rule
and nothing else.

*The floor.* Hold a commentator out of the lexicon and put his clean, born-
digital text through the same test. Nothing is wrong with that text, and it
still scores 1.1-3.8 % — that is what ordinary lexical novelty costs. A reading
at 3 % is at the measurement's floor and its remaining errors are invisible to
this instrument; only a human with the scan can go below it.

Dependencies: none (Python standard library).
"""
from __future__ import annotations

import json
import os
import re
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import ocrqual                                   # noqa: E402

HEB = re.compile(r"[א-ת]")
PAGE_RE = re.compile(r"===== PDF3 page (\d+) =====")
MIN_HEBREW = 0.60      # a page below this is not Hebrew and is not measured
MIN_CHARS = 200        # nor is a page with almost nothing on it


def hebrew(text: str) -> bool:
    letters = [c for c in text if not c.isspace()]
    return (len(letters) >= MIN_CHARS
            and sum(bool(HEB.match(c)) for c in letters) / len(letters) >= MIN_HEBREW)


def rate(pages: dict[int, str], lex: set[str], keep: set[int]) -> tuple[int, float]:
    """Words, and the share of them unattested, over *keep* only."""
    bad = tot = 0
    for n, text in pages.items():
        if n in keep:
            _, b, t = ocrqual.suspects(text, lex)
            bad, tot = bad + b, tot + t
    return tot, bad / tot if tot else 0.0


def scan(path: str) -> dict[int, str]:
    """A `===== PDF3 page NNN =====` transcript, split by page."""
    text = open(path, encoding="utf-8").read()
    parts = PAGE_RE.split(text)
    return {int(parts[i]): parts[i + 1] for i in range(1, len(parts) - 1, 2)}


def readings(base: str) -> dict[str, dict[int, str]]:
    """Every reading of the volume that survives, keyed by page."""
    layer = json.load(open(f"{base}/data/book_layer.json", encoding="utf-8"))["pages"]

    def joined(p, kind):
        return " ".join(t for t, _ in p[kind])

    def zone(name):
        try:
            return {d["page"]: d.get("body") or "" for d in
                    json.load(open(f"{base}/data/{name}", encoding="utf-8"))}
        except FileNotFoundError:
            return {}

    def ens(name, drop=()):
        """One arbitrated stage, optionally without the words it did not read."""
        try:
            pages = json.load(open(f"{base}/data/{name}", encoding="utf-8"))["pages"]
        except FileNotFoundError:
            return {}
        return {p["page"]: " ".join(t for t, w in p["body"] if w not in drop)
                for p in pages}

    out = {
        "tesseract-heb --psm 6, 300 dpi, whole page":
            scan(f"{base}/out/AmudeiKesef_hebrewbooks_OCR_raw.txt"),
        "publisher's text layer, whole page":
            {p["page"]: joined(p, "body") + " " + joined(p, "notes") for p in layer},
        "publisher's text layer, Kaspi zone":
            {p["page"]: joined(p, "body") for p in layer},
        "tesseract-heb --psm 6, 300 dpi, Kaspi zone": zone("book_tess300.json"),
        "tesseract-heb_best --psm 4, 600 dpi, Kaspi zone": zone("book_tess.json"),
        # The fourth reading, made by looking. It is a reading like the others
        # and is measured like the others; the row is here so the claim that it
        # is better than machine OCR is a number rather than an assertion.
        "read by eye off the scan, Kaspi zone": zone("book_eyes.json"),
        "readings arbitrated, Kaspi zone":
            ens("ensemble_arbitrated.json", drop=("guide",)),
        "…with quotations restored from Ibn Tibbon":
            ens("ensemble_arbitrated.json"),
        "…and confusions repaired from the volume's own evidence":
            ens("ensemble.json"),
    }
    return {k: v for k, v in out.items() if v}


def run(base: str = ".") -> dict:
    corpus = json.load(open(f"{base}/data/corpus.json", encoding="utf-8"))
    lex = ocrqual.lexicon(*(" ".join(sum(w.values(), [])) for w in corpus.values()))
    reads = readings(base)

    # One page set for every stage, or the stages are not comparable. Take it
    # from the reading that sees both scripts and has geometry behind it.
    keep = {n for n, t in reads["publisher's text layer, whole page"].items()
            if hebrew(t)}

    rows = [{"reading": name, "words": w, "unattested": r}
            for name, pages in reads.items()
            for w, r in [rate(pages, lex, keep)]]

    ens = json.load(open(f"{base}/data/ensemble.json", encoding="utf-8"))
    every = [(t, w) for p in ens["pages"] if p["page"] in keep for t, w in p["body"]]
    why = {k: sum(1 for _, w in every if w == k)
           for k in ("guide", "agree", "most", "seen", "lex", "fix",
                     "keep", "doubt")}

    return {"pages": len(keep), "skipped": len(reads["publisher's text layer,"
                                                    " whole page"]) - len(keep),
            "lexicon": len(lex), "rows": rows, "why": why,
            "certain": sum(why[k] for k in ("guide", "agree")) / max(1, len(every)),
            "floor": ocrqual.calibrate(f"{base}/data/corpus.json")}


FLOOR = "clean born-digital text, same test (the floor)"


def table(m: dict) -> str:
    """The stage table, its columns sized to whatever the longest label is."""
    w = max(len(FLOOR), *(len(r["reading"]) for r in m["rows"])) + 2
    rule = "  " + "─" * (w + 21)
    out = [f"Measured over the {m['pages']} Hebrew pages of the 1848 print "
           f"({m['skipped']} pages of German and Latin matter excluded),",
           f"against a lexicon of {m['lexicon']:,} word-forms from the clean "
           f"witnesses.", "",
           f"  {'reading':<{w}}{'words':>9}{'unattested':>12}", rule]
    first = None
    for r in m["rows"]:
        first = r["unattested"] if first is None else first
        gain = "" if r is m["rows"][0] else f"   {1 - r['unattested']/first:+.0%}"
        out.append(f"  {r['reading']:<{w}}{r['words']:>9,}{r['unattested']:>11.2%}{gain}")
    out += [rule,
            f"  {FLOOR:<{w}}{'—':>9}{min(f['rate'] for f in m['floor']):>10.1%}"
            f"–{max(f['rate'] for f in m['floor']):.1%}", "",
            "Where each surviving word came from:"]
    label = {"guide": "restored verbatim from Ibn Tibbon — known, not read",
             "agree": "every reader that saw a word returned the same one",
             "most": "readers differed; a majority carried the word",
             "seen": "a machine consensus one stroke from what the eye saw",
             "lex": "readers differed; only one reading was a Hebrew word",
             "fix": "no reading was a word; one repair made it one",
             "keep": "readers differed; several were words — earliest kept",
             "doubt": "no reading is a word and no single repair helps"}
    tot = sum(m["why"].values())
    for k in ("guide", "agree", "most", "seen", "lex", "fix", "keep", "doubt"):
        out.append(f"  {label[k]:<55}{m['why'][k]:>8,}{m['why'][k]/tot:>7.1%}")
    out.append(f"\n  {'certain (restored or unanimous)':<55}"
               f"{sum(m['why'][k] for k in ('guide','agree')):>8,}{m['certain']:>7.1%}")
    return "\n".join(out)


if __name__ == "__main__":
    base = sys.argv[1] if len(sys.argv) > 1 else "."
    m = run(base)
    json.dump(m, open(f"{base}/data/measure.json", "w", encoding="utf-8"),
              ensure_ascii=False, indent=1)
    print(table(m))
