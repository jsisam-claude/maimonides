#!/usr/bin/env python3
"""Typeset the edition as a book: one PDF, laid out for paper.

The screen edition is a workbench — three panes, toggles, a search box. Paper
has no hover, so the print keeps what survives on paper and nothing else: the
Guide text, the two commentaries beneath it chapter by chapter, the apparatus
under each block with its sigla and its photographs of the ink, and the method
introduction. Everything is taken from the *built* edition file, not from the
pipeline: the page drives the same data island a reader's browser inflates, so
the book that is printed is by construction the book that was checked — same
texts, same notes, same numbers in the introduction. Nothing is retyped.

The introduction is the edition's own method panel, captured by clicking the
button a reader would click. If the panel's wording or figures change, the PDF
follows on the next build; there is no second copy to go stale.

The page follows the layout of the critical editions this volume sits beside
(and of the 2025 edition used as this project's yardstick): the Guide's own
text stands at the head of the page in a larger face on a narrower measure;
the commentary sits beneath it in two headed columns, smaller, in a different
face; the apparatus runs under both, full measure, above nothing. The two
texts must be tellable apart at arm's length, before a word is read — that is
what the layout is *for* — so the distinction is carried three ways at once:
face (Hadasim for Maimonides, Frank Ruehl for Kaspi), size, and architecture.
Lemma quotations inside the commentary are bold, as that tradition sets them.
The apparatus keeps the edition's bracket convention (lemma ] then readings,
siglum subscripted, photograph last), numbered continuously through the unit.

Dependencies: playwright + the culmus fonts, both already in the toolchain.
"""
from __future__ import annotations

import os
import re
import sys

from playwright.sync_api import sync_playwright

# Parts open with a divider leaf, as the 1848 volume opens them with a banner.
PARTS = {"ch:1:1": "חלק ראשון", "intro:2:0": "חלק שני", "intro:3:0": "חלק שלישי"}

CSS = """
@page{size:A4}
*{box-sizing:border-box}
body{font-family:'Frank Ruehl CLM',serif;color:#000;margin:0;
     font-size:11pt;line-height:1.55;text-align:justify}
h1,h2,h3{font-family:'David CLM',serif;font-weight:700;text-align:center;
         margin:0}

/* ── the title leaf, framed as such books frame their gates ── */
.leaf{page-break-before:always;page-break-after:always;min-height:250mm;
      display:flex;align-items:stretch}
.leaf:first-child{page-break-before:auto}
.leaf>div{border:1.1pt solid #000;outline:.4pt solid #000;
          outline-offset:2.2pt;flex:1;display:flex;flex-direction:column;
          justify-content:center;align-items:center;text-align:center;
          padding:14mm}
.title h1{font-size:36pt;letter-spacing:.04em}
.title .who{font-size:15pt;margin-top:9mm;line-height:2}
.title .works{font-size:20pt;font-weight:700;font-family:'David CLM';
              margin-top:7mm}
.title .src,.title .ed{font-size:11.5pt;margin-top:9mm;line-height:1.9;
                       color:#222}
.title .rule{width:38mm;border-bottom:.6pt solid #000;margin-top:9mm}
.part h1{font-size:32pt}

/* ── the introduction, verbatim from the edition's method panel ── */
.intro{page-break-before:always;page-break-after:always}
.intro h2{font-size:17pt;margin:0 0 6mm}
.intro h4{font-family:'David CLM';font-size:13.5pt;text-align:right;
          margin:5mm 0 1.5mm}
.intro p{margin:0 0 2.2mm;font-size:12pt;line-height:1.7}
.intro b{font-weight:700}
.intro em{font-style:normal;color:#444}

/* ── the page: the Guide above, the commentary below in columns ──
   The two texts are told apart before they are read: Maimonides in Hadasim
   on the wide leading and the narrow measure of a base text, Kaspi under him
   in Frank Ruehl, two sizes down, in the two headed columns of the printed
   commentary tradition. */
section.unit{margin:0 0 7mm}
.unit h2{font-size:16pt;margin:7mm 0 1mm;page-break-after:avoid}
.unit .cite{text-align:center;font-size:9.5pt;color:#555;margin:0 0 3mm;
            page-break-after:avoid}
.guide{font-family:'Hadasim CLM',serif;font-size:14.5pt;line-height:1.8;
       margin:0 7mm 3.5mm}
.guide p{margin:0 0 2mm;text-indent:5mm}
.guide p:first-child{text-indent:0}
.guide p:last-child{text-align-last:center}
.comm{column-count:2;column-gap:8mm;column-fill:balance}
.work h3{font-size:12pt;margin:2.5mm 0 1.2mm;column-span:all}
.work:first-child h3{margin-top:0}
.work .body{font-size:11pt;line-height:1.58}
.empty{color:#555;font-size:11.5pt;text-align:center}

/* lemma quotations: bold in the commentary, as the tradition sets them */
.work .q{font-weight:700}
.guide .q{font-weight:inherit}
sup.fn{font-size:7pt;line-height:0}

/* the marks, as in the edition: thin underlines, each kind its own line */
u{text-decoration-thickness:.5pt;text-underline-offset:.18em}
u.x{text-decoration:underline wavy #555}
u.doubt{text-decoration:underline dotted #000}
u.most,u.seen,u.lex,u.fix,u.keep{text-decoration:underline dotted #777}
u.guide{text-decoration:underline solid #999}
u.note{text-decoration:none}

/* ── the apparatus: full measure beneath both columns ── */
.notes{border-top:.5pt solid #000;margin-top:2.6mm;padding-top:1.3mm;
       font-size:9.8pt;line-height:1.75;text-align:right}
.notes span{margin-inline-end:3.2mm;display:inline-block}
.notes b{font-size:7pt;vertical-align:super;font-weight:700}
.notes q{quotes:none;font-weight:700}
.notes s{text-decoration:none;margin:0 .35mm}
.notes em{font-style:normal}
.notes em.was{color:#333}
.notes em sub{font-size:7pt}
.notes img{max-height:1.7em;vertical-align:middle;margin-inline-start:.8mm;
           image-rendering:auto}

/* ── back matter ── */
.addenda{page-break-before:always}
.addenda h2{font-size:17pt;margin-bottom:5mm}
.addenda h3{text-align:right;font-size:13pt;margin:4mm 0 1.5mm}
.colophon{page-break-before:always;text-align:center;font-size:11.5pt;
          color:#333;display:flex;align-items:center;justify-content:center;
          min-height:240mm;line-height:2.1}
"""


def note(x: list, i: int) -> str:
    """One apparatus entry — the Python twin of the page's own `note`."""
    return ("<span><b>%d</b><q>%s</q><s>]</s>%s%s%s</span>" % (
        i + 1, x[0],
        '<em class="was">%s</em>' % x[2] if x[2] else "",
        "".join("<em>%s<sub>%s</sub></em>" % (f, g) for f, g in x[3]),
        '<img src="%s" alt="">' % x[1] if x[1] else ""))


SUP = re.compile(r'(<sup class="fn">)(\d+)(</sup>)')


def unit(key: str, u: dict, label: str) -> str:
    """One chapter, in the architecture of the printed tradition.

    The Guide's text first, on its own measure; then the two commentaries in
    balanced columns; then one apparatus, full width, under both. On screen
    each commentary numbers its own notes, because each work's notes print
    under it — here they share a shelf, so Maskiyot's numbers continue from
    where Amudei's stop, in the body and in the notes alike, and no number
    appears twice on a page.
    """
    out = ['<section class="unit" id="%s">' % key]
    out.append("<h2>%s</h2>" % label)
    if u.get("p"):
        out.append('<div class="cite">דפוס פרנקפורט תר״ח, דף %s</div>' % u["p"])
    if u.get("g"):
        out.append('<div class="guide">%s</div>' % u["g"])
    n = u.get("n") or {}
    a_notes = n.get("a") or []
    m_notes = (n.get("m") or []) if u.get("m") else []
    cols = []
    for f, name in (("a", "עמודי כסף"), ("m", "משכיות כסף")):
        body = u.get(f)
        if not body:
            continue
        if f == "m" and a_notes:
            body = SUP.sub(lambda m: "%s%d%s" % (m.group(1),
                                                 int(m.group(2)) + len(a_notes),
                                                 m.group(3)), body)
        cols.append('<div class="work"><h3>%s</h3><div class="body">%s</div></div>'
                    % (name, body))
    if cols:
        out.append('<div class="comm">%s</div>' % "".join(cols))
        shelf = a_notes + m_notes
        if shelf:
            out.append('<div class="notes">%s</div>' % "".join(
                note(x, i) for i, x in enumerate(shelf)))
    elif u.get("g"):
        out.append('<p class="empty">אין פירוש כספי לפרק זה בדפוס פרנקפורט תר״ח.</p>')
    out.append("</section>")
    return "".join(out)


def compose(d: dict, panel: str) -> str:
    m = d["meta"]
    body = ["""<!doctype html><html lang="he" dir="rtl"><head><meta charset="utf-8">
<title>מורה נבוכים עם עמודי כסף ומשכיות כסף</title><style>%s</style></head><body>""" % CSS]

    body.append("""
<div class="leaf title"><div>
 <h1>מורה נבוכים</h1>
 <div class="who">לרבנו משה בן מימון זצ״ל<br>
   בהעתקת ר׳ שמואל בן יהודה אבן תיבון</div>
 <div class="rule"></div>
 <div class="works">עם שני פירושי ר׳ יוסף אבן כספי<br>עמודי כסף · ומשכיות כסף</div>
 <div class="rule"></div>
 <div class="src">הפירושים נדפסו לראשונה מכתבי־יד מינכן ולייפציג<br>
   על ידי שלמה זלמן ווערבלונר · פרנקפורט דמיין · תר״ח (1848)</div>
 <div class="ed">מהדורה דיגיטלית ביקורתית<br>
   הוקמה מן הדפוס בזיהוי־תווים רב־עדים, הושבה על סדר המורה,<br>
   ולוותה באפרט של תיקונים, חילופים וצילומי הדיו · תשפ״ו 2026</div>
</div></div>""")

    # The keyboard section serves a reader with keys; paper has none.
    panel = re.sub(r"<h4>מקלדת</h4>.*?(?=<h4>|$)", "", panel, flags=re.S)
    body.append('<section class="intro"><h2>מבוא — דרך המהדורה</h2>%s</section>'
                % panel)

    for key in d["order"]:
        if key in PARTS:
            body.append('<div class="leaf part"><div><h1>%s</h1></div></div>'
                        % PARTS[key])
        u = d["units"].get(key) or {}
        if not (u.get("g") or u.get("a") or u.get("m")):
            continue
        body.append(unit(key, u, d["labels"].get(key, key)))

    if d.get("addenda"):
        body.append('<section class="addenda"><h2>הוספות המגיה מכ״י מינכן</h2>')
        for a in d["addenda"]:
            cite = (' <small>דף %s</small>' % a["page"]) if a.get("page") else ""
            body.append("<h3>%s%s</h3>%s" % (a["label"], cite, a["html"]))
        body.append("</section>")

    body.append("""
<div class="colophon"><div>
 נסדר, נבדק ונמדד במכונה, עמוד עמוד מול הסריקה.<br>
 %d פרקים ו־%d שערי כרך · %s למות מזוהות · %s הערות אפרט ·
 %s תיקונים, כולם מדווחים · %s צילומי דיו.<br>
 המהדורה המלאה, על עדיה וכליה, בקובץ ה־HTML הנלווה.
</div></div>""" % (m["matched"], m.get("front", 0), "{:,}".format(m["quotes"]),
                   "{:,}".format(m["notes"]), "{:,}".format(m["mended"]),
                   "{:,}".format(m["inked"])))
    body.append("</body></html>")
    return "\n".join(body)


def main() -> None:
    base = sys.argv[1] if len(sys.argv) > 1 else "."
    src = os.path.abspath(f"{base}/out/MorehNevukhim_KaspiEdition.html")
    mid = f"{base}/out/MorehNevukhim_Kaspi_print.html"
    dst = f"{base}/out/MorehNevukhim_KaspiEdition.pdf"

    with sync_playwright() as p:
        browser = p.chromium.launch()
        pg = browser.new_page()
        pg.goto("file://" + src)
        # D is a page-scope const, not a window property — probe it bare.
        pg.wait_for_function("typeof D!=='undefined' && !!D.order")
        pg.click("#about")
        panel = pg.evaluate("document.getElementById('dlgbody').innerHTML")
        data = pg.evaluate(
            "({order:D.order, labels:D.labels, units:D.units,"
            "  addenda:D.addenda, meta:D.meta})")
        pg.close()

        open(mid, "w", encoding="utf-8").write(compose(data, panel))

        pg = browser.new_page()
        pg.goto("file://" + os.path.abspath(mid))
        pg.wait_for_timeout(1500)
        # The running head of the tradition: title centred, folio at the
        # outer (left) edge, a hair-rule under both.
        pg.pdf(path=dst, format="A4", print_background=False,
               display_header_footer=True,
               header_template="""<div style="width:100%;margin:0 17mm;
                 font-family:'Frank Ruehl CLM',serif;font-size:9pt;color:#333;
                 border-bottom:0.5pt solid #999;padding-bottom:2pt;
                 display:flex;direction:ltr">
                 <span class="pageNumber"></span>
                 <span style="flex:1;text-align:center">מורה נבוכים · עמודי כסף ומשכיות כסף</span>
                 <span style="visibility:hidden" class="pageNumber"></span></div>""",
               footer_template="<span></span>",
               margin={"top": "20mm", "bottom": "16mm",
                       "left": "17mm", "right": "17mm"})
        browser.close()

    os.remove(mid)
    print(f"pdf: {dst}  {os.path.getsize(dst)/1048576:.1f} MB", file=sys.stderr)


if __name__ == "__main__":
    main()
