# The order the edition has to be built in, written down so that it cannot be
# got wrong twice.
#
# Every stage here reads a file an earlier stage wrote, and nothing in the
# Python says so. Run `repair.py` and forget `units.py` and the edition is
# built from a book that no longer exists: the text is the new one, the chapter
# boundaries are the old one's, and every page citation in the volume is off by
# however much the two disagree. Nothing errors. The file opens. That is what
# happened, and the fix is not to be more careful — it is to write the
# dependencies down where a tool can check them, which is what a Makefile is.
#
# make            build everything that is out of date, then assert it renders
# make check      the browser assertions alone, on both builds
# make gold       score this edition against the 2025 critical edition
# make clean      remove built artefacts, keep the scans and the corpus
#
# The two source PDFs are inputs, not products; override them on the command
# line if they live elsewhere. Dependencies: python3 and, for `check` only,
# playwright.

PY      := python3
UPLOADS := /root/.claude/uploads/ca27e3be-5e31-54b5-a0cd-e849fa507b0e
SCAN    := $(UPLOADS)/3bf68a5d-3Hebrewbooks_org_34446.pdf
GOLDPDF := $(UPLOADS)/44058e4d-________________________________.pdf

D := data
O := out
S := src

.PHONY: all check gold reports pdf clean
.DELETE_ON_ERROR:                 # a half-written JSON must not look current

# The reports are built by `all` and not left to be asked for. They are the two
# files a reader is meant to check the edition against, and a report describing
# a text that has since been re-read is the same stale-artefact failure this
# file exists to prevent, only quieter, because nothing about a report announces
# which run it came from. The PDF is in `all` for the same reason: it is
# typeset from the checked build's own data island, and a book that survives a
# rebuild it was not part of is a book quietly describing the previous text.
all: check reports pdf

# ── the text ─────────────────────────────────────────────────────────────────
# Four readings of the same page, arbitrated word by word, then the quotations
# collated against Ibn Tibbon.
$(D)/ensemble_arbitrated.json: $(S)/ensemble.py $(S)/ocrqual.py \
		$(D)/book_layer.json $(D)/book_tess.json $(D)/book_tess300.json \
		$(D)/book_eyes.json $(D)/corpus.json
	$(PY) $(S)/ensemble.py .

# The repair pass, and the plain-text book that `units.py` cuts up. One command
# writes two files. The grouped-target syntax (`a b &: deps`) says exactly that
# and is the right way to say it, but make 4.3 forgets the second member of the
# group under `-n`: the dry run then shows the repair and stops, hiding the four
# stages that actually follow. A preview that under-reports is worse than none,
# so the second output is instead declared to depend on the first with no recipe
# of its own — the older idiom, correct under `-n`, and true besides: the text
# file is rewritten exactly when the JSON is.
$(D)/ensemble.json: $(S)/repair.py $(D)/ensemble_arbitrated.json
	$(PY) $(S)/repair.py .
$(O)/AmudeiKesef_ensemble_OCR.txt: $(D)/ensemble.json ;

# ── the structure ────────────────────────────────────────────────────────────
$(D)/kaspi_units.json: $(S)/units.py $(O)/AmudeiKesef_ensemble_OCR.txt \
		$(D)/corpus.json
	$(PY) $(S)/units.py $(O)/AmudeiKesef_ensemble_OCR.txt

$(D)/verification.json: $(S)/verify.py $(D)/kaspi_units.json $(D)/corpus.json
	$(PY) $(S)/verify.py

# ── the editions ─────────────────────────────────────────────────────────────
# crops.json is optional — an edition built without it is the same edition with
# its photographs off — so it is an order-only prerequisite: used if present,
# never a reason to fail.
$(O)/MorehNevukhim_KaspiEdition.html: $(S)/edition.py $(S)/quote.py \
		$(D)/ensemble.json $(D)/kaspi_units.json $(D)/verification.json \
		$(D)/corpus.json | $(D)/crops.json
	$(PY) $(S)/edition.py

$(O)/MorehNevukhim_Kaspi_chat.html: $(S)/slim.py \
		$(O)/MorehNevukhim_KaspiEdition.html
	$(PY) $(S)/slim.py

$(D)/crops.json: ;                # cut by hand from the scan; never rebuilt here

# ── the assertions ───────────────────────────────────────────────────────────
# Not a separate step a person may skip. `all` is `check`, so the default build
# is the one that has been driven in a browser and found to work.
check: $(O)/MorehNevukhim_KaspiEdition.html $(O)/MorehNevukhim_Kaspi_chat.html
	$(PY) $(S)/check_edition.py
	$(PY) $(S)/check_edition.py $(O)/MorehNevukhim_Kaspi_chat.html $(O)/shots_chat

# ── the book ─────────────────────────────────────────────────────────────────
# Typeset from the built edition's own data island — same texts, same notes,
# same numbers — so it cannot say anything the checked file does not.
pdf: $(O)/MorehNevukhim_KaspiEdition.pdf
$(O)/MorehNevukhim_KaspiEdition.pdf: $(S)/print.py \
		$(O)/MorehNevukhim_KaspiEdition.html
	$(PY) $(S)/print.py

# ── the measurements ─────────────────────────────────────────────────────────
# Against a 2025 manuscript-based critical edition of the same commentaries.
# It is a yardstick and not a target: this is an edition of the 1848 print, and
# agreeing with a manuscript against the page would be the wrong kind of right.
gold: $(D)/gold_score.json
$(D)/gold_score.json: $(S)/gold.py $(D)/kaspi_units.json $(GOLDPDF)
	$(PY) $(S)/gold.py . "$(GOLDPDF)"

# The two reports for the eye: sentences the edition could not read, and the
# words it still doubts, each beside a photograph of its ink.
reports: $(O)/AmudeiKesef_broken.html $(O)/AmudeiKesef_failures.html
$(O)/AmudeiKesef_broken.html: $(S)/broken.py $(D)/ensemble.json
	$(PY) $(S)/broken.py . "$(SCAN)"
$(O)/AmudeiKesef_failures.html: $(S)/failures.py $(D)/ensemble.json
	$(PY) $(S)/failures.py . "$(SCAN)"

clean:
	rm -f $(D)/ensemble_arbitrated.json $(D)/ensemble.json \
	      $(D)/kaspi_units.json $(D)/verification.json \
	      $(D)/gold.json $(D)/gold_score.json \
	      $(O)/AmudeiKesef_ensemble_OCR.txt \
	      $(O)/MorehNevukhim_KaspiEdition.html \
	      $(O)/MorehNevukhim_Kaspi_chat.html \
	      $(O)/MorehNevukhim_KaspiEdition.pdf
