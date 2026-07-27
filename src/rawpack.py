#!/usr/bin/env python3
"""Raw study files: every unarbitrated Kaspi volume, as page-anchored markdown.

The full pipeline — four witnesses, arbitration, repair, apparatus — has run
on one book. Eleven more printed volumes now wait, and waiting text helps
nobody: even the scan's own OCR layer, taken with the salt it deserves, makes
a volume searchable, quotable by scan page, and loadable into an analysis
conversation today. So this module does deliberately little: it reads each
PDF's embedded text layer, strips the bidi control characters the layer is
salted with, and writes one markdown file per volume, one section per scan
page, under a banner that states exactly what the file is — a raw first
reading, not an established text.

The banner also carries a measured number, not a shrug: the share of the
volume's word-forms attested in the project's 43,929-form lexicon, the same
instrument the edition uses. A reader deciding how far to trust a quotation
sees the volume's own figure beside it. (For calibration: clean witnesses
score 96–99% attested; the arbitrated-and-repaired 1848 edition, 97.1%.)

Dependencies: pdftotext (poppler), plus the project corpus for the lexicon.
"""
from __future__ import annotations

import json
import os
import re
import subprocess
import sys
import zipfile

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import ocrqual

UPLOADS = "/root/.claude/uploads/ca27e3be-5e31-54b5-a0cd-e849fa507b0e"

# file prefix → (slug, Hebrew title, source note)
VOLUMES = [
    ("8ffb7e30", "adnei_kesef_1", "אדני כסף — חלק א",
     "נביאים ראשונים וישעיהו · מהד' לאסט, לונדון תרע\"א · כ\"י אוקספורד · HB 26882"),
    ("d8b31336", "tirat_kesef", "משנה כסף א — טירת כסף",
     "ביאור התורה בכלל · מהד' לאסט, פרשבורג תרס\"ה · HB 9458"),
    ("71f306ab", "matzref_lakesef", "משנה כסף ב — מצרף לכסף",
     "ביאור התורה בפרט · מהד' לאסט, קרקא תרס\"ו · HB 9459"),
    ("647e2e5f", "chatzotzrot_mishlei_1", "חצוצרות כסף — משלי א",
     "כ\"י פריז · מהד' לאסט · HB 33605"),
    ("13ba2d11", "chatzotzrot_mishlei_2", "חצוצרות כסף — משלי ב",
     "כ\"י מינכן · מהד' לאסט · HB 33606"),
    ("14e4f565", "shir_kohelet", "חצוצרות כסף — שיר השירים וקהלת",
     "שה\"ש ע\"פ דפוס קושטא של\"ז; קהלת משני כ\"י אוקספורד · HB 33604"),
    ("fccfd65a", "chagorat_kesef", "חגורת כסף — עזרא נחמיה ודברי הימים",
     "כ\"י אוקספורד · HB 33578"),
    ("21193ca8", "shulchan_kesef", "שלחן כסף — איוב",
     "כ\"י מינכן 265 · HB 35224"),
    ("597dac79", "tam_hakesef", "תם הכסף — שמונה דרשות",
     "מהד' לאסט, לונדון תרע\"ג · HB 39632"),
    ("cf107f9f", "sodot_raava", "פירוש הסודות לראב\"ע",
     "כ\"י אוקספורד (נויבאואר 227, 232) · HB 34555"),
    ("6e4aac5b", "nekarot_kesef", "נקרות כסף — מכתבים והערות",
     "הארות חכמי הדור על דברי כספי · HB 34190"),
    ("83b1104d", "asara_1_front", "עשרה כלי כסף א — שערים ומבוא לאסט (חלקי)",
     "מבוא המהדיר וקטלוג קבוצת כסף בלבד; גוף הכרך חסר · HB 34512"),
    ("63afe14c", "asara_2_front", "עשרה כלי כסף ב — שערים ותחילת איכה (חלקי)",
     "גוף הכרך — ובו מנורת כסף, עמ' 75–142 — חסר · HB 34513"),
]

BIDI = re.compile("[‎‏‪-‮⁦-⁩﻿]")
WS = re.compile(r"[ \t]+")

BANNER = """\
> **קריאה גולמית — לא טקסט מבוקר.** שכבת ה־OCR של הסריקה כפי שהיא, ללא
> בוררות עדים וללא תיקון. לחיפוש, להתמצאות ולציטוט־לפי־עמוד; כל ציטוט
> ייבדק מול הסריקה. מלים מאושרות במילון הפרויקט: **{rate:.0%}**
> (עד נקי: ‎96–99%; מהדורת תר\"ח לאחר בוררות: ‎97.1%).
> המקור: {src}. הטקסט נחלץ בפרויקט
> https://github.com/jsisam-claude/maimonides
"""


def clean(page: str) -> str:
    lines = [WS.sub(" ", BIDI.sub("", ln)).strip() for ln in page.split("\n")]
    return "\n".join(ln for ln in lines if ln)


def rate(text: str, lex: set[str]) -> float:
    words = [w for w in ocrqual.WORD.findall(text)]
    if not words:
        return 0.0
    return sum(bool(ocrqual.attested(w, lex)) for w in words) / len(words)


def main() -> None:
    base = sys.argv[1] if len(sys.argv) > 1 else "."
    corpus = json.load(open(f"{base}/data/corpus.json", encoding="utf-8"))
    lex = ocrqual.lexicon(*(" ".join(sum(w.values(), []))
                            for w in corpus.values()))
    dst = f"{base}/out/raw"
    os.makedirs(dst, exist_ok=True)
    index = ["# הספרייה הגולמית — כרכי כספי שטרם עברו בוררות", "",
             "קובץ לכל כרך; פסקה לכל עמוד סריקה. האחוז — מלים מאושרות",
             "במילון (מדד איכות גס; ראו כותרת כל קובץ).", ""]

    for prefix, slug, he, src in VOLUMES:
        pdf = next((f"{UPLOADS}/{f}" for f in os.listdir(UPLOADS)
                    if f.startswith(prefix)), None)
        if not pdf:
            print(f"  MISSING upload {prefix} ({slug})", file=sys.stderr)
            continue
        txt = subprocess.run(["pdftotext", pdf, "-"], capture_output=True,
                             text=True).stdout
        pages = [clean(p) for p in txt.split("\f")]
        body = "\n".join(f"## דף סריקה {i}\n\n{p}\n"
                         for i, p in enumerate(pages, 1) if p)
        r = rate("\n".join(pages), lex)
        head = "# %s\n\n%s\n" % (he, BANNER.format(rate=r, src=src))
        open(f"{dst}/{slug}.md", "w", encoding="utf-8").write(head + body)
        kb = (len(head) + len(body)) // 1024
        index.append("- `%s.md` — %s · %d עמ' · %d kB · מאושרות %.0f%%"
                     % (slug, he, len(pages), kb, 100 * r))
        print(f"  {slug:24} {len(pages):>4} pp  {kb:>5} kB  "
              f"attested {r:.0%}", file=sys.stderr)

    open(f"{dst}/index.md", "w", encoding="utf-8").write("\n".join(index) + "\n")
    with zipfile.ZipFile(f"{base}/out/kaspi_raw_library.zip", "w",
                         zipfile.ZIP_DEFLATED) as z:
        for f in sorted(os.listdir(dst)):
            z.write(f"{dst}/{f}", f"kaspi_raw_library/{f}")
    print(f"zip: {base}/out/kaspi_raw_library.zip", file=sys.stderr)


if __name__ == "__main__":
    main()
