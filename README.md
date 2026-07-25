# מורה נבוכים עם עמודי כסף ומשכיות כסף

A digital critical edition of Joseph ibn Kaspi's two commentaries on
Maimonides' *Guide of the Perplexed* — **עמודי כסף** (*ʿAmudei Kesef*) and
**משכיות כסף** (*Maskiyot Kesef*) — set around the Guide itself in the
Miqraot-Gedolot arrangement: the Guide runs down the centre, Kaspi stands on
the right where the eye falls first, and five classical commentators (Efodi,
Shem Tov, Crescas, Narboni, Abarbanel) stand on the left.

The edition is one file, `out/MorehNevukhim_KaspiEdition.html` (2.3 MB). It
opens in any modern browser, fetches nothing, loads no fonts, sets no cookies
and calls no script it does not carry. Everything below describes how the text
inside it was established, and how far it should be trusted.

## Reading it

Open the file. Arrow keys move between chapters (`→` back, `←` forward, since
the page is right-to-left); `/` opens search across the whole volume. The
buttons above the columns turn each witness on and off. Hovering a lemma in
Kaspi lights the same words in the Guide; clicking pins the pair and scrolls
the centre column to it. The badges in the header report, per chapter, the
scan page, the share of word-forms attested in clean Hebrew, and the strength
of the evidence that this commentary belongs to this chapter. `על המהדורה`
opens the method note in Hebrew.

## Where the text comes from

The Guide and the five commentators are Sefaria's open text export, taken from
the public GitHub/GCS release rather than the web API: Samuel ibn Tibbon's
Hebrew of the Guide, and the standard commentaries as Sefaria has them. That
material arrives clean and needs only normalising onto a common citation key,
which `src/corpus.py` does — the epistle, the preface, the three
part-introductions and 178 chapters, 183 addressable units in all.

Kaspi is another matter. Neither commentary exists in a usable digital text,
so the edition is built on the Frankfurt 1848 Werbluner printing, OCR'd here.
`src/preprocess.py` deskews and despeckles each page; `src/ocr_pipeline.py`
reads every line with several engines at once and records where they disagree,
so that a disputed line can be cropped and shown to a human rather than
silently guessed. The result of that stage, `out/AmudeiKesef_hebrewbooks_OCR_raw.txt`,
is committed here because it is the one artefact in the chain that cannot be
regenerated identically; everything downstream is derived from it by the
scripts in `src/`.

## Recovering the structure

The 1848 print marks a new chapter with a Hebrew numeral and a change of type
face. OCR sees the numeral and not the face, and it misreads numerals. So
`src/units.py` decides each unit from four weak signals rather than one strong
one — the numeral (weight 1.0), verbatim overlap with the opening of the
candidate chapter (1.6), the heading shape (0.3), and monotone position in the
volume (0.25) — and accepts an assignment only above 0.8 of a possible 3.15.
It places 153 of the 178 chapters.

That is the matcher's own opinion of its work, which is worth little.
`src/verify.py` therefore re-decides every unit from a signal the matcher never
used: cosine similarity between tf-idf-weighted 4-gram vectors of the *whole*
commentary and the *whole* chapter. Of the 117 units long enough to vote on,
the independent method ranks the same chapter first for 85 (73%) and inside
its top three for 99 (85%). Two methods this unlike each other are unlikely to
fail the same way, so agreement is evidence — not proof, and the edition
prints the verdict per chapter so the reader can see where the two disagree.

Plain containment, for the record, does not work: it rewards long chapters and
maps most of the volume onto Guide I:73, II:29 and III:49. It ranks the true
chapter first for 4% of units against cosine's 73%. The chapter's own norm in
the denominator is what fixes it.

## Recovering the lemmata

Kaspi comments lemma by lemma — a few words of Maimonides, then his remark,
then the next few words — and the 1848 print marks the join only by `וג׳` and
a change of face. The lemmata are nevertheless recoverable, because a lemma is
a *verbatim* quotation: reduce both texts to bare letters, fold final forms,
and take every maximal common substring above a threshold.

The threshold is measured, not guessed. `src/quote.calibrate()` runs each unit
against its own chapter (signal) and against two null models — a chapter drawn
at random, and the *neighbouring* chapter, which is the harder null since
adjacent chapters share vocabulary and Kaspi genuinely cross-refers to them:

| MINLEN | hits | random null | adjacent null |
|-------:|-----:|------------:|--------------:|
| 10 | 842 | 23 | 158 |
| 11 | 639 | 13 | 100 |
| 12 | 499 | 4 | 67 |
| 14 | 333 | 2 | 29 |

Twelve letters is the knee: three quarters more lemmata than fourteen, with a
random-null rate under one per cent. The edition uses twelve and carries 452
two-way links. Those links do double duty — besides binding the two texts,
they restore the paragraphing, since a recovered lemma is exactly where the
1848 compositor started a new sense-unit.

## Flagging the damage

The scan is good but not clean, and the damage is not evenly spread: one
paragraph is flawless and the next carries a line of nonsense from a smudged
forme. `src/ocrqual.py` marks the difference. The test is lexical and the
lexicon costs nothing, because the edition already holds some 3.5 M characters
of clean Hebrew in the same register and century — Ibn Tibbon and the five
commentators — from which it builds 43,456 word-forms. Hebrew particles are
stripped before the lookup fails, final forms are folded, and anything
carrying a Latin letter or a digit is damage by definition.

How specific is that flag? `ocrqual.calibrate()` answers it by holding each
clean witness out of its own lexicon and flagging it as though it were OCR.
Clean fourteenth-century philosophical Hebrew, judged by a lexicon that has
never seen it, scores between 1.1% and 3.8%. The Kaspi OCR scores 24.3%. So
roughly two points of the flag rate are the ordinary novelty of a Hebrew
vocabulary and twenty-two are scanning damage: a word underlined in the
edition is about ten times likelier to be a misreading than a rare form.

`out/ocr_worklist.md` ranks the forty worst units for human adjudication, with
the scan page for each.

## Reproducing

Python 3.11, standard library only, in this order:

    python3 src/corpus.py        # Sefaria export      -> data/corpus.json
    python3 src/units.py         # OCR + corpus        -> data/kaspi_units.json
    python3 src/verify.py        # independent check   -> data/verification.json
    python3 src/edition.py       # everything          -> out/*.html, out/*.md

`src/quote.py` and `src/ocrqual.py` run standalone to print their calibration
tables. The OCR stage (`src/preprocess.py`, `src/ocr_pipeline.py`) needs
Tesseract with the Hebrew models, OpenCV and NumPy; nothing else in the chain
has a dependency at all, and the edition itself has none — the data island is
gzipped JSON in a `<script>` tag, inflated in the browser by the platform
`DecompressionStream` API.

`src/check_edition.py` drives the built file in a headless browser and asserts
twenty things that could silently be wrong — that the data island inflates,
that Hebrew survives the round trip, that the columns are in the right order
for a right-to-left page, that a lemma lights its twin, that navigation and
search work. It needs Playwright, which the edition does not.

## What is still open

Part III stops at chapter 51 in the recovered units; whether 52–54 are absent
from this printing or sit in the addenda is undetermined. The addenda
themselves remain one unsegmented block, because their bracketed rubrics are
set in a face the OCR garbles. Printed folio numbers are not a constant offset
from the PDF page numbers, so the edition cites the scan page rather than the
folio. And twenty-five chapters have no Kaspi at all — the edition says so
rather than pretending otherwise.

## Provenance

Kaspi's commentaries and Ibn Tibbon's translation are long out of copyright.
The Sefaria texts are used under the terms of Sefaria's open export. The
scripts here are original work. Nothing in this repository is a binary blob or
a prebuilt artefact except the OCR raw text and the built edition, both of
which are reproducible from the sources by the commands above.
