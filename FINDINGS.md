# Kaspi Project — Findings to Date

*A distillation of what has been established, measured, cleared, and built.
This document is the handoff brief: a fresh session that clones
[jsisam-claude/maimonides](https://github.com/jsisam-claude/maimonides) and
reads this file plus README.md can continue every open thread.*

---

## 1. The edition that now exists

A digital critical edition of Joseph ibn Kaspi's two commentaries on the
*Guide of the Perplexed* — **עמודי כסף** (exoteric) and **משכיות כסף**
(esoteric) — established from the only printing ever made (Werbluner,
Frankfurt 1848), which itself was set from the Munich and Leipzig
manuscripts. Neither commentary existed anywhere as a digital text before
this project.

The text was established by *arbitration among four witnesses* of every page
(the scan's text layer, Tesseract at two settings, a human-guided reading of
the ink), judged against a 43,929-form lexicon built from Ibn Tibbon and the
five classical Guide commentators, repaired by a confusion table learned from
21,663 optically witnessed letter pairs, and collated against Ibn Tibbon's
text — which may restore damaged lemmata but may never overwrite sound ink.

**The governing principle, learned the hard way:** an edition may not alter
silently. At one point 425 of 553 machine corrections were applied without
being reported; that number is now **zero**, and it is held by a browser
assertion (`altered === mended`) that runs on every build — a claim about
method enforced as a test, not stated as prose.

| measure | value |
|---|---|
| Guide chapters with commentary recovered | 157 of 178 (+6 front units) |
| chapters with no commentary in the print | 21 (stated, not papered over) |
| verbatim lemma links to Ibn Tibbon | 839 |
| apparatus notes (readings, corrections, variants) | 1,600 |
| corrections — made / reported | 381 / 381 (asserted equal) |
| ink photographs in the apparatus | 512 |
| word accuracy vs. a 2025 manuscript-based edition | 93.1% (its sample region) |
| unattested tokens after repair | 2.9% (clean witnesses score 1.1–3.8%) |
| browser assertions per build | 30, on both builds |

## 2. The structural discoveries

**The front matter had been swallowed.** The volume's opening — Kaspi's own
preface, his commentary on the dedication letter and the Guide's
introduction, and the part-prefaces of Parts II and III (the twenty-five
propositions; the six-fold plan of Part III with its own Maskiyot pass) —
was printed under false chapter labels or glued to neighbouring chapters.
The independent verifier had flagged the false "I:1" (disagree, rank 106)
and the flag went unread. Six front units were recovered by fixed incipits
(`אמר יוסף אבן כספי`) and by *measured quotation seams* — the sentence break
that strands the least verbatim quotation on the wrong side. All verify
rank-1 against their own Guide sections; overall independent agreement rose
from 73% to 86%.

**There is no commentary on Guide III:1–7 (the Merkabah chapters) — by
design.** Page 121 of the print runs from a three-line פרק א directly to
פרק ז. Kaspi states the reason on that page (`שלא ילומד אלא פנים בפנים`)
and directs the material to his Merkabah treatise **מנורת כסף** and the
reserved **אוצר ה׳** (not known to survive). Werbluner's Munich addenda
turned out to be intellect-doctrine pieces for I:70–72, not the missing
chapters. Every absence is now stated explicitly, chapter by chapter, in
every output.

**Commentary–Guide synchrony is measured, not assumed.** Taking each unit's
lemma links in the order the commentary utters them, their anchors in the
Guide are nearly sorted: median in-order (LIS) ratio 0.89 across 116 units,
now a standing assertion (floor 0.8). Tied quotation matches anchor at the
reading position, not the chapter's first occurrence of a repeated formula.

## 3. The Kaspi library assembled (uploads inventory)

| HebrewBooks / file | work | status |
|---|---|---|
| 34446 (1848 Frankfurt) | עמודי כסף + משכיות כסף | **fully ingested** — the edition |
| daat scan (same print) | — | witness for the ensemble |
| 2025 critical edition (sample, 50 pp.) | yardstick only | measurement; in copyright; zero words used |
| 34512 (partial, 23 pp.) | עשרה כלי כסף I — Last's introduction + works catalog | front matter only; catalog useful |
| 34513 (partial, 31 pp.) | עשרה כלי כסף II — front + start of Lamentations | **מנורת כסף NOT inside**; need pp. 75–142 of the full volume |
| 34555 (28 pp., complete) | פירוש הסודות לראב״ע (Oxford MSS) | queued for ingestion |
| 34190 (26 pp., complete) | נקרות כסף (letters and glosses on Kaspi) | queued |
| 26882 (383 pp.) | **אדני כסף I** — Former Prophets + Isaiah, ed. Last (Oxford MS); its preface announces vol. II as separate | queued |
| 9458 (184 pp.) | **משנה כסף I — טירת כסף** (Last 1905) | queued |
| 9459 (338 pp.) | **משנה כסף II — מצרף לכסף** (Last 1906) | queued; Rock's dissertation supersedes it for Genesis |
| 33605 / 33606 | **חצוצרות כסף** — the two Proverbs commentaries (Paris & Munich MSS) | queued |
| 33604 | שיר השירים (Constantinople 1577 text) + קהלת (two Oxford MSS) | queued |
| 33578 | **חגורת כסף** — Ezra, Nehemiah, Chronicles (Oxford MS) | queued |
| 35224 | **שלחן כסף** — Job (Munich Cod. 265) | queued |
| 39632 | **תם הכסף** — the eight discourses (Last, London 1913) | queued |
| Rock 2007 dissertation (360 pp.) | study + critical מצרף לכסף/Genesis | **private research only — in copyright** |

**Still missing, obtainable (public domain, printed):**

1. **מנורת כסף** — עשרה כלי כסף II, pp. 75–142 (full HebrewBooks 34513) — *the original quest*.
2. **אדני כסף II** — Jeremiah, Ezekiel, the Twelve (Last, London 1912; a separate HebrewBooks item).
3. עשרה כלי כסף I body: the two Job commentaries (pp. 133–179, distinct from שלחן כסף) and ספר המוסר (pp. 59–74).
4. עשרה כלי כסף II body: Esther (pp. 29–40) and the complete Ruth + Lamentations (pp. 1–28; the front-slice caught only part).

**Not obtainable as public domain** (manuscripts or modern editions only —
private-research route): גביע כסף (Herring 1982), צרור הכסף (Vatican 283;
the ההטעאה section in Rosenberg 1984), פרשת כסף (Vatican 151),
שרשות/רתוקות כסף. קבוצת כסף, Kaspi's own works-catalog, is already in hand
inside the vol. I front matter.

**Key scholarly finding from Dr. A. Rock's dissertation (Bar-Ilan 2007):**
her census fixes מנורת כסף's address (עשרה כלי כסף II, pp. 75–142), and her
critique of Last — that he emended silently, "ואין המהדיר מיידע את הקורא
לגבי התערבותו" — is precisely the defect this edition eliminated in
Werbluner. Any ingestion of Last's prints must treat the print as a witness
that itself edits its manuscript unreliably.

## 4. Rights, validated

Public availability is not public domain; clearance rests on status:
Kaspi (d. c. 1345) and Ibn Tibbon (d. c. 1230) — public domain everywhere.
The 1848 and 1903–1912 printings — public domain by age. Scans of them —
no new rights in faithful reproductions. The collation source — Sefaria's
Ibn Tibbon, marked Public Domain in its own metadata. The 2025 edition and
the Rock dissertation — **in copyright**: yardstick and research companion
respectively, zero words in the corpus. Our transcription labour — dedicated
CC0. Nothing in the public repo or the Sefaria package is encumbered.

## 5. Assets produced

| asset | purpose |
|---|---|
| `out/MorehNevukhim_KaspiEdition.html` (2.9 MB) | the edition: 3 panes, apparatus, ink photos, method panel |
| `out/MorehNevukhim_Kaspi_chat.html` (0.7 MB) | same text, chat-sized, for reading in artifacts |
| `out/MorehNevukhim_KaspiEdition.pdf` (560 pp.) | the typeset book: Guide in Hadasim above, Kaspi in two Frank Ruehl columns, apparatus with photographs beneath — the layout of the printed tradition |
| `out/study/` (AK/MK markdown + index) | **the analysis format**: plain citable text, sigla per chapter, absences stated — for Claude Projects |
| `out/sefaria/` + zip | contribution package for Sefaria, CC0, with provenance and quality disclosure |
| `out/AmudeiKesef_broken.html`, `_failures.html` | diagnostic reports beside the ink |
| `Makefile` | the stage order, enforced; `make` ends in 30 assertions per build |

## 6. Open threads, in order

1. **מנורת כסף**: obtain full עשרה כלי כסף II (HebrewBooks 34513), pages
   75–142 → machine pass through the existing pipeline → `MnK` study file;
   optionally an edition/PDF section.
2. Ingest the queued texts (אדני כסף; טירת כסף; מצרף לכסף — with Rock as
   private yardstick for Genesis; the Ibn Ezra secrets; נקרות כסף).
3. Werbluner's own Hebrew preface and corrigenda (1848, pp. 3–7) as an
   attributed text.
4. Send the Sefaria package (no self-serve upload; write to their team).
5. The standing security rule: every GitHub token pasted in chat is burned —
   revoke after each push cycle.

*Method in one sentence: four witnesses, one arbitration, every alteration
reported, every claim the edition makes about itself asserted in a browser —
and what the page does not contain, the edition says out loud.*
