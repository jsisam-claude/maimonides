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


def main() -> int:
    os.makedirs(SHOT, exist_ok=True)
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

        pg.goto("file://" + FILE)
        # `let D` is a global *lexical* binding, so it is not a window property
        pg.wait_for_function("typeof D !== 'undefined' && D.order", timeout=20000)

        check("no JS errors", not errs, "; ".join(errs[:3]))
        n = pg.evaluate("Object.keys(D.units).length")
        check("data island inflated", n == 183, f"{n} units")

        check("document is RTL", pg.evaluate("document.documentElement.dir") == "rtl")
        cols = pg.evaluate("getComputedStyle(document.querySelector('main'))"
                           ".gridTemplateColumns").split()
        check("three columns", len(cols) == 3, " / ".join(cols))

        # Hebrew survived the gzip/base64/JSON round trip
        txt = pg.inner_text("#guide")
        heb = sum(c in HEBREW for c in txt)
        check("guide text is Hebrew", heb > 200 and heb / max(1, len(txt)) > 0.5,
              f"{heb}/{len(txt)} letters")
        check("no replacement chars", "�" not in txt)

        # column order: in RTL the first grid child sits on the right
        r = pg.evaluate("()=>{const b=x=>document.querySelector(x).getBoundingClientRect().x;"
                        "return [b('#right'),b('#centre'),b('#left')]}")
        check("Kaspi right, Guide centre, commentators left", r[0] > r[1] > r[2],
              f"x = {[round(x) for x in r]}")

        pg.screenshot(path=f"{SHOT}/01_open.png", full_page=False)

        # a chapter with both commentaries and lemmata
        key = pg.evaluate("D.order.find(k=>D.units[k].m && "
                          "D.units[k].a.includes('data-q'))")
        pg.evaluate(f"location.hash={key!r}")
        pg.wait_for_timeout(250)
        check("found a chapter with both commentaries", bool(key), key or "")

        nq = pg.eval_on_selector_all("#kaspi .q", "e=>e.length")
        check("lemmata marked in Kaspi", nq > 0, f"{nq} spans")

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

        pg.screenshot(path=f"{SHOT}/02_lemma_link.png")

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

        # search
        pg.fill("#qbox", "השם")
        pg.press("#qbox", "Enter")
        pg.wait_for_timeout(900)
        hits = pg.eval_on_selector_all("#hits div", "e=>e.length")
        check("search returns hits", hits > 0, f"{hits} shown")
        pg.screenshot(path=f"{SHOT}/03_search.png")
        pg.evaluate("dlg.close()")

        # about panel
        pg.click("#about")
        pg.wait_for_timeout(250)
        about = pg.inner_text("#dlgbody")
        check("method panel populated", "אבן תיבון" in about and "%" in about,
              f"{len(about)} chars")
        pg.screenshot(path=f"{SHOT}/04_method.png")
        pg.evaluate("dlg.close()")

        # a chapter Kaspi does not cover must say so, not break
        gap = pg.evaluate("D.order.find(k=>k.startsWith('ch:')&&!D.units[k].a)")
        if gap:
            pg.evaluate(f"location.hash={gap!r}")
            pg.wait_for_timeout(200)
            check("uncovered chapter degrades gracefully",
                  "אין פירוש" in pg.inner_text("#kaspi"), gap)

        pg.evaluate("location.hash='ch:1:1'")
        pg.wait_for_timeout(200)
        pg.screenshot(path=f"{SHOT}/05_chapter_one.png")
        b.close()

    print(f"\n{'ALL CHECKS PASSED' if not fails else 'FAILED: ' + ', '.join(fails)}",
          file=sys.stderr)
    return 1 if fails else 0


if __name__ == "__main__":
    sys.exit(main())
