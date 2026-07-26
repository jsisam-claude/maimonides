#!/usr/bin/env python3
"""The same edition, cut down until it fits inside a chat.

`edition.py` writes a 2.3 MB file. That is the right size for a scholarly
artefact meant to be opened in a browser and kept, and the wrong size for a
document that has to be carried into a conversation, where every byte is read.
This module produces the second kind without forking the first: it calls
`edition.build`, removes what a chat-sized copy cannot afford, and renders the
result through the very same page template. There is one edition and one
renderer; only the payload differs.

Three reductions, in order of what they cost the reader.

*The classical witnesses go.* Efodi, Shem Tov, Crescas, Narboni and Abarbanel
are two thirds of the payload, for texts already available everywhere in clean
digital copies. What is unique here is Kaspi, recovered from a scan, and the
Guide he is anchored to. Dropping the five leaves the edition's own
contribution untouched. The page notices the empty witness list and closes that
column rather than showing a blank one; the lexicon that judges OCR quality is
still built from all six, so no measurement changes.

*The scan crops go — the apparatus stays.* Every word the edition still doubts
carries a photograph of its own ink, and those are the one part of the payload
that will not compress: a PNG is already compressed, and base64 then costs a
third again on top, so six hundred kilobytes of them survive gzip almost whole
and would be most of a chat-sized file. They are also the part that loses least
by going. A photograph is evidence a reader consults for one word at a time,
having already decided to doubt it; a conversation is not where that is done,
and the full edition is where it can be.

What the apparatus *says* is a different matter and costs almost nothing. The
reading this edition rejected, and what a word said before it was corrected,
are a few letters each; dropping them to save bytes it was not spending would
leave a text that silently differs from the scan, which is the one thing an
edition may not do. So the chat build asks `edition.build` for the apparatus
without the pictures rather than cutting the pictures out afterwards — the note
numbers are set into the text, and stripping notes downstream would renumber
every mark after each one it removed. Notes reduced to nothing by the loss of
their image are never made in the first place, so the numbering is right by
construction.

*The bytes are folded.* Hebrew in UTF-8 is two bytes a letter, and gzip cannot
undo that: it sees a two-byte pattern where there is one letter of information.
This edition uses well under a hundred distinct non-ASCII characters in all —
twenty-two square letters, five finals, the geresh and gershayim, a handful of
punctuation. Map them into the top of latin-1 first (codes from 0xA0 up, for
the reason given at BASE below) and the compressor sees one byte per letter.
That is not a cleverer algorithm, only a better alphabet, and it is worth
another tenth. The table travels with the file as a `data-map` attribute and
the browser unfolds it in one line.

    full edition, five witnesses          2.34 MB
    Guide + Kaspi                         0.82 MB
    Guide + Kaspi, alphabet folded        0.73 MB

Below that the content itself would have to go, and the file would stop being
the edition. Where a conversation cannot hold 0.73 MB, the answer is not a
smaller edition but a different artefact.

Dependencies: none (Python standard library), and `edition.py` beside it.
"""
from __future__ import annotations

import base64
import gzip
import json
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import edition                                   # noqa: E402

# Where the folded codes start, and how many there is room for. Not 0x80:
# every latin-1 label in the Encoding Standard resolves to windows-1252, which
# is the identity map only from 0xA0 up. Folding into 0x80-0x9F round-trips
# through Python and comes back from the browser as typographic punctuation.
BASE = 0xA0
ROOM = 0x100 - BASE


def reduce(data: dict) -> dict:
    """Drop the classical witnesses; keep the rest entire.

    The crops are already absent — `main` builds without them — so there is
    nothing to strip here but the five commentators, and `meta.notes` counts
    exactly the notes the payload carries.
    """
    out = dict(data)
    out["wit"] = []
    out["units"] = {k: {**u, "w": {}} for k, u in data["units"].items()}
    return out


def pack(text: str) -> tuple[bytes, str]:
    """Fold the text's non-ASCII alphabet into single bytes.

    Returns the latin-1 bytes and the alphabet, in the order the codes were
    assigned, so the browser can read it back. If the text uses more distinct
    characters than there is room for, nothing is folded and the caller falls
    back to UTF-8 — correctness first, then size.
    """
    alphabet = sorted({c for c in text if ord(c) >= 0x80})
    if len(alphabet) > ROOM:
        return text.encode(), ""
    code = {c: chr(BASE + i) for i, c in enumerate(alphabet)}
    return "".join(code.get(c, c) for c in text).encode("latin-1"), "".join(alphabet)


def render(data: dict, fold: bool = True) -> str:
    """The page, with its payload compressed and its alphabet noted."""
    text = json.dumps(data, ensure_ascii=False, separators=(",", ":"))
    raw, alphabet = pack(text) if fold else (text.encode(), "")
    blob = base64.b64encode(gzip.compress(raw, 9)).decode()
    page = edition.PAGE.replace("__DATA__", blob)
    if alphabet:
        page = page.replace('id="data"', 'id="data" data-map="%s"'
                            % edition.esc(alphabet).replace('"', "&quot;"))
    return page


def main() -> None:
    base = os.path.join(os.path.dirname(os.path.abspath(__file__)), "..")
    data = reduce(edition.build(base, crops=False))
    page = render(data)
    dst = os.path.abspath(f"{base}/out/MorehNevukhim_Kaspi_chat.html")
    open(dst, "w", encoding="utf-8").write(page)

    plain = len(render(data, fold=False).encode())
    size = os.path.getsize(dst)
    print(f"units    : {len(data['units'])}, witnesses dropped\n"
          f"folded   : {size/1e6:.2f} MB  (utf-8 would be {plain/1e6:.2f} MB, "
          f"saving {1 - size/plain:.1%})\n"
          f"file     : {dst}", file=sys.stderr)


if __name__ == "__main__":
    main()
