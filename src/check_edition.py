#!/usr/bin/env python3
"""Open the built edition in a real browser and assert that it works.

Building an HTML file is not evidence that it renders. This drives the page
headlessly and checks the things that could silently be wrong: that the
gzipped data island actually inflates, that Hebrew arrives as Hebrew (a
mojibake bug would still produce a page), that the layout is right-to-left
and three-columned, that a lemma lights up its counterpart in the base text,
that navigation moves between chapters, and that search finds a word we know
is there. Screenshots are written for the eye to check what assertions cannot.

Dependencies: playwright (dev-time only; the edition itself has none).
"""
from __future__ import annotations

import os
import sys

from playwright.sync_api import sync_playwright

BASE = os.path.join(os.path.dirname(os.path.abspath(__file__)), "..")
FILE = os.path.abspath(f"{BASE}/out/MorehNevukhim_KaspiEdition.html")
SHOT = os.path.abspath(f"{BASE}/out/shots")

HEBREW = "אבגדהוזחטיכלמנסעפצקרשת"


def main(path: str = FILE, shots: str = SHOT) -> int:
    os.makedirs(shots, exist_ok=True)
    fails: list[str] = []

    def check(name: str, ok: bool, detail: str = "") -> None:
        print(f"  {'PASS' if ok else 'FAIL'}  {name}"
              f"{'  — ' + detail if detail else ''}", file=sys.stderr)
        if not ok:
            fails.append(name)

    with sync_playwright() as pw:
        b = pw.chromium.launch()
        pg = b.new_page(viewport={"width": 1600, "height": 1000})
        errs: list[str] = []
        pg.on("pageerror", lambda e: errs.append(str(e)))
        pg.on("console", lambda m: errs.append(m.text) if m.type == "error" else None)

        pg.goto("file://" + os.path.abspath(path))
        # `let D` is a global *lexical* binding, so it is not a window property
        pg.wait_for_function("typeof D !== 'undefined' && D.order", timeout=20000)

        check("no JS errors", not errs, "; ".join(errs[:3]))
        n = pg.evaluate("Object.keys(D.units).length")
        # 178 chapters, the Guide's five front sections, and Kaspi's own
        # preface, which has no Guide text and is a unit all the same.
        check("data island inflated", n == 184, f"{n} units")

        check("document is RTL", pg.evaluate("document.documentElement.dir") == "rtl")
        wide = pg.evaluate("D.wit.length > 0")
        cols = pg.evaluate("getComputedStyle(document.querySelector('main'))"
                           ".gridTemplateColumns").split()
        want = 3 if wide else 2
        check(f"{want} columns", len(cols) == want, " / ".join(cols))

        # Hebrew survived the gzip/base64/JSON round trip. Sampled at I:1 —
        # the volume now lands on Kaspi's preface, whose Guide pane is
        # rightly empty, so the sample must go where Guide text is.
        pg.evaluate("location.hash='ch:1:1'")
        pg.wait_for_timeout(150)
        txt = pg.inner_text("#guide")
        heb = sum(c in HEBREW for c in txt)
        check("guide text is Hebrew", heb > 200 and heb / max(1, len(txt)) > 0.5,
              f"{heb}/{len(txt)} letters")
        check("no replacement chars", "�" not in txt)

        # column order: in RTL the first grid child sits on the right
        want_panes = "['#right','#centre','#left']" if wide else "['#right','#centre']"
        r = pg.evaluate("()=>%s.map(x=>document.querySelector(x)"
                        ".getBoundingClientRect().x)" % want_panes)
        check("Kaspi to the right of the Guide"
              + (", commentators left" if wide else ""),
              all(a > b for a, b in zip(r, r[1:])),
              f"x = {[round(x) for x in r]}")

        pg.screenshot(path=f"{shots}/01_open.png", full_page=False)

        # a chapter with both commentaries and lemmata
        key = pg.evaluate("D.order.find(k=>D.units[k].m && "
                          "D.units[k].a.includes('data-q'))")
        pg.evaluate(f"location.hash={key!r}")
        pg.wait_for_timeout(250)
        check("found a chapter with both commentaries", bool(key), key or "")

        nq = pg.eval_on_selector_all("#kaspi .q", "e=>e.length")
        check("lemmata marked in Kaspi", nq > 0, f"{nq} spans")

        # The apparatus's one unconditional promise, asserted rather than
        # printed. `altered` counts the words this edition changed, taken from
        # the book; `mended` counts the notes that say so. They were once 558
        # and 133, and the method panel claimed they were equal. A renderer
        # that drops a mark drops the note with it, and nothing about the page
        # looks wrong afterwards — which is why this is a test and not a
        # docstring.
        alt, men = pg.evaluate("[D.meta.altered, D.meta.mended]")
        check("every correction is reported", alt == men,
              f"{alt} altered, {men} reported")
        # ...which in practice means notes must survive inside a lemma, since
        # that is where the collation does its work.
        nest = pg.evaluate("""D.order.reduce((a,k)=>a+['a','m'].reduce((b,f)=>
          b+[...(D.units[k][f]||'').matchAll(/<span class="q"[^>]*>(.*?)<\\/span>/g)]
            .filter(m=>m[1].includes('sup class="fn"')).length,0),0)""")
        check("footnotes survive inside a lemma", nest > 0, f"{nest} nested")

        # The volume's front matter. The 1848 print opens with Kaspi's own
        # preface and his commentary on the letter, the introduction and the
        # three part-prefaces; an earlier build of this file printed all of it
        # as mislabelled chapters or not at all. The photographed correction
        # the editor sent — החיבורים ההם ר״ל — lives in the letter commentary,
        # so its presence is the one-word proof the front matter is standing.
        fr = pg.evaluate("""['kaspi:0:0','letter:0:0','pref:0:0','intro:1:0',
          'intro:2:0','intro:3:0'].filter(k=>D.units[k]&&D.units[k].a).length""")
        check("front matter is printed", fr == 6, f"{fr}/6 units with text")
        rl = pg.evaluate("""/הח.?בורים ההם/.test(D.units['letter:0:0'].a)""")
        check("the photographed ר״ל passage is printed", bool(rl),
              "החיבורים ההם found in the letter commentary")

        # the binding: hovering a lemma must light its twin in the Guide
        pg.hover("#kaspi .q")
        pg.wait_for_timeout(120)
        hot = pg.eval_on_selector_all(".q.hot", "e=>e.length")
        both = pg.evaluate("()=>{const h=[...document.querySelectorAll('.q.hot')];"
                           "return h.some(e=>e.closest('#kaspi'))&&"
                           "h.some(e=>e.closest('#guide'))}")
        check("lemma lights both sides", hot >= 2 and both, f"{hot} spans hot")

        lemma = pg.eval_on_selector("#kaspi .q", "e=>e.textContent")
        guide = pg.eval_on_selector(".q.hot", "e=>e.closest('#guide')?"
                                    "e.textContent:''") or ""
        check("lemma is verbatim", len(lemma.strip()) >= 12,
              f"{lemma[:40]!r}")

        pg.screenshot(path=f"{shots}/02_lemma_link.png")

        # navigation
        before = pg.inner_text("#here")
        pg.keyboard.press("ArrowLeft")
        pg.wait_for_timeout(200)
        after = pg.inner_text("#here")
        check("keyboard advances chapter", before != after, f"{before} -> {after}")

        # confidence badge is populated and legible
        conf = pg.inner_text("#conf")
        check("evidence badge shown", "ראיות" in conf and "אימות" in conf, conf)
        ocr = pg.inner_text("#ocr")
        check("OCR-quality badge shown", "%" in ocr, ocr)
        nx = pg.eval_on_selector_all("#kaspi u.x", "e=>e.length")
        check("unattested words underlined", nx > 0, f"{nx} words")
        pg.click("#toggles button:last-child")
        pg.wait_for_timeout(120)
        off = pg.eval_on_selector("#kaspi u.x",
                                  "e=>getComputedStyle(e).textDecorationLine")
        check("error marking can be switched off", off == "none", off)
        pg.click("#toggles button:last-child")
        cite = pg.inner_text("#cite")
        check("scan page cited", "דף" in cite, cite)

        # footnotes: the scan of every word the edition still doubts.
        #
        # The numbering is the thing that can be silently wrong. A marker is
        # generated by the painter and its apparatus entry by a later pass over
        # the surviving spans, so a mismatch between them is invisible in the
        # source and catastrophic on the page — every note pointing at the wrong
        # word while looking perfectly well-formed. So the check is not "there
        # are footnotes" but "the sequence of numbers in the text is exactly the
        # sequence in the apparatus", per commentary, and the images decode.
        top = pg.evaluate("D.order.reduce((a,k)=>{const n=D.units[k].n||{};"
                          "const c=(n.a||[]).length+(n.m||[]).length;"
                          "return c>a[1]?[k,c]:a},['',0])")
        if top[1]:
            pg.evaluate(f"location.hash={top[0]!r}")
            pg.wait_for_timeout(250)
            pg.wait_for_function("[...document.images].every(i=>i.complete)",
                                 timeout=20000)
            fn = pg.evaluate("""()=>[...document.querySelectorAll('#kaspi .work')]
              .map(w=>{
                const mark=[...w.querySelectorAll('sup.fn')].map(s=>+s.textContent);
                const app =[...w.querySelectorAll('.notes b')].map(b=>+b.textContent);
                const img =[...w.querySelectorAll('.notes img')];
                return {mark, app, dead: img.filter(i=>!i.naturalWidth).length,
                        wide: Math.max(0,...img.map(i=>i.naturalWidth))};
              })""")
            shown = sum(len(w["mark"]) for w in fn)
            check("doubtful words carry a footnote", shown > 0,
                  f"{shown} in {top[0]}, {top[1]} in the unit")
            check("footnote numbers match their apparatus",
                  all(w["mark"] == w["app"] == list(range(1, len(w["app"]) + 1))
                      for w in fn),
                  " | ".join(f"{w['mark']} vs {w['app']}" for w in fn))
            # How many pictures this unit is *supposed* to show, asked of the
            # payload rather than assumed. The chat build carries the readings
            # and not the ink, so demanding an image here failed a file that
            # was behaving exactly as designed; demanding nothing would let the
            # full edition lose its crops in silence. The payload is the only
            # thing that knows which build this is.
            want = pg.evaluate(f"""(()=>{{const n=D.units[{top[0]!r}].n||{{}};
              return [...(n.a||[]),...(n.m||[])].filter(x=>x[1]).length}})()""")
            check("every footnote image decodes",
                  all(not w["dead"] for w in fn)
                  and bool(want) == any(w["wide"] for w in fn),
                  f"{sum(w['dead'] for w in fn)} dead of {want} expected, "
                  f"widest {max(w['wide'] for w in fn)}px")
            pg.screenshot(path=f"{shots}/06_footnotes.png")
            pg.click("#toggles button:last-child")
            pg.wait_for_timeout(120)
            hid = pg.eval_on_selector("#kaspi sup.fn", "e=>getComputedStyle(e).display")
            check("footnotes hide with the error marking", hid == "none", hid)
            pg.click("#toggles button:last-child")
        else:
            # A build with the crops stripped still carries the markers: they
            # are painted into the commentary, not added at render time. What
            # has to be true is that none of them is shown, because each would
            # be a number referring to an apparatus left behind in the other
            # file.
            k = pg.evaluate("D.order.find(k=>((D.units[k].a||'')+(D.units[k].m||''))"
                            ".includes('class=\"fn\"'))")
            if k:
                pg.evaluate(f"location.hash={k!r}")
                pg.wait_for_timeout(250)
            vis = pg.evaluate("[...document.querySelectorAll('#kaspi sup.fn')]"
                              ".filter(e=>getComputedStyle(e).display!=='none').length")
            check("no dangling footnote markers", vis == 0, f"{vis} shown in {k}")

        # search
        pg.fill("#qbox", "השם")
        pg.press("#qbox", "Enter")
        pg.wait_for_timeout(900)
        hits = pg.eval_on_selector_all("#hits div", "e=>e.length")
        check("search returns hits", hits > 0, f"{hits} shown")
        pg.screenshot(path=f"{shots}/03_search.png")
        pg.evaluate("dlg.close()")

        # about panel
        pg.click("#about")
        pg.wait_for_timeout(250)
        about = pg.inner_text("#dlgbody")
        check("method panel populated", "אבן תיבון" in about and "%" in about,
              f"{len(about)} chars")
        pg.screenshot(path=f"{shots}/04_method.png")
        pg.evaluate("dlg.close()")

        # A chapter Kaspi does not cover must say so, not break. It is the
        # chapter with *neither* commentary that is uncovered: Werbluner prints
        # Maskiyot Kesef on chapters ʿAmudei Kesef passes over — I:73 is
        # fourteen thousand characters of it and no ʿAmudei at all — and a test
        # that looked only at ʿAmudei called the fullest Kaspi page in the
        # volume an empty one.
        gap = pg.evaluate(
            "D.order.find(k=>k.startsWith('ch:')&&!D.units[k].a&&!D.units[k].m)")
        if gap:
            pg.evaluate(f"location.hash={gap!r}")
            pg.wait_for_timeout(200)
            check("uncovered chapter degrades gracefully",
                  "אין פירוש" in pg.inner_text("#kaspi"), gap)

        pg.evaluate("location.hash='ch:1:1'")
        pg.wait_for_timeout(200)
        pg.screenshot(path=f"{shots}/05_chapter_one.png")
        b.close()

    print(f"\n{'ALL CHECKS PASSED' if not fails else 'FAILED: ' + ', '.join(fails)}",
          file=sys.stderr)
    return 1 if fails else 0


if __name__ == "__main__":
    sys.exit(main(*sys.argv[1:]))
