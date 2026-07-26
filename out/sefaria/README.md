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
addenda. 157 Guide chapters carry a commentary; chapters the 1848 print does
not comment on are simply absent.

## How the text was made, and how far to trust it

The print was read by four witnesses (the scan's text layer, Tesseract at two
settings, and a human-guided reading of the ink), arbitrated word by word
against a 43,929-form lexicon built from Ibn Tibbon and the classical Guide
commentators, and repaired using a confusion table learned from 21,663
optically witnessed letter pairs. The 839 lemma quotations were verified
verbatim against Ibn Tibbon's text (Sefaria's own Public Domain version).
Measured against a 2025 manuscript-based critical edition over its sample
region, word accuracy is 93.1%; 2.9% of tokens remain unattested by the
lexicon and should be treated as possible OCR errors. Every one of the 381
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
