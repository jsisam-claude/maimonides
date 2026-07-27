#!/usr/bin/env python3
"""One self-contained HTML reader over the raw library, for the artifact shelf.

The markdown files serve analysis; a reader served a 700 kB markdown file is
not reading, they are scrolling. This page is the browsing form of the same
text: every volume behind one dropdown, every scan page an anchored block,
a plain substring search across whichever volume is open, and the volume's
attested-rate banner kept in view — the raw-text warning must travel with
the text it warns about. No dependencies, no network, text embedded plain:
the file is its own archive, and an assistant handed it as context can read
it straight, which the gzip island of the main edition cannot offer.

Dependencies: none (Python standard library; reads out/raw/*.md).
"""
from __future__ import annotations

import glob
import html
import os
import re
import sys

HEAD = re.compile(r"^# (.+)$", re.M)
NOTE = re.compile(r"^> (.*)$", re.M)
PAGE = re.compile(r"^## (דף סריקה \d+)$", re.M)

TEMPLATE = """<!doctype html><html lang="he" dir="rtl"><head><meta charset="utf-8">
<meta name="viewport" content="width=device-width,initial-scale=1">
<title>ספריית כספי — קריאות גולמיות</title><style>
body{font-family:'Frank Ruehl CLM','Taamey Frank CLM',David,serif;margin:0;
 background:#f7f3ea;color:#1e1a16;line-height:1.75}
header{position:sticky;top:0;background:#efe7d6;border-bottom:1px solid #d8cfbd;
 padding:.6rem 1rem;display:flex;gap:.7rem;align-items:center;flex-wrap:wrap}
header b{font-size:1.05rem}
select,input{font:inherit;padding:.25rem .5rem;border:1px solid #c8bda6;
 border-radius:3px;background:#fdfbf6;max-width:46vw}
main{max-width:52rem;margin:0 auto;padding:1rem 1.2rem 4rem}
.note{font-size:.85rem;background:#f3e9d2;border:1px solid #decfae;
 border-radius:4px;padding:.6rem .9rem;margin:.8rem 0}
h3{border-bottom:1px dotted #c8bda6;padding-bottom:.15rem;margin:1.6rem 0 .5rem;
 font-size:.95rem;color:#6b5d43}
p{margin:.35rem 0;text-align:justify}
mark{background:#f3e2b8}
.hide{display:none}
footer{font-size:.8rem;color:#8a7f6c;text-align:center;padding:2rem 0}
</style></head><body>
<header><b>ספריית כספי — קריאות גולמיות</b>
<select id="vol" onchange="show(this.value)">%OPTIONS%</select>
<input id="q" placeholder="חיפוש בכרך הפתוח…" oninput="find(this.value)">
<span id="hits" style="font-size:.85rem;color:#6b5d43"></span></header>
<main>%SECTIONS%</main>
<footer>נחלץ משכבות ה־OCR של הסריקות · טקסט גולמי, לא מבוקר ·
github.com/jsisam-claude/maimonides</footer>
<script>
const $=s=>document.querySelector(s),$$=s=>[...document.querySelectorAll(s)];
function show(id){$$('section').forEach(s=>s.classList.toggle('hide',s.id!==id));
 $('#q').value='';find('');window.scrollTo(0,0)}
function find(q){const sec=$('section:not(.hide)');let n=0;
 for(const p of sec.querySelectorAll('p,h3')){
  const t=p.textContent;
  if(!q||q.length<2){p.style.display='';p.innerHTML=p.innerHTML.replace(/<\\/?mark>/g,'');continue}
  const hit=t.includes(q);p.style.display=hit||p.tagName==='H3'?'':'none';
  if(hit&&p.tagName==='P'){n++;
   p.innerHTML=t.split(q).map(x=>x.replace(/&/g,'&amp;').replace(/</g,'&lt;'))
     .join('<mark>'+q.replace(/&/g,'&amp;').replace(/</g,'&lt;')+'</mark>')}}
 $('#hits').textContent=q&&q.length>=2?n+' פסקאות':''}
show($('#vol').value);
</script></body></html>"""


def main() -> None:
    base = sys.argv[1] if len(sys.argv) > 1 else "."
    opts, secs = [], []
    files = sorted(glob.glob(f"{base}/out/raw/*.md"))
    files = [f for f in files if not f.endswith("index.md")]
    for i, f in enumerate(files):
        txt = open(f, encoding="utf-8").read()
        title = HEAD.search(txt).group(1)
        note = " ".join(m.group(1) for m in NOTE.finditer(txt))
        sid = os.path.basename(f)[:-3]
        opts.append('<option value="%s">%s</option>' % (sid, html.escape(title)))
        body = ['<section id="%s"%s><h2>%s</h2><div class="note">%s</div>'
                % (sid, "" if i == 0 else ' class="hide"',
                   html.escape(title), html.escape(note))]
        chunks = PAGE.split(txt)
        for k in range(1, len(chunks) - 1, 2):
            body.append("<h3>%s</h3>" % html.escape(chunks[k]))
            for para in chunks[k + 1].split("\n\n"):
                para = para.strip()
                if para and not para.startswith(("#", ">")):
                    body.append("<p>%s</p>"
                                % html.escape(para).replace("\n", "<br>"))
        body.append("</section>")
        secs.append("".join(body))
    out = TEMPLATE.replace("%OPTIONS%", "".join(opts)) \
                  .replace("%SECTIONS%", "\n".join(secs))
    dst = f"{base}/out/KaspiRawLibrary.html"
    open(dst, "w", encoding="utf-8").write(out)
    print(f"html: {dst}  {os.path.getsize(dst)//1048576} MB "
          f"({len(files)} volumes)", file=sys.stderr)


if __name__ == "__main__":
    main()
