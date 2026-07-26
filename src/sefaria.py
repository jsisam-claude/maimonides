#!/usr/bin/env python3
"""Package Kaspi's two commentaries as a contribution to Sefaria.

Sefaria's library holds the Guide and its classical commentators, but neither
of Kaspi's commentaries exists there as a digital text. This module emits the
package their curators need: one structured JSON per work, keyed the way the
Guide is cited (part and chapter, with the front matter named), a README
stating provenance and measured quality, and a CC0 dedication — the license a
transcription of a public-domain print ought to carry, and the one that lets
Sefaria do anything at all with it.

The text is read out of the *built and checked* edition file, exactly as
`print.py` reads it: what is contributed is what was asserted in a browser,
not a parallel export that can drift. Markup is reduced to plain text —
footnote numbers removed whole, apparatus left behind in the source
repository — because a library text is a reading text; the critical apparatus
stays with the edition that explains it.

Copyright, so the reasoning is on the record: Kaspi died c. 1345 and Ibn
Tibbon c. 1230, so the words are public domain everywhere. The 1848 Werbluner
printing is pre-1930, public domain in the US, and its editor cannot have
survived into any term still running. Scans of that printing (Hebrewbooks,
daat) are faithful reproductions of public-domain pages and take no new
rights. The one collation source, Sefaria's Ibn Tibbon version, is marked
Public Domain in its own metadata. The 2025 critical edition used as this
project's yardstick contributed measurements and not one word of text. What
remains — the transcription labour itself — is dedicated here.

Dependencies: none (Python standard library).
"""
from __future__ import annotations

import base64
import gzip
import html
import json
import os
import re
import sys
import zipfile

ISLAND = re.compile(
    r'<script type="application/octet-stream" id="data"([^>]*)>([^<]+)</script>')
MAP = re.compile(r'data-map="([^"]*)"')
SUP = re.compile(r"<sup[^>]*>.*?</sup>", re.S)
TAG = re.compile(r"<[^>]+>")
PARA = re.compile(r"<p>(.*?)</p>", re.S)
WS = re.compile(r"\s+")

# Where each front unit lives in the Guide as Sefaria names its parts.
FRONT = {"kaspi:0:0": "Author's Preface",
         "letter:0:0": "Commentary on the Epistle Dedicatory",
         "pref:0:0": "Commentary on the Introduction",
         "intro:1:0": "Commentary on the Introduction, the causes of contradiction",
         "intro:2:0": "Part II, Introduction (the twenty-five propositions)",
         "intro:3:0": "Part III, Introduction"}

WORKS = {"a": ("Amudei Kesef", "עמודי כסף"),
         "m": ("Maskiyot Kesef", "משכיות כסף")}


def island(path: str) -> dict:
    """The data island of the built edition, decoded as the browser decodes it."""
    m = ISLAND.search(open(path, encoding="utf-8").read())
    raw = gzip.decompress(base64.b64decode(m.group(2).strip()))
    fold = MAP.search(m.group(1))
    if fold and fold.group(1):
        # The chat build folds Hebrew into one byte per letter and carries the
        # alphabet it used; the full build is plain UTF-8 and carries none.
        # Decoding the wrong branch is not an error anywhere — it is mojibake
        # in every word, which is why the sanity pass downstream counts
        # Hebrew letters instead of trusting this function.
        alpha = fold.group(1)
        txt = "".join(alpha[ord(c) - 0xA0]
                      if 0xA0 <= ord(c) < 0xA0 + len(alpha) else c
                      for c in raw.decode("latin-1"))
    else:
        txt = raw.decode("utf-8")
    return json.loads(txt)


def plain(rendered: str) -> list[str]:
    """Paragraphs of reading text: notes' numbers gone whole, tags stripped."""
    out = []
    for p in PARA.findall(rendered or ""):
        t = WS.sub(" ", html.unescape(TAG.sub("", SUP.sub("", p)))).strip()
        if re.search(r"[א-ת]", t):     # a paragraph with no letters is noise
            out.append(t)
    return out


def build(base: str) -> None:
    D = island(f"{base}/out/MorehNevukhim_KaspiEdition.html")
    meta = D["meta"]
    dst = f"{base}/out/sefaria"
    os.makedirs(dst, exist_ok=True)

    for field, (en, he) in WORKS.items():
        front, parts = {}, {"1": {}, "2": {}, "3": {}}
        segs = chapters = 0
        for key in D["order"]:
            text = plain((D["units"].get(key) or {}).get(field))
            if not text:
                continue
            if key in FRONT:
                front[FRONT[key]] = text
            else:
                _, p, c = key.split(":")
                parts[p][c] = text
                chapters += 1
            segs += len(text)
        work = {
            "title": en, "heTitle": he,
            "author": "Joseph ibn Kaspi (c. 1280 – c. 1345)",
            "base_text": "Guide for the Perplexed, tr. Samuel ibn Tibbon",
            "versionTitle": f"{en}, Frankfurt 1848 (ed. S. Werbluner), "
                            "digital transcription 2026",
            "versionSource": "https://github.com/jsisam-claude/maimonides",
            "language": "he",
            "license": "CC0",
            "front_matter": front,
            "parts": {p: dict(sorted(ch.items(), key=lambda kv: int(kv[0])))
                      for p, ch in parts.items() if ch},
            "coverage": {"chapters_with_commentary": chapters,
                         "front_sections": len(front), "segments": segs},
        }
        name = en.lower().replace(" ", "_") + ".json"
        json.dump(work, open(f"{dst}/{name}", "w", encoding="utf-8"),
                  ensure_ascii=False, indent=1)
        print(f"  {name}: {chapters} chapters, {len(front)} front sections, "
              f"{segs} segments", file=sys.stderr)

    if D.get("addenda"):
        add = [{"label": a["label"], "printed_page": a.get("page"),
                "text": plain(a["html"])} for a in D["addenda"]]
        json.dump({"title": "Addenda from MS Munich (ed. Werbluner, 1848)",
                   "license": "CC0", "blocks": add},
                  open(f"{dst}/addenda_munich.json", "w", encoding="utf-8"),
                  ensure_ascii=False, indent=1)

    open(f"{dst}/README.md", "w", encoding="utf-8").write(README % (
        meta["matched"], meta["quotes"], meta["mended"]))
    open(f"{dst}/LICENSE.md", "w", encoding="utf-8").write(CC0)

    with zipfile.ZipFile(f"{base}/out/sefaria_contribution.zip", "w",
                         zipfile.ZIP_DEFLATED) as z:
        for f in sorted(os.listdir(dst)):
            z.write(f"{dst}/{f}", f"kaspi_guide_commentaries/{f}")
    print(f"zip: {base}/out/sefaria_contribution.zip", file=sys.stderr)


README = """\
# Kaspi's commentaries on the Guide — contribution package

Joseph ibn Kaspi's two commentaries on Maimonides' *Guide of the Perplexed*
— **עמודי כסף** (the exoteric commentary) and **משכיות כסף** (the esoteric
one) — transcribed from their only printing, S. Werbluner's Frankfurt 1848
edition, from the Hebrewbooks and daat.ac.il scans.

Neither work currently exists on Sefaria as a digital text.

## What is in the package

`amudei_kesef.json`, `maskiyot_kesef.json` — one file per work. Text is
keyed to the Guide's structure as Sefaria cites it: the front sections by
name, then parts 1–3 by chapter number, each chapter an array of paragraphs
(paragraph breaks follow the lemmata of the 1848 print). `addenda_munich.json`
carries the chapters Werbluner found only in MS Munich and printed as
addenda. %d Guide chapters carry a commentary; chapters the 1848 print does
not comment on are simply absent.

## How the text was made, and how far to trust it

The print was read by four witnesses (the scan's text layer, Tesseract at two
settings, and a human-guided reading of the ink), arbitrated word by word
against a 43,929-form lexicon built from Ibn Tibbon and the classical Guide
commentators, and repaired using a confusion table learned from 21,663
optically witnessed letter pairs. The %d lemma quotations were verified
verbatim against Ibn Tibbon's text (Sefaria's own Public Domain version).
Measured against a 2025 manuscript-based critical edition over its sample
region, word accuracy is 93.1%%; 2.9%% of tokens remain unattested by the
lexicon and should be treated as possible OCR errors. Every one of the %d
places where the transcription's machinery altered a reading of the print is
recorded, with the pre-correction reading and rejected variants, in the
apparatus of the source edition:
https://github.com/jsisam-claude/maimonides — which also holds the full
pipeline, so the text is reproducible from the scans.

This is a diplomatic transcription of the 1848 print (with its orthography),
not a critical text from the manuscripts. Sefaria may wish to flag it as a
digitization open to correction.

## Rights

Kaspi (d. c. 1345) and Ibn Tibbon (d. c. 1230) are public domain everywhere.
The 1848 printing is public domain (pre-1930 publication; its editor's term,
under any life+70 rule, expired in the nineteenth or early twentieth
century). The scans are faithful reproductions of public-domain pages and
take no new rights. The transcription labour is dedicated under CC0 — see
LICENSE.md. No text from any in-copyright edition was used: the one modern
critical edition consulted served as an accuracy yardstick only, and not one
word of it enters this text.
"""

CC0 = """\
# CC0 1.0 Universal

To the extent possible under law, the contributors of this transcription of
Joseph ibn Kaspi's *Amudei Kesef* and *Maskiyot Kesef* (Frankfurt 1848) have
waived all copyright and related or neighboring rights to the transcription,
its structure and its packaging, worldwide. The underlying works are public
domain.

Full legal text: https://creativecommons.org/publicdomain/zero/1.0/legalcode
"""


if __name__ == "__main__":
    build(sys.argv[1] if len(sys.argv) > 1 else ".")
