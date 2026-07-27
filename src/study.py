#!/usr/bin/env python3
"""Emit the study pack: Kaspi's commentaries as markdown, shaped for analysis.

The chat-sized HTML edition is for reading — it carries its text gzipped in a
data island, which a browser inflates and an assistant handed the file as
context cannot. For analysing Kaspi's *ideas* in a Claude conversation or
Project, the text has to arrive as text: plain markdown, one file per work,
one heading per chapter, each heading carrying a stable citation siglum
(``AK 1:2``, ``MK 3:26``) so that claims about the ideas can be pinned to the
passage that grounds them. Paragraphs fall at the print's lemmata — the unit
of Kaspi's own argument — and the apparatus stays behind in the edition:
analysis wants the reading text, with one honest note up front about how it
was made and how far to trust it.

Reads the Sefaria contribution JSONs, which were themselves read out of the
built and checked edition — one chain, no second transcription to drift.

Dependencies: none (Python standard library).
"""
from __future__ import annotations

import json
import os
import sys

PARTS = {"1": "חלק ראשון", "2": "חלק שני", "3": "חלק שלישי"}
PART_LEN = {"1": 76, "2": 48, "3": 54}

# The formula the edition itself prints for a chapter the 1848 volume does
# not comment on. Absence must be stated, not implied by a numbering gap:
# Kaspi withheld the Merkabah chapters (III:2–6 run straight from פרק א to
# פרק ז on the page), and a reader of the study pack who meets a silent gap
# cannot tell a source lacuna from a packaging hole.
ABSENT = "אין פירוש בדפוס פרנקפורט תר״ח."

# The front sections, in reading order: Sefaria-package key → Hebrew head +
# citation siglum.
FRONT = [("Author's Preface", "הקדמת המפרש", "0:pref"),
         ("Commentary on the Epistle Dedicatory", "פירוש האגרת לתלמיד", "0:ep"),
         ("Commentary on the Introduction", "פירוש הפתיחה", "0:intro"),
         ("Commentary on the Introduction, the causes of contradiction",
          "פירוש סיבות הסתירה", "0:contra"),
         ("Part II, Introduction (the twenty-five propositions)",
          "פירוש הקדמות החלק השני", "2:intro"),
         ("Part III, Introduction", "פירוש הקדמת החלק השלישי", "3:intro")]

NOTE = """\
> מהדורה דיגיטלית של דפוס פרנקפורט תר״ח (ווערבלונר), שוקמה בזיהוי־תווים
> רב־עדים ונבדקה מול מהדורה ביקורתית מכתבי־יד (דיוק מלים מדוד: ‎93.1%‎;
> ‎2.9%‎ מן המלים אינן מאושרות במילון וייתכן שהן שגיאות קריאה). הפסקאות
> נחתכות בלמות הדפוס. ציטוט: הסיגלה שבכל כותרת ({sig} = {work} חלק:פרק).
> הטקסט מוקדש CC0; המהדורה המלאה על האפרט שלה:
> https://github.com/jsisam-claude/maimonides
"""


def emit(src: str, dst: str, sig: str, work_he: str) -> tuple[int, list]:
    w = json.load(open(src, encoding="utf-8"))
    out = ["# %s — ר׳ יוסף אבן כספי על מורה הנבוכים" % work_he, "",
           NOTE.format(sig=sig, work=work_he), ""]
    toc = []

    def block(head, ref, page, paras):
        cite = " · דף %s" % page if page else ""
        out.append("## %s  [%s %s%s]" % (head, sig, ref, cite))
        out.append("")
        for t in paras:
            out.append(t)
            out.append("")
        toc.append((ref, head, len(" ".join(paras))))

    fm = w.get("front_matter") or {}
    for key, he, ref in FRONT:
        if key in fm and not ref.startswith(("2", "3")):
            block(he, ref, None, fm[key])
    for p in ("1", "2", "3"):
        chs = (w.get("parts") or {}).get(p)
        intro = next((f for f in FRONT if f[2] == p + ":intro"), None)
        if not chs and not (intro and intro[0] in fm):
            continue
        out.append("# %s" % PARTS[p])
        out.append("")
        if intro and intro[0] in fm:
            block(intro[1], intro[2], None, fm[intro[0]])
        for c in map(str, range(1, PART_LEN[p] + 1)):
            if c in (chs or {}):
                block("פרק %s" % c, "%s:%s" % (p, c), None, chs[c])
            else:
                out.append("## פרק %s  [%s %s:%s] — %s"
                           % (c, sig, p, c, ABSENT))
                out.append("")
                toc.append(("%s:%s" % (p, c), "פרק %s — אין פירוש" % c, 0))

    open(dst, "w", encoding="utf-8").write("\n".join(out))
    return len("\n".join(out)), toc


def main() -> None:
    base = sys.argv[1] if len(sys.argv) > 1 else "."
    dst = f"{base}/out/study"
    os.makedirs(dst, exist_ok=True)
    index = ["# מפתח — פירושי אבן כספי למורה הנבוכים", "",
             "One line per section: siglum, head, and size in characters —",
             "the map to load beside either file, or alone as a table of",
             "what Kaspi treats where.", ""]
    for src, sig, he in ((f"{base}/out/sefaria/amudei_kesef.json", "AK", "עמודי כסף"),
                         (f"{base}/out/sefaria/maskiyot_kesef.json", "MK", "משכיות כסף")):
        name = f"{dst}/{sig.lower()}_{'amudei' if sig=='AK' else 'maskiyot'}_kesef.md"
        n, toc = emit(src, name, sig, he)
        if sig == "AK":
            # Werbluner's addenda — matter he found only in MS Munich at the
            # end of Amudei Kesef — belong in the study text, not only in the
            # library package: analysis that stops at the printed run misses
            # Kaspi's own closing pieces.
            add = json.load(open(f"{base}/out/sefaria/addenda_munich.json",
                                 encoding="utf-8"))
            with open(name, "a", encoding="utf-8") as f:
                f.write("\n# הוספות המגיה מכ״י מינכן\n\n")
                for i, b in enumerate(add["blocks"], 1):
                    head = b["label"] or "הוספות מכ״י מינכן"
                    f.write("## %s  [AK add:%d · דף %s]\n\n"
                            % (head, i, b.get("printed_page") or "?"))
                    for t in b["text"]:
                        f.write(t + "\n\n")
                    toc.append(("add:%d" % i, head,
                                len(" ".join(b["text"]))))
        index.append("## %s" % he)
        index.append("")
        for ref, head, chars in toc:
            index.append("- `%s %s` — %s (%d)" % (sig, ref, head, chars))
        index.append("")
        print(f"  {os.path.basename(name)}: {n//1024} kB, "
              f"{len(toc)} sections", file=sys.stderr)
    open(f"{dst}/index.md", "w", encoding="utf-8").write("\n".join(index))


if __name__ == "__main__":
    main()
