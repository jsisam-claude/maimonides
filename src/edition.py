#!/usr/bin/env python3
"""Assemble the edition: the Guide at the centre, its commentators around it.

This is the *Miqraot Gedolot* arrangement applied to the ``Moreh Nevukhim``.
The base text (Ibn Tibbon's Hebrew, held verbatim from Sefaria) runs down the
middle; Kaspi's two commentaries — recovered from the 1848 Werbluner print by
src/units.py — stand to its right, where a Hebrew reader's eye lands first;
the five classical commentators stand to its left.

Three things are done here that a plain transcription cannot do:

*Lemmatisation.* The 1848 print marks Kaspi's lemmata only by a change of
face, which OCR cannot see. src/quote.py recovers them as maximal verbatim
runs shared with Ibn Tibbon; this module turns each recovered lemma into a
paragraph break, restoring the lemma/comment rhythm the typography carried.

*Binding.* Every lemma is also located in the Guide, so a lemma and the words
it quotes are two ends of one link: touch either and both light up. Kaspi's
remark is therefore anchored to a position in the base text, not merely to a
chapter.

*Confidence, shown.* Each unit carries the matcher's score, the route it was
found by, the verdict of the independent validator (src/verify.py) and the
share of its words that any Hebrew text attests (src/ocrqual.py). None of it
is hidden: unattested words are underlined where they stand, so the reader
sees the damage rather than being told about it in a preface.

Output is one self-contained HTML file with no network access and no external
assets. The corpus (~7 MB of JSON) is gzipped and base64'd into a data island
and inflated in the browser by ``DecompressionStream`` — a platform API, so
the zero-dependency rule holds on both sides.

Dependencies: none (Python standard library).
"""
from __future__ import annotations

import base64
import gzip
import json
import os
import re
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import ocrqual                                  # noqa: E402
import quote                                    # noqa: E402
import units as U                               # noqa: E402

MAXSCORE = U.W_NUM + U.W_LEM + U.W_HEAD + U.W_INIT

WITNESSES = [("efodi", "אפודי"), ("shemtov", "שם טוב"), ("crescas", "קרשקש"),
             ("narboni", "נרבוני"), ("abarbanel", "אברבנאל")]

PART_NAME = {1: "חלק ראשון", 2: "חלק שני", 3: "חלק שלישי"}
FRONT = [("letter:0:0", "אגרת המחבר לר׳ יוסף בן יהודה", 0),
         ("pref:0:0", "פתיחה", 0),
         ("intro:1:0", "הקדמה — סיבות הסתירה", 1),
         ("intro:2:0", "הקדמה לחלק שני — כ״ה ההקדמות", 2),
         ("intro:3:0", "הקדמה לחלק שלישי", 3)]
PART_LEN = {1: 76, 2: 48, 3: 54}

WS = re.compile(r"[ \t]+")


# ── text → HTML ───────────────────────────────────────────────────────────────

def esc(s: str) -> str:
    return s.replace("&", "&amp;").replace("<", "&lt;").replace(">", "&gt;")


# A span is (start, end, kind, qid). Kinds: "q" = quotation of the base text,
# "x" = word attested nowhere in the clean corpus. A quotation is verbatim
# Ibn Tibbon, so it cannot be OCR damage: where the two collide, "q" wins.
PRIORITY = {"q": 0, "x": 1}
Span = tuple


def resolve(spans: list[Span]) -> list[Span]:
    """Drop overlaps, lower-priority first, and return in reading order."""
    keep: list[Span] = []
    for sp in sorted(spans, key=lambda s: (PRIORITY[s[2]], s[0])):
        if any(sp[0] < e and s < sp[1] for s, e, _, _ in keep):
            continue
        keep.append(sp)
    keep.sort()
    return keep


def paint(text: str, spans: list[Span]) -> str:
    """Escape *text*, wrapping each resolved span in its mark-up."""
    out, prev = [], 0
    for s, e, kind, q in spans:
        out.append(esc(text[prev:s]))
        body = esc(text[s:e])
        out.append('<span class="q" data-q="%d">%s</span>' % (q, body)
                   if kind == "q" else '<u class="x">%s</u>' % body)
        prev = e
    out.append(esc(text[prev:]))
    return "".join(out)


def pair(comment: str, base: str) -> list[tuple[tuple[int, int], tuple[int, int]]]:
    """Quotation pairs, longest first, kept only where both sides are free.

    quote.quotations already returns disjoint spans on the commentary side,
    but a stock phrase can land twice in the chapter. Resolving greedily by
    length keeps the pairing a bijection, which is what the two-way highlight
    depends on.
    """
    cs, bs = quote.quotations(comment, base)
    keep: list[tuple[tuple[int, int], tuple[int, int]]] = []
    for c, b in sorted(zip(cs, bs), key=lambda t: t[0][0] - t[0][1]):
        if any(c[0] < e and s < c[1] for (s, e), _ in keep):
            continue
        if any(b[0] < e and s < b[1] for _, (s, e) in keep):
            continue
        keep.append((c, b))
    keep.sort(key=lambda t: t[0][0])
    return keep


def clip(text: str, spans: list[Span]) -> list[Span]:
    """Split spans at newlines so none straddles a paragraph."""
    out = []
    for s, e, kind, q in spans:
        a = s
        while True:
            nl = text.find("\n", a, e)
            if nl < 0:
                if a < e:
                    out.append((a, e, kind, q))
                break
            if a < nl:
                out.append((a, nl, kind, q))
            a = nl + 1
    return out


def paragraphs(text: str, spans: list[Span]) -> str:
    """Paint *text*, then break it into <p> at every newline."""
    html = paint(text, resolve(clip(text, spans)))
    return "".join("<p>%s</p>" % p for p in html.split("\n") if p.strip())


def lemmatised(text: str, spans: list[Span]) -> str:
    """Paint a commentary, starting a new paragraph at each lemma."""
    if not text.strip():
        return ""
    spans = resolve(spans)
    cuts = sorted({0, len(text)} | {s for s, _, k, _ in spans if k == "q"})
    out = []
    for a, b in zip(cuts, cuts[1:]):
        inner = [(s - a, e - a, k, q) for s, e, k, q in spans if a <= s and e <= b]
        chunk = paint(text[a:b], inner).strip()
        if chunk:
            out.append("<p>%s</p>" % chunk)
    return "".join(out)


def plain(segments: list[str]) -> str:
    return "".join("<p>%s</p>" % esc(WS.sub(" ", s).strip())
                   for s in segments if s and s.strip())


# ── assembly ─────────────────────────────────────────────────────────────────

def order() -> list[str]:
    keys = ["letter:0:0", "pref:0:0"]
    for p in (1, 2, 3):
        keys.append("intro:%d:0" % p)
        keys += ["ch:%d:%d" % (p, c) for c in range(1, PART_LEN[p] + 1)]
    return keys


def gershayim(n: int) -> str:
    """Hebrew numeral as it is set in print: ב׳, ט״ו, ע״ו."""
    s = U.numeral(n)
    return s + "׳" if len(s) == 1 else s[:-1] + "״" + s[-1]


def label(key: str) -> str:
    for k, lab, _ in FRONT:
        if k == key:
            return lab
    _, p, c = key.split(":")
    return "%s · פרק %s" % (PART_NAME[int(p)], gershayim(int(c)))


def build(base: str) -> dict:
    corpus = json.load(open(f"{base}/data/corpus.json", encoding="utf-8"))
    kaspi = json.load(open(f"{base}/data/kaspi_units.json", encoding="utf-8"))
    verify = json.load(open(f"{base}/data/verification.json", encoding="utf-8"))

    kby = {u["unit"]: u for u in kaspi["units"]}
    vby = {r["unit"]: r for r in verify["rows"]}
    moreh = corpus["moreh"]

    lex = ocrqual.lexicon(*(" ".join(sum(w.values(), [])) for w in corpus.values()))

    units, quoted, flagged, tokens = {}, 0, 0, 0
    for key in order():
        segs = moreh.get(key) or []
        gtext = "\n".join(WS.sub(" ", s).strip() for s in segs)
        rec: dict = {"g": "", "a": "", "m": "", "w": {}}

        u = kby.get(key)
        if u:
            gspans: list[Span] = []
            qid, bad, tot = 0, 0, 0
            for field in ("amudei", "maskiyot"):
                txt = WS.sub(" ", u[field]).strip()
                spans: list[Span] = []
                for (cs, ce), (bs, be) in pair(txt, gtext):
                    qid += 1
                    spans.append((cs, ce, "q", qid))
                    gspans.append((bs, be, "q", qid))
                sus, b, t = ocrqual.suspects(txt, lex)
                bad, tot = bad + b, tot + t
                spans += [(s, e, "x", 0) for s, e in sus]
                rec[field[0]] = lemmatised(txt, spans)
            quoted += qid
            flagged, tokens = flagged + bad, tokens + tot
            rec["g"] = paragraphs(gtext, gspans)
            rec["p"] = u["page"]
            rec["s"] = u["score"]
            rec["r"] = u["via"]
            rec["o"] = round(1.0 - bad / tot, 3) if tot else None
            v = vby.get(key, {})
            rec["v"] = v.get("verdict")
            rec["vr"] = v.get("rank")
            rec["va"] = v.get("argmax")
        else:
            rec["g"] = plain(segs)

        for wid, _ in WITNESSES:
            seg = corpus[wid].get(key)
            if seg:
                rec["w"][wid] = plain(seg)
        units[key] = rec

    add = [{"label": a.get("label") or "הוספות המגיה מכ״י מינכן",
            "page": a.get("page"),
            "html": plain(re.split(r"\n{2,}", a["text"]))}
           for a in kaspi.get("addenda", [])]

    have = {u["unit"] for u in kaspi["units"]}
    missing = {p: [c for c in range(1, PART_LEN[p] + 1)
                   if "ch:%d:%d" % (p, c) not in have] for p in (1, 2, 3)}

    return {
        "order": order(),
        "labels": {k: label(k) for k in order()},
        "units": units,
        "addenda": add,
        "wit": WITNESSES,
        "meta": {
            "matched": len(kaspi["units"]), "total": sum(PART_LEN.values()),
            "coverage": kaspi["coverage"], "quotes": quoted,
            "anchors": kaspi["part_anchors"], "missing": missing,
            "verify": verify["summary"], "maxscore": round(MAXSCORE, 2),
            "lexicon": len(lex), "flagged": flagged, "tokens": tokens,
            "minlen": quote.MINLEN,
        },
    }


def worklist(data: dict, dst: str, n: int = 40) -> None:
    """The units a human should adjudicate first, worst OCR at the top."""
    rows = [(k, u) for k, u in data["units"].items() if u.get("o") is not None]
    rows.sort(key=lambda t: (t[1]["o"], -(t[1].get("s") or 0)))
    m = data["meta"]
    out = [
        "# Adjudication worklist",
        "",
        "Units ranked by the share of word-forms that no clean Hebrew text in the",
        f"corpus attests ({m['lexicon']:,} forms). A low figure means the scan, the OCR,",
        "or both need a human eye. Consult the scan page given in the last column;",
        "the same page numbers index `out/AmudeiKesef_hebrewbooks_OCR_raw.txt`.",
        "",
        f"Across the {m['matched']} recovered units, {m['flagged']:,} of {m['tokens']:,} tokens "
        f"({m['flagged']/max(1,m['tokens']):.1%}) are unattested.",
        "",
        "| # | chapter | attested | evidence | validator | scan page |",
        "|--:|---------|---------:|---------:|-----------|----------:|",
    ]
    verdict = {"agree": "agrees", "near": "top-3", "disagree": "dissents",
               "short": "too short", None: "—"}
    for i, (k, u) in enumerate(rows[:n], 1):
        out.append("| %d | %s | %.0f%% | %.2f/%.2f | %s | %s |"
                   % (i, data["labels"][k], 100 * u["o"], u["s"], MAXSCORE,
                      verdict.get(u.get("v"), "—"), u["p"]))
    open(dst, "w", encoding="utf-8").write("\n".join(out) + "\n")


# ── page ─────────────────────────────────────────────────────────────────────

PAGE = r"""<!doctype html>
<html lang="he" dir="rtl"><head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width,initial-scale=1">
<title>מורה נבוכים עם עמודי כסף ומשכיות כסף</title>
<style>
:root{
  --paper:#f7f3ea; --ink:#1e1a16; --rule:#d8cfbd; --dim:#8a7f6c;
  --hot:#c8531f; --lemma:#8a5a12; --mark:#f3e2b8; --pane:#fdfbf6;
}
*{box-sizing:border-box}
html,body{margin:0;height:100%}
body{
  background:var(--paper); color:var(--ink);
  font-family:"Frank Ruehl CLM","Taamey Frank CLM","David CLM","Noto Serif Hebrew",
              "Times New Roman",serif;
  font-size:17px; line-height:1.75;
  display:flex; flex-direction:column;
}
header{border-bottom:1px solid var(--rule);background:var(--pane);flex:0 0 auto}
.bar{display:flex;align-items:center;gap:.75rem;padding:.4rem .9rem;flex-wrap:wrap}
.bar+.bar{border-top:1px solid #e9e2d3}
h1{font-size:1.05rem;margin:0;font-weight:600;letter-spacing:.01em}
h1 small{color:var(--dim);font-weight:400;font-size:.8em;margin-inline-start:.5rem}
button,select,input{font:inherit;color:inherit;background:transparent;
  border:1px solid var(--rule);border-radius:3px;padding:.1rem .5rem;cursor:pointer}
button:hover{background:#efe8d8}
button[aria-pressed=true]{background:var(--ink);color:var(--paper);border-color:var(--ink)}
input{cursor:text;min-width:11rem}
.grow{flex:1}
#chips{display:flex;gap:.2rem;overflow-x:auto;padding:.35rem .9rem;scrollbar-width:thin}
#chips b{font-weight:600;color:var(--dim);padding:0 .35rem;align-self:center;
  font-size:.8rem;white-space:nowrap}
.chip{border:1px solid transparent;border-radius:3px;padding:.05rem .38rem;
  font-size:.85rem;min-width:1.9rem;text-align:center;color:var(--dim)}
.chip.has{color:var(--ink);border-color:var(--rule);background:#fff}
.chip.on{background:var(--ink);color:var(--paper);border-color:var(--ink)}

main{flex:1;min-height:0;display:grid;grid-template-columns:1fr 1.25fr 1fr;gap:0}
.pane{overflow:auto;padding:1.1rem 1.4rem 4rem;border-inline-start:1px solid var(--rule)}
.pane:first-child{border:0}
#centre{background:var(--pane)}
.pane h2{position:sticky;top:-1.1rem;margin:-1.1rem -1.4rem 1rem;
  padding:.45rem 1.4rem;background:inherit;border-bottom:1px solid var(--rule);
  font-size:.82rem;font-weight:600;letter-spacing:.06em;color:var(--dim);
  text-transform:none;z-index:2}
#right{background:var(--paper)} #left{background:var(--paper)}
h3{font-size:.8rem;letter-spacing:.05em;color:var(--dim);margin:1.6rem 0 .3rem;
  border-bottom:1px dotted var(--rule);padding-bottom:.15rem;font-weight:600}
h3:first-of-type{margin-top:0}
p{margin:0 0 .55rem;text-align:justify;text-justify:inter-word}
#centre p{font-size:1.06rem;line-height:1.95}
.work p{font-size:.95rem;line-height:1.7}
.work{margin-bottom:1.2rem}
.q{border-bottom:1px solid #d9c48d;cursor:pointer}
#right .q,#centre .q{color:var(--lemma)}
.q.hot{background:var(--mark);border-bottom-color:var(--hot);color:var(--hot)}
mark{background:var(--mark);color:inherit}
u.x{text-decoration:underline wavy #c0392b8c;text-underline-offset:.22em;
    text-decoration-thickness:1px}
body.clean u.x{text-decoration:none}

.badge{font-size:.72rem;border:1px solid var(--rule);border-radius:2rem;
  padding:.02rem .5rem;color:var(--dim);white-space:nowrap}
.badge.agree{border-color:#5d7a4a;color:#456034}
.badge.near{border-color:#b08a2a;color:#8a6a12}
.badge.disagree{border-color:#a8412a;color:#8d3320}
.empty{color:var(--dim);font-style:italic;font-size:.9rem}

dialog{border:1px solid var(--rule);background:var(--pane);color:var(--ink);
  max-width:44rem;padding:1.4rem 1.7rem;line-height:1.8;border-radius:3px}
dialog::backdrop{background:#1e1a1666}
dialog h4{margin:1.1rem 0 .3rem;font-size:.95rem}
dialog h4:first-child{margin-top:0}
dialog p{font-size:.95rem}
#hits{max-height:60vh;overflow:auto}
#hits div{padding:.35rem 0;border-bottom:1px dotted var(--rule);cursor:pointer;font-size:.9rem}
#hits div:hover{background:#efe8d8}
#hits i{color:var(--dim);font-style:normal;font-size:.8rem;margin-inline-start:.4rem}
@media (max-width:1100px){main{grid-template-columns:1fr}
  .pane{height:auto;overflow:visible;border-inline-start:0;border-top:1px solid var(--rule)}
  body{height:auto;display:block} main{display:block}}
@media print{
  body{height:auto;display:block;background:#fff}
  header,#chips,.noprint{display:none}
  main{display:grid;grid-template-columns:1fr 1.3fr 1fr}
  .pane{overflow:visible;height:auto}
  .q{border:0;color:inherit} .q.hot{background:none}
}
</style></head><body>
<header>
 <div class="bar">
  <h1>מורה נבוכים <small>עם עמודי כסף ומשכיות כסף לר׳ יוסף אבן כספי</small></h1>
  <span class="grow"></span>
  <span id="cite" class="badge"></span>
  <span id="ocr" class="badge"></span>
  <span id="conf" class="badge"></span>
  <input id="qbox" placeholder="חיפוש בכל הכרך…">
  <button id="about">על המהדורה</button>
 </div>
 <div class="bar">
  <button id="prev">→ הקודם</button><button id="next">הבא ←</button>
  <span id="here" style="font-weight:600"></span>
  <span class="grow"></span>
  <span id="toggles"></span>
 </div>
 <div id="chips"></div>
</header>
<main>
 <section class="pane" id="right"><h2>ר׳ יוסף אבן כספי</h2><div id="kaspi"></div></section>
 <section class="pane" id="centre"><h2>מורה נבוכים — תרגום ר׳ שמואל אבן תיבון</h2><div id="guide"></div></section>
 <section class="pane" id="left"><h2>מפרשים</h2><div id="wit"></div></section>
</main>
<dialog id="dlg"><div id="dlgbody"></div>
 <p style="margin-top:1.2rem"><button onclick="dlg.close()">סגירה</button></p></dialog>
<script type="application/octet-stream" id="data">__DATA__</script>
<script>
const $=(s,r=document)=>r.querySelector(s), $$=(s,r=document)=>[...r.querySelectorAll(s)];
let D, cur, hidden=new Set(), pin=null, idx=null;

(async()=>{
  const b64=$('#data').textContent.trim();
  let json;
  try{
    const bin=Uint8Array.from(atob(b64),c=>c.charCodeAt(0));
    json=await new Response(new Blob([bin]).stream()
          .pipeThrough(new DecompressionStream('gzip'))).text();
  }catch(e){
    document.body.innerHTML='<p style="padding:2rem">הדפדפן אינו תומך ב־DecompressionStream.</p>';
    return;
  }
  D=JSON.parse(json);
  chips(); toggles();
  show(location.hash.slice(1)||'ch:1:1');
  addEventListener('hashchange',()=>show(location.hash.slice(1)));
})();

function chips(){
  const c=$('#chips');
  const add=(txt,key,cls)=>{const b=document.createElement('button');
    b.className='chip '+cls; b.textContent=txt; b.dataset.k=key;
    b.onclick=()=>location.hash=key; c.append(b); };
  const grp=t=>{const b=document.createElement('b'); b.textContent=t; c.append(b)};
  grp('פתיחה');
  for(const k of D.order) if(!k.startsWith('ch:')&&!k.startsWith('intro'))
    add(D.labels[k].split(' ')[0],k,has(k));
  for(const p of [1,2,3]){
    grp(['','א','ב','ג'][p]);
    add('הק׳','intro:'+p+':0',has('intro:'+p+':0'));
    for(const k of D.order.filter(k=>k.startsWith('ch:'+p+':')))
      add(k.split(':')[2],k,has(k));
  }
}
const has=k=>D.units[k]&&D.units[k].a?'has':'';

function toggles(){
  const t=$('#toggles');
  const mk=(id,name)=>{const b=document.createElement('button');
    b.textContent=name; b.setAttribute('aria-pressed','true');
    b.onclick=()=>{hidden.has(id)?hidden.delete(id):hidden.add(id);
      b.setAttribute('aria-pressed',String(!hidden.has(id))); render()};
    t.append(b)};
  mk('amudei','עמודי כסף'); mk('maskiyot','משכיות כסף');
  for(const [id,name] of D.wit) mk(id,name);
  const b=document.createElement('button');
  b.textContent='סימון שגיאות'; b.setAttribute('aria-pressed','true');
  b.onclick=()=>{document.body.classList.toggle('clean');
    b.setAttribute('aria-pressed',String(!document.body.classList.contains('clean')))};
  t.append(b);
}

function show(k){
  if(!D.units[k]) k='ch:1:1';
  cur=k; pin=null;
  $('#here').textContent=D.labels[k];
  $$('.chip').forEach(c=>c.classList.toggle('on',c.dataset.k===k));
  const on=$('.chip.on'); if(on) on.scrollIntoView({inline:'center',block:'nearest'});
  render();
  $$('.pane').forEach(p=>p.scrollTop=0);
  if(location.hash.slice(1)!==k) history.replaceState(null,'',' #'+k);
}

function render(){
  const u=D.units[cur];
  $('#guide').innerHTML=u.g||'<p class="empty">—</p>';
  let h='';
  if(u.a&&!hidden.has('amudei'))  h+='<div class="work"><h3>עמודי כסף</h3>'+u.a+'</div>';
  if(u.m&&!hidden.has('maskiyot'))h+='<div class="work"><h3>משכיות כסף</h3>'+u.m+'</div>';
  $('#kaspi').innerHTML=h||'<p class="empty">אין פירוש כספי לפרק זה בדפוס פרנקפורט תר״ח.</p>';
  let w='';
  for(const [id,name] of D.wit) if(u.w[id]&&!hidden.has(id))
    w+='<div class="work"><h3>'+name+'</h3>'+u.w[id]+'</div>';
  $('#wit').innerHTML=w||'<p class="empty">—</p>';

  $('#cite').textContent=u.p?('פרנקפורט תר״ח, דף '+u.p):'—';
  const o=$('#ocr');
  o.textContent=u.o==null?'':('מלים מאושרות '+Math.round(u.o*100)+'%');
  o.className='badge '+(u.o==null?'':u.o>=.9?'agree':u.o>=.8?'near':'disagree');
  o.style.display=u.o==null?'none':'';
  const c=$('#conf');
  if(u.s){ c.className='badge '+(u.v||''); c.textContent=
    'ראיות '+u.s.toFixed(2)+'/'+D.meta.maxscore+
    ' · '+({heading:'כותרת',lemma:'ציטוט'}[u.r]||u.r)+
    ' · '+({agree:'אימות מסכים',near:'אימות קרוב',disagree:'אימות חולק',
            short:'קצר מדי לאימות'}[u.v]||'ללא אימות');
  } else { c.className='badge'; c.textContent='טקסט בסיס בלבד'; }

  for(const s of $$('.q')){
    s.onmouseenter=()=>light(s.dataset.q,true);
    s.onmouseleave=()=>{if(!pin) light(s.dataset.q,false)};
    s.onclick=()=>{ if(pin) light(pin,false);
      pin=(pin===s.dataset.q)?null:s.dataset.q;
      if(pin){light(pin,true);
        const t=$$('#guide .q').find(x=>x.dataset.q===pin);
        if(t) t.scrollIntoView({block:'center',behavior:'smooth'});}};
  }
}
const light=(q,on)=>$$('.q[data-q="'+q+'"]').forEach(e=>e.classList.toggle('hot',on));

const step=d=>{const i=D.order.indexOf(cur); const j=i+d;
  if(j>=0&&j<D.order.length) location.hash=D.order[j]};
$('#prev').onclick=()=>step(-1); $('#next').onclick=()=>step(1);
addEventListener('keydown',e=>{
  if(e.target.tagName==='INPUT'){ if(e.key==='Escape') e.target.blur(); return }
  if(e.key==='ArrowRight') step(-1);
  else if(e.key==='ArrowLeft') step(1);
  else if(e.key==='/'){e.preventDefault(); $('#qbox').focus()}
});

/* search: index built once, on demand, from the rendered strings */
const strip=h=>h.replace(/<[^>]*>/g,' ').replace(/[֑-ׇ]/g,'')
                 .replace(/[׳״'"׳״]/g,'');
const fold=s=>s.replace(/ך/g,'כ').replace(/ם/g,'מ').replace(/ן/g,'נ')
               .replace(/ף/g,'פ').replace(/ץ/g,'צ');
function index(){
  if(idx) return idx;
  idx=[];
  for(const k of D.order){ const u=D.units[k];
    const put=(w,h)=>{ if(h) idx.push([k,w,fold(strip(h))]) };
    put('מורה',u.g); put('עמודי כסף',u.a); put('משכיות כסף',u.m);
    for(const [id,name] of D.wit) put(name,u.w[id]);
  }
  return idx;
}
$('#qbox').addEventListener('keydown',e=>{ if(e.key!=='Enter') return;
  const q=fold(strip(e.target.value)).trim(); if(q.length<2) return;
  const hits=[];
  for(const [k,w,t] of index()){
    let i=t.indexOf(q);
    while(i>=0&&hits.length<400){
      hits.push([k,w,t.slice(Math.max(0,i-45),i+q.length+45)]);
      i=t.indexOf(q,i+q.length);
    }
  }
  const body=$('#dlgbody');
  body.innerHTML='<h4>‏'+hits.length+' תוצאות עבור «'+q+'»</h4><div id="hits"></div>';
  const box=$('#hits');
  for(const [k,w,s] of hits.slice(0,300)){
    const d=document.createElement('div');
    d.innerHTML=s.replace(q,'<mark>'+q+'</mark>')+'<i>'+D.labels[k]+' · '+w+'</i>';
    d.onclick=()=>{location.hash=k; dlg.close()};
    box.append(d);
  }
  dlg.showModal();
});

$('#about').onclick=()=>{
  const m=D.meta, v=m.verify;
  const miss=[1,2,3].map(p=>'חלק '+['','א','ב','ג'][p]+': '+
      (m.missing[p].length?m.missing[p].join(', '):'—')).join('<br>');
  $('#dlgbody').innerHTML=`
  <h4>מה יש כאן</h4>
  <p>טקסט המורה — תרגום ר׳ שמואל אבן תיבון, לפי מהדורת ספריא (רשות הרבים).
  פירושי ר׳ יוסף אבן כספי — <i>עמודי כסף</i> ו<i>משכיות כסף</i> — הוצאו בזיהוי
  תווים מדפוס ש״ז ווערבלונר, פרנקפורט תר״ח (1848), והושבו למקומם בספר המורה
  בדרך אלגוריתמית. אפודי, שם טוב, קרשקש, נרבוני ואברבנאל — ספריא.</p>
  <h4>איך שוחזר המבנה</h4>
  <p>הדפוס אינו מסמן את הפרקים אלא בכותרת רצה בגוף השורה, ולעתים קרובות
  אינו מסמן כלל. לכל אחד ממאה שבעים ושמונה פרקי המורה נבנתה &quot;תבנית&quot;:
  מספר הפרק באותיות, ופתיחת הפרק לפי אבן תיבון. כל מועמד בסריקה נמדד מול
  התבניות בשני אותות בלתי־תלויים — דמיון לוונשטיין משוקלל לשגיאות זיהוי
  אופייניות (ד/ר, ב/כ, ה/ח/ת), וחפיפת מחרוזות־שלוש בין הסביבה לפתיחה — ותכנות
  דינמי מונוטוני בחר את ההשמה הכוללת הטובה ביותר. נמצאו
  ${m.matched} מתוך ${m.total} פרקים (${Math.round(m.coverage*100)}%).</p>
  <h4>איך נבדק</h4>
  <p>בדיקה עצמאית השוותה כל יחידה שהתקבלה אל כל פרקי המורה בעזרת מדד קוסינוס
  על מחרוזות־ארבע משוקללות ב־idf — אות שהמנוע הראשון לא ראה כלל.
  ${v.agree} מתוך ${v.scored} (${Math.round(v.agree_rate*100)}%) קיבלו את אותה
  התשובה במקום הראשון, ${Math.round(v.top3_rate*100)}% בשלושת הראשונים;
  ${v.short} יחידות קצרות מכדי להצביע. התווית שבראש העמוד מציגה את פסק הבדיקה
  לפרק הנוכחי — אין כאן הסתרה של אי־ודאות.</p>
  <h4>הלמות</h4>
  <p>הדפוס מבחין בין דברי המורה לדברי כספי בשינוי אות בלבד, וזיהוי התווים אינו
  רואה זאת. הלמות שוחזרו כאן כמחרוזות משותפות מרביות (${m.minlen} אותיות ומעלה)
  בין הפירוש ובין פרק אבן תיבון; ${m.quotes} כאלה נמצאו. הסף אינו משוער אלא
  נמדד: כל יחידה הורצה גם מול פרק אקראי וגם מול הפרק הסמוך, והסף נבחר במקום
  שבו הרעש יורד מתחת לאחוז. כל למה פותחת פסקה בפירוש ומקושרת למקומה בטקסט —
  מעבר עכבר מדליק את שני הצדדים, הקשה מקבעת וגוללת אל המקום במורה.</p>
  <h4>איפה הזיהוי נכשל</h4>
  <p>מילון של ${m.lexicon.toLocaleString('he')} צורות מילים נבנה מן הטקסטים
  הנקיים שבכרך עצמו — אבן תיבון וחמשת המפרשים — והוא באותו רובד לשון ובאותה
  כתיב שבו כתב כספי. כל מלה בפירוש שאינה מאושרת בו (גם לאחר קילוף מוקדמות
  וה־בכלמ״ש) מסומנת בקו גלי במקומה: ${m.flagged.toLocaleString('he')} מתוך
  ${m.tokens.toLocaleString('he')} (${(100*m.flagged/m.tokens).toFixed(1)}%).
  אין כאן תיקון אלא הצבעה — הקורא רואה את הפגם ולא רק שומע עליו. אפשר לכבות
  את הסימון בכפתור «סימון שגיאות».</p>
  <p>גם המדד הזה נבדק: כשמוציאים מפרש שלם מן המילון ומעבירים את הטקסט הנקי שלו
  באותה בדיקה, שיעור הסימון הוא 1.1%–3.8% בלבד. כלומר כשתי נקודות אחוז הן
  חידוש לשוני רגיל, וכעשרים ושתיים הן פגם סריקה — מלה מסומנת כאן היא בקירוב
  פי עשרה יותר טעות זיהוי מאשר צורה נדירה.</p>
  <h4>פרקים שלא נמצאו בדפוס</h4>
  <p style="font-size:.88rem">${miss}</p>
  <h4>מקלדת</h4>
  <p>← הפרק הבא · → הפרק הקודם · / חיפוש</p>`;
  dlg.showModal();
};
</script></body></html>
"""


def main() -> None:
    base = os.path.join(os.path.dirname(os.path.abspath(__file__)), "..")
    data = build(base)
    raw = json.dumps(data, ensure_ascii=False, separators=(",", ":")).encode()
    blob = base64.b64encode(gzip.compress(raw, 9)).decode()
    dst = os.path.abspath(f"{base}/out/MorehNevukhim_KaspiEdition.html")
    open(dst, "w", encoding="utf-8").write(PAGE.replace("__DATA__", blob))
    work = os.path.abspath(f"{base}/out/ocr_worklist.md")
    worklist(data, work)

    m = data["meta"]
    print(f"units      : {len(data['units'])} ({m['matched']}/{m['total']} with Kaspi)",
          file=sys.stderr)
    print(f"lemmata    : {m['quotes']} quotation links "
          f"(MINLEN={m['minlen']})", file=sys.stderr)
    print(f"lexicon    : {m['lexicon']:,} word-forms; "
          f"{m['flagged']:,}/{m['tokens']:,} tokens unattested "
          f"({m['flagged']/max(1,m['tokens']):.1%})", file=sys.stderr)
    print(f"payload    : {len(raw)/1e6:.2f} MB json -> {len(blob)/1e6:.2f} MB base64",
          file=sys.stderr)
    print(f"file       : {dst} ({os.path.getsize(dst)/1e6:.2f} MB)", file=sys.stderr)
    print(f"worklist   : {work}", file=sys.stderr)


if __name__ == "__main__":
    main()
