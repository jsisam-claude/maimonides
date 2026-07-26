#!/usr/bin/env python3
"""Decide the text from three disagreeing readings of the same page.

No single reading of this scan is worth adopting on its own. The Hebrewbooks
layer is automatic OCR by an unnamed engine; `heb_best --psm 4` at 600 dpi and
`heb --psm 6` at 300 dpi are automatic OCR by a known one, at different
resolutions and under different assumptions about the page; all three are wrong
about roughly one word in seven, and none announces which. What makes them
useful together is that they are wrong in *different places*: systems that
share no code, no training data or no segmentation strategy do not fail on the
same ligature.

Two readings can only ever say *whether* they agree. Three can say which of
them is outvoted, and that is a different and much more useful thing. The case
that forced it: at the head of Part II chapter 41 the publisher's layer reads
‏פלה מא‎ and Tesseract reads ‏פרק מב‎ — a chapter heading. Both readings are
Hebrew words, so a lexicon cannot separate them, and a two-way rule that keeps
the better reading on aggregate keeps ‏פלה‎ and the heading is gone: not one
word wrong but a whole unit of the edition lost, silently. A third reader
breaks it, and the majority is right.

Four tests decide the text, in descending order of how much they are worth:

*The Guide itself.* Kaspi comments lemma by lemma, and a lemma is a verbatim
quotation from a text this edition already holds in a clean digital copy. Where
the 1848 compositor marked a quotation in display type — which `book.py` reads
straight off the page geometry — the correct reading is not a matter of opinion
at all. It can be restored from Ibn Tibbon, and it is then *known*, not guessed.
This is collation, not recognition, and it is the only step here that produces
certainty.

*Agreement.* Every reading that saw a word at this place returning the same
string is strong evidence, and it is what most of the page consists of.

*Majority.* Two of the three against one. Weaker than unanimity — one reader
did see something else — but it is a vote by readers that fail independently,
and it is right far more often than any rule about which reader to trust.

*Attestation.* Where all three differ, prefer the reading that is a Hebrew
word. The lexicon is the 43,456 forms of the clean witnesses; it is not a spell
checker and it does not correct anything, it only breaks ties. Where several
candidates are attested the earliest reading is kept and the place is flagged;
where none is, the place is flagged harder, and those are the lines that go to
a human with the image beside them.

Every word carries the reason it is there. That is the point: an edition that
cannot say why it reads what it reads is not a critical edition.

One thing besides the words has to survive this pass: the line breaks. Where a
line of type ends is evidence — the compositor sets a part banner on a line of
its own, and a chapter heading at the head of a line, and the structural pass
downstream reads both. Arbitration works on word sequences and would flatten a
page to a single line, silently destroying that evidence. So the layer's line
geometry is carried through the alignment: every layer word appears exactly
once in the output, so the word that opened a line still can be identified, and
the transcript is written out with its lines intact.

Dependencies: none. Standard library only.
"""
from __future__ import annotations

import json
import os
import re
import sys
from dataclasses import dataclass

import ocrqual

LETTERS = re.compile(r"[א-ת]+")
GAP = -1          # cost of an unmatched word
MATCH = 2         # reward for identical folded forms
NEAR = 1          # reward for forms one edit apart
MISS = -1         # cost of aligning two unrelated words
BAND = 24         # words; alignment never strays further than this from the diagonal
MAXWELD = 5       # backbone fragments one lost space can scatter a word into

AGREE, GUIDE, MOST, SEEN, LEX, KEEP, DOUBT, FIX = (
    "agree", "guide", "most", "seen", "lex", "keep", "doubt", "fix")
REASONS = (GUIDE, AGREE, MOST, SEEN, LEX, FIX, KEEP, DOUBT)

# How often each instrument is right, in the order the measurement puts them:
# read by eye off the scan leaves 3.2 % of its word-forms unattested, the
# publisher's layer 14.7 %, Tesseract 19.8 % — one test, applied identically to
# all three, in `measure.py`. Where the evidence separates candidates this
# ordering is irrelevant and unused; every rule below reaches it only after
# unanimity, majority and attestation have all failed to decide. But something
# has to choose then, and what chose before was list position, which meant the
# layer won every open question by accident of being written first. Preferring
# the reading that is measurably right most often is not a decree about which
# witness to trust — it is the one answer the evidence does support to a
# question the evidence cannot settle.
RANK = {"eye": 0, "layer": 1, "tesseract": 2}


@dataclass
class Token:
    text: str
    why: str          # which test put this word here
    nl: bool = False  # ...and did it open a line of type on the page
    at: int | None = None
    # ^ and which word of the backbone it is — the layer's own tokenisation,
    #   which is the only reading of this book that carries coordinates. A
    #   token that no reader but one saw was inserted between two backbone
    #   words and belongs to no ink the layer measured, so it carries None.
    #
    #   This exists because the alternative is to recover the correspondence
    #   afterwards by aligning the finished text back against the backbone, and
    #   that alignment is a guess. Measured over the words this edition still
    #   doubts, it put one crop in twenty on the wrong word — showing a reader
    #   the ink of a *neighbouring* word beside the transcription, which is not
    #   a smaller error than a bad transcription but a larger one, because it
    #   looks like evidence. The correspondence is known exactly at the moment
    #   the token is made; carrying it costs one integer and no reasoning.
    alt: tuple[tuple[str, str], ...] = ()
    # ^ the readings that lost here, each with the instrument that gave it.
    #   An edition that arbitrates and then throws the losers away asks to be
    #   taken on trust: the reader can see that a word was doubted but not what
    #   the doubt was between, which is the one thing an apparatus exists to
    #   show. They are known at the moment the vote is counted and nowhere
    #   afterwards — recovering them later would mean re-aligning four readings
    #   against a text that has since been repaired, and that alignment is the
    #   same guess the coordinate above exists to avoid making.
    was: str = ""
    # ^ ...and what this token said before a later pass changed it. Empty when
    #   nothing did, so the field is itself the record of the correction and no
    #   second list has to be kept in step with the text.

    @property
    def sure(self) -> bool:
        return self.why in (GUIDE, AGREE)


def bare(w: str) -> str:
    """A word reduced to what two OCR engines could agree about."""
    return "".join(LETTERS.findall(ocrqual.fold(w)))


def ok(word: str, lex: set[str]) -> bool:
    """Is this token, as printed, a Hebrew word?

    `ocrqual.attested` judges one bare folded form; a token off the page still
    carries its punctuation, and may be two words joined by a maqaf. Judge it
    the same way `ocrqual.suspects` does, so that every figure quoted about
    this edition is the same measurement.
    """
    if ocrqual.FOREIGN.search(word) or ocrqual.pieces(word):
        return False
    runs = ocrqual.WORD.findall(ocrqual.NIQQUD.sub("", word))
    return bool(runs) and all(ocrqual.attested(ocrqual.fold(r), lex) for r in runs)


def weld(lines: list[str],
         reads: list[list[str]]) -> tuple[list[str], list[list[int]]]:
    """Put back the spaces the backbone's own OCR invented.

    The publisher's text layer is itself machine-read, and where the letters of
    a word sit loosely it returns them as several tokens — ‏להרבות‎ as ‏ל ה רבו
    ת‎, ‏הקשים‎ as ‏ה ק שי ם‎, ‏עמודי‎ as ‏עמ ודי‎. Nothing downstream can undo
    this. The aligner is matching whole words, so four fragments cannot pair
    with the one word the other readers saw; the vote never gets to compare
    them, and the arbitration emits the fragments *and* the word — ``ל ה רבו ת
    להרבות`` — which is the one failure mode of this edition that a reader
    notices without knowing any Hebrew. It runs to 1,550 places in the volume,
    2.15 % of the backbone.

    The repair asks for character-identical evidence and nothing weaker. A run
    of backbone tokens is welded when its letters, concatenated, are exactly a
    token some other reader of the same page read whole, and when no other
    reader put a space anywhere inside the run. No lexicon is consulted: the
    letters do not change, only a space the readers disagree about, and the
    disagreement is settled by the readers who were looking at the ink rather
    than by a corpus of other authors. That is the lesson of the split rule,
    which fabricated 275 spaces while a lexicon told it they were plausible;
    here the evidence is outside the word, and it is exact.

    Welding is done inside a line, never across one, so the line structure the
    volume's layout is partly written in survives untouched.

    Returned with the lines is the grouping: for each welded token, which words
    of the original backbone went into it. The backbone is the only reading of
    this volume that carries coordinates, and every crop in the edition is a box
    looked up by backbone position, so a pass that renumbers the backbone and
    keeps the renumbering to itself silently points every footnote at the wrong
    word. The grouping is that renumbering, handed to whoever needs it, computed
    once here rather than reconstructed by each caller from the same evidence.
    """
    whole = {bare(w) for r in reads for w in r}
    seam = {(bare(a), bare(b)) for r in reads for a, b in zip(r, r[1:])}
    out, group, base = [], [], 0
    for line in lines:
        toks, new, i = line.split(), [], 0
        while i < len(toks):
            run = 1
            for j in range(min(i + MAXWELD, len(toks)), i + 1, -1):
                part = [bare(t) for t in toks[i:j]]
                if all(part) and "".join(part) in whole and not any(
                        p in seam for p in zip(part, part[1:])):
                    run = j - i
                    break
            new.append("".join(toks[i:i + run]) if run > 1 else toks[i])
            group.append(list(range(base + i, base + i + run)))
            i += run
        out.append(" ".join(new))
        base += len(toks)
    return out, group


def _near(a: str, b: str) -> bool:
    """True if *a* and *b* differ by one substitution, or one inserted letter."""
    if abs(len(a) - len(b)) > 1:
        return False
    if len(a) == len(b):
        return sum(x != y for x, y in zip(a, b)) == 1
    lo, hi = (a, b) if len(a) < len(b) else (b, a)
    for i in range(len(hi)):
        if hi[:i] + hi[i + 1:] == lo:
            return True
    return False


def align(a: list[str], b: list[str]) -> list[tuple[int | None, int | None]]:
    """Pair up two readings of the same line of type.

    Needleman-Wunsch on the reduced forms, restricted to a band around the
    diagonal — two readings of one page never drift further apart than a few
    words, and the band turns a quadratic into something linear enough to run
    over a book.
    """
    n, m = len(a), len(b)
    fa, fb = [bare(x) for x in a], [bare(x) for x in b]
    wide = max(BAND, abs(n - m) + 2)

    def cols(i):
        return range(max(0, i - wide), min(m, i + wide) + 1)

    score = {(0, 0): 0}
    back: dict[tuple[int, int], tuple[int, int]] = {}
    for i in range(n + 1):
        for j in cols(i):
            if i == j == 0:
                continue
            best, whence = None, None
            if i and j and (i - 1, j - 1) in score:
                s = MATCH if fa[i - 1] == fb[j - 1] else (
                    NEAR if _near(fa[i - 1], fb[j - 1]) else MISS)
                best, whence = score[(i - 1, j - 1)] + s, (i - 1, j - 1)
            if i and (i - 1, j) in score and (best is None or score[(i - 1, j)] + GAP > best):
                best, whence = score[(i - 1, j)] + GAP, (i - 1, j)
            if j and (i, j - 1) in score and (best is None or score[(i, j - 1)] + GAP > best):
                best, whence = score[(i, j - 1)] + GAP, (i, j - 1)
            if best is not None:
                score[(i, j)], back[(i, j)] = best, whence

    out, at = [], (n, m)
    while at != (0, 0):
        pi, pj = back[at]
        out.append((pi if pi < at[0] else None, pj if pj < at[1] else None))
        at = (pi, pj)
    return out[::-1]


def against(base: list[str], other: list[str]) -> tuple[dict, dict]:
    """One other reading, expressed against the backbone.

    Returns what *other* has at each position of *base*, and what it has that
    *base* has nowhere — the second keyed by the base position the extra words
    arrive before, so that several readings' insertions can be compared with
    each other before any of them is believed.
    """
    at: dict[int, str] = {}
    extra: dict[int, list[str]] = {}
    pending: list[str] = []
    for i, j in align(base, other):
        if i is None:
            pending.append(other[j])
            continue
        if pending:
            extra[i], pending = pending, []
        if j is not None:
            at[i] = other[j]
    if pending:
        extra[len(base)] = pending
    return at, extra


def vote(words: list[str], by: list[str] | None = None) -> list[str]:
    """The largest group of readings that say the same thing.

    *by* names the instrument behind each reading. Counting readings rather
    than instruments is what let two settings of one OCR engine out-vote every
    other witness; counting instruments makes a majority mean what it says.
    """
    tally: dict[str, list[str]] = {}
    weight: dict[str, set[str]] = {}
    for i, w in enumerate(words):
        k = bare(w)
        tally.setdefault(k, []).append(w)
        weight.setdefault(k, set()).add(by[i] if by else str(i))
    return max(tally.values(), key=lambda ws: len(weight[bare(ws[0])]))


# Letters of the square alphabet that differ by a single stroke, and that the
# machine readers therefore confuse with each other: ‏ד‎ has the roof projecting
# past its leg that ‏ר‎ rounds away; ‏ב‎ has the foot that ‏כ‎ lacks; ‏ה‎ leaves
# its left leg free where ‏ח‎ joins it to the roof and ‏ת‎ kicks it out into a
# foot; ‏ז‎ is ‏ו‎ with a shoulder to the left, ‏י‎ is ‏ו‎ cut short, ‏ן‎ is ‏ו‎
# with a tail; ‏ג‎ is ‏נ‎ with a foot; ‏ס‎ is ‏מ‎ with the corner rounded. Forms
# are compared folded, so the finals are already their medial letters.
#
# The table is morphology, not statistics. It was written from the shapes and
# then checked against the volume, where the ranked confusions between the eye
# and the machines are ‏ד‎/‏ר‎ 949 times, ‏ב‎/‏כ‎ 237, ‏ה‎/‏ח‎ 99, ‏ח‎/‏ת‎ 64,
# ‏ו‎/‏ז‎ 54, ‏מ‎/‏ס‎ 47 — every frequent one already here. Deriving it from those
# counts instead would have been fitting the arbitration to the corpus it
# arbitrates. Seven of the ten are witnessed independently a third time, in the
# confusion table `repair.py` learns from the lemmata the Guide restores, where
# what was printed is known rather than inferred.
SHAPE = frozenset(("דר", "בכ", "הח", "הת", "חת", "וז", "וי", "ונ", "גנ", "מס"))


def stroke(a: str, b: str) -> bool:
    """Do two forms differ only where the alphabet differs by one stroke?"""
    return (len(a) == len(b) and a != b
            and all(x == y or x + y in SHAPE or y + x in SHAPE
                    for x, y in zip(a, b)))


def decide(cand: list[str | None], lex: set[str],
           by: list[str] | None = None) -> tuple[str, str]:
    """The word, and the test that put it there.

    The order of the tests is the whole argument. Counting votes first looks
    obvious and is wrong here: two of the three readings are Tesseract at
    different settings, and two settings of one engine are not two witnesses —
    they fail on the same ligature, so an unweighted majority quietly hands
    every disagreement to Tesseract and discards the publisher's layer, which
    is the better single reading. Measured over the book that costs three and a
    half points of accuracy.

    So attestation comes first and the vote breaks ties inside it: a reading
    that is a Hebrew word beats one that is not however many settings produced
    it, and the vote decides only among readings that are all equally possible.

    *by* carries the same argument into the vote itself. With the eye reading
    added there are four readings but three instruments, and a majority that
    counts readings would still hand the disagreement to Tesseract twice over.
    Grouping by instrument is the difference between a fourth witness and a
    fourth vote for the engine that already had two.

    Grouping by instrument is still not enough where the difference is one
    stroke. ‏דוד‎ and ‏דור‎ are both Hebrew words, so attestation cannot separate
    them, and the layer and Tesseract both read the ink as ‏דור‎ — not because
    two witnesses saw a resh but because a dalet whose roof has faded is a resh
    to anything that recognises letters by their shape. Counting that as two
    instruments against the one reader that can see is counting the same failure
    twice. Over the volume the eye contradicts a unanimous machine consensus at
    2,184 positions; at the 823 of them the lexicon can judge, the eye's form is
    the Hebrew word and the machines' is not 96 % of the time.

    So a machine consensus that differs from the eye by stroke-confusable
    letters alone does not carry. The restriction to those letters is what keeps
    this from being a blanket override: a reader who knows Hebrew is exactly the
    reader who might quietly improve a word he cannot make out, and the eye is
    allowed to win only where the machines are known to be blind rather than
    wherever it disagrees. Attestation still comes first — an eye reading that
    is not a word loses to a machine reading that is.

    And every rule here ends, if nothing else has decided, in "take the first".
    Sorting the readings by RANK before any of them runs is what turns that
    last clause from an accident into a decision — see RANK for why the order
    is a measurement rather than an opinion.
    """
    keep = [i for i, w in enumerate(cand) if w is not None]
    seen = [cand[i] for i in keep]
    src = [by[i] for i in keep] if by else [str(i) for i in keep]
    if len({bare(w) for w in seen}) == 1 and len(seen) > 1:
        return seen[0], AGREE                   # every reader that saw a word
    order = sorted(range(len(seen)), key=lambda k: RANK.get(src[k], len(RANK)))
    seen = [seen[k] for k in order]
    src = [src[k] for k in order]
    good = [w for w in seen if ok(w, lex)]
    gsrc = [s for w, s in zip(seen, src) if ok(w, lex)]
    top = vote(good, gsrc) if good else vote(seen, src)
    look = next((w for w, s in zip(seen, src) if s == "eye"), None)
    if (look is not None and stroke(bare(look), bare(top[0]))
            and (ok(look, lex) or not good)):
        return look, SEEN
    if len(top) > 1:
        return top[0], MOST                     # ...or most of the plausible ones
    if len(good) == 1:
        return good[0], LEX
    if good:
        return good[0], KEEP                    # several plausible; earliest wins
    return seen[0], DOUBT


def losers(cand: list[str | None], by: list[str] | None,
           won: str) -> tuple[tuple[str, str], ...]:
    """The readings this position rejected, each credited to one instrument.

    Compared on bare forms, so that a reader who differs only in a final letter
    or a comma is not reported as having read a different word: the apparatus
    is for disagreements about what is on the page, and an edition that files
    ‏האדם‎ against ‏האדם,‎ as a variant has buried its real variants in noise.

    First instrument to give a reading keeps it. `decide` has already sorted by
    RANK when it chose, and crediting a reading to the best-ranked reader that
    returned it is the same convention, applied to the ones that lost.
    """
    out: dict[str, str] = {}
    for w, s in zip(cand, by or ()):
        if w is not None and bare(w) != bare(won):
            out.setdefault(w, s)
    return tuple(out.items())


def arbitrate(base: list[str], others: list[list[str]], lex: set[str],
              opens: frozenset[int] = frozenset(),
              by: list[str] | None = None) -> list[Token]:
    """One reading of the page from several, with a reason on every word.

    The first reading is the backbone: the others are aligned to it and voted
    against it, position by position. That is not a claim that it is the best
    reading — it is the one with page geometry behind it, and *opens* holds the
    indices at which its lines begin. The winning word may come from any
    reader, but where the line broke is a fact about the page rather than about
    any of them, so it travels with the backbone.
    """
    reads = [against(base, o) for o in others]
    rank = [RANK.get(s, len(RANK)) for s in (by[1:] if by else [])]
    rank += [len(RANK)] * (len(reads) - len(rank))
    out = []
    for i in range(len(base) + 1):
        # Words some reader has and the backbone does not. A chapter heading
        # the layer dropped altogether arrives here, so these are kept even on
        # a single vote — but two readers inserting the same word is worth
        # recording, and it must not be inserted twice.
        adds = [extra.get(i, []) for _, extra in reads]
        if any(adds):
            # Take one reader's insertion whole, in its own order — word order
            # is evidence too, and merging two readers' insertions by matching
            # forms would scramble it. Whose: the best-ranked reader's, length
            # deciding only between equals, and *including when it is empty*.
            # Taking the longest outright, as this did while every reader was a
            # machine, is what walked the scanning watermark into the text —
            # ‏ינטרנט‎, ‏008.08‎, a library stamp — because Tesseract reads
            # furniture off the margin and a reader with nothing to say here
            # could not outvote seven words of it. Silence from a reader that
            # read this page is a reading: it says there is nothing there. A
            # word another reader also inserted is corroborated; the rest stand
            # on one vote.
            best = adds[min(range(len(adds)),
                            key=lambda t: (rank[t], -len(adds[t])))]
            seconded = {bare(w) for ws in adds if ws is not best for w in ws}
            out.extend(Token(w, MOST if bare(w) in seconded
                             else LEX if ok(w, lex) else DOUBT) for w in best)
        if i == len(base):
            break
        cand = [base[i]] + [at.get(i) for at, _ in reads]
        word, why = decide(cand, lex, by)
        out.append(Token(word, why, i in opens, i, losers(cand, by, word)))
    return out


class Source:
    """The Guide, indexed once so that quotations of it can be found quickly.

    Two things make the difference between a pass that runs over a book and one
    that does not.

    *Fold once.* `bare` is a regular expression and a table lookup per word.
    Called from inside the extension loop it is evaluated millions of times on
    the same few hundred thousand words; called once per word at construction it
    is evaluated a quarter of a million times in total.

    *Seed on pairs.* The Guide is a quarter of a million words and its commonest
    form occurs in several thousand of them. Seeding a candidate run on a single
    word means every ``את`` in the commentary opens thousands of runs, none of
    which survive — the cost is the product of two word-frequency distributions,
    which for Hebrew function words is enormous. A pair is specific enough that
    a seed is almost always either the quotation or nothing. Since a restored
    run must be at least four words long, nothing that would have been restored
    is lost by requiring its first two words to match.
    """

    __slots__ = ("words", "fold", "index")

    def __init__(self, text: str):
        self.words = text.split()
        self.fold = [bare(w) for w in self.words]
        self.index: dict[tuple[str, str], list[int]] = {}
        for k in range(len(self.fold) - 1):
            self.index.setdefault((self.fold[k], self.fold[k + 1]), []).append(k)


def restore(tokens: list[Token], source: Source, lex: set[str],
            minrun: int = 4, log: list | None = None) -> tuple[int, int]:
    """Collate the quotations against the Guide; mend only what is broken.

    Kaspi's lemmata are Ibn Tibbon. Where a run of the page's words matches a
    run of the Guide closely enough to be that quotation and not a coincidence,
    the Guide is a second witness to what the ink must say — and what an
    edition may do with a second witness is narrower than it first looks.

    Where the page's reading is not a Hebrew word at all, the Guide supplies
    it: the ink is damaged, the true word is known, and the substitution is an
    emendation, reported like every other. Where the page reads soundly and
    still differs, it is not damage. It is Kaspi quoting the manuscript he had,
    or the Frankfurt compositor setting ‏המושאלים‎ where the text on Sefaria
    spells ‏המשאלים‎, and replacing it prints another edition's words under this
    edition's lemma. Those differences are recorded as rejected readings with
    the Guide as their witness — the first entries in this apparatus that are
    about transmission rather than about legibility.

    An earlier version substituted throughout the run. It rewrote 461 sound
    words to agree with Sefaria and reported none of them, and among them it
    turned ‏ר״ל‎ — Kaspi's constant *that is to say* — into ‏אל‎, which is how
    the error a reader photographed for us was printed in the first place.

    An emendation is also a fact about the scanner: read *this*, meant *that*,
    on this ink. Passed a *log*, the pass records those pairs. It no longer
    records the sound ones. They were never evidence about a scanner, and being
    twenty-three of every twenty-five, they were very nearly all the confusion
    table downstream had ever been told — see `repair.witnessed`.

    Returns (emended, collated).
    """
    src, sf, index = source.words, source.fold, source.index
    tf = [bare(t.text) for t in tokens]

    fixed, kept, i, end = 0, 0, 0, len(tokens)
    while i < end:
        seeds = index.get((tf[i], tf[i + 1]), ()) if i + 1 < end else ()
        best = (0, -1)
        for k in seeds:
            n = 2
            while (i + n < end and k + n < len(src)
                   and (tf[i + n] == sf[k + n] or _near(tf[i + n], sf[k + n]))):
                n += 1
            if n > best[0]:
                best = (n, k)
        if best[0] >= minrun:
            n, k = best
            # A pair seed cannot start on a damaged second word, so a quotation
            # whose second word the scanner mangled is found from its third
            # word on. Walk back from the seed under the same near-match rule
            # and the opening words come back: what the index could not find,
            # the match itself can reach.
            while (i and k and tokens[i - 1].why != GUIDE
                   and (tf[i - 1] == sf[k - 1] or _near(tf[i - 1], sf[k - 1]))):
                i, k, n = i - 1, k - 1, n + 1
            for d in range(n):
                # The word is inside a citation either way, so `why` is GUIDE
                # either way; what changes is whose reading is printed. The page
                # still supplies the line it was set on, the ink it was set in,
                # and — where the edition altered it — the reading it was
                # altered from, which is the reader's only evidence that
                # anything happened here at all.
                old = tokens[i + d]
                if tf[i + d] == sf[k + d]:
                    tokens[i + d] = Token(src[k + d], GUIDE, old.nl, old.at,
                                          old.alt, old.was)
                elif ok(old.text, lex):
                    kept += 1
                    tokens[i + d] = Token(old.text, GUIDE, old.nl, old.at,
                                          old.alt + ((src[k + d], GUIDE),),
                                          old.was)
                    continue                      # the page keeps its word
                else:
                    fixed += 1
                    if log is not None:
                        log.append([tf[i + d], sf[k + d]])
                    tokens[i + d] = Token(src[k + d], GUIDE, old.nl, old.at,
                                          old.alt, old.text)
                tf[i + d] = sf[k + d]
            i += n
        else:
            i += 1
    return fixed, kept


def report(tokens: list[Token], lex: set[str]) -> dict:
    n = len(tokens)
    why = {k: sum(1 for t in tokens if t.why == k) for k in REASONS}
    bad = sum(1 for t in tokens if not ok(t.text, lex))
    return {"words": n, **why, "unattested": bad,
            "rate": bad / n if n else 0.0,
            "sure": sum(1 for t in tokens if t.sure) / n if n else 0.0}


def lexicon(corpus: dict) -> set[str]:
    """Every word-form the clean witnesses use, as a tie-breaker."""
    return ocrqual.lexicon(*(p for w in corpus.values()
                             for ps in w.values() for p in ps))


def reading(path: str) -> dict[int, str]:
    """One zone-split Tesseract pass, keyed by page.

    A missing pass is not fatal. The ensemble is better with three readings and
    correct with two, and an edition that cannot be rebuilt without every
    intermediate file is a fragile one.
    """
    try:
        data = json.load(open(path, encoding="utf-8"))
    except FileNotFoundError:
        print(f"  (no {os.path.basename(path)}; arbitrating without it)",
              file=sys.stderr)
        return {}
    return {d["page"]: d.get("body") or "" for d in data}


def run(base: str = ".") -> dict:
    corpus = json.load(open(f"{base}/data/corpus.json", encoding="utf-8"))
    lex = lexicon(corpus)
    pages = json.load(open(f"{base}/data/book_layer.json", encoding="utf-8"))["pages"]
    # Reading, and the instrument behind it. The backbone is the layer; the two
    # Tesseract passes are one engine at two settings and vote as one; the eye
    # reading is a third instrument, entered here as a peer and nothing more.
    WITNESS = [("book_tess.json", "tesseract"),
               ("book_tess300.json", "tesseract"),
               ("book_eyes.json", "eye")]
    other = [(reading(f"{base}/data/{f}"), src) for f, src in WITNESS]
    guide = Source(" ".join(p for ps in corpus["moreh"].values() for p in ps))

    out, fixed, collated, damage = [], 0, 0, []
    for n, p in enumerate(pages, 1):
        if n % 25 == 0:
            print(f"  ...{n}/{len(pages)} pages", file=sys.stderr, flush=True)
        got = [(t.get(p["page"], "").split(), src) for t, src in other]
        # Before anything is aligned, undo the backbone's own broken words —
        # the aligner cannot match four fragments to one word, so this has to
        # happen while the other readers' whole words are still evidence.
        lines, group = weld([t for t, _ in p["body"]], [w for w, _ in got if w])
        opens, k = set(), 0
        for ln in lines:                      # word index at which each line opens
            opens.add(k)
            k += len(ln.split())
        a = " ".join(lines).split()
        rest = [w for w, _ in got if w]
        by = ["layer"] + [src for w, src in got if w]
        toks = (arbitrate(a, rest, lex, frozenset(opens), by) if rest
                else [Token(w, KEEP, i in opens, i) for i, w in enumerate(a)])
        mended, kept = restore(toks, guide, lex, log=damage)
        fixed, collated = fixed + mended, collated + kept
        out.append({"page": p["page"], "folio": p["folio"],
                    "body": [[t.text, t.why] for t in toks],
                    "breaks": [i for i, t in enumerate(toks) if t.nl and i],
                    # Kept beside the body rather than inside it: everything
                    # downstream reads a body entry as [word, reason], and a
                    # third element would be a change to every one of them for
                    # the sake of the one pass that wants it.
                    # In the layer's own numbering, not the welded one. Welding
                    # renumbered the backbone; the glyph boxes did not move, and
                    # this is what every crop is looked up by. A welded token
                    # keeps the first fragment's position and the rest leave no
                    # token of their own — exactly the convention the join
                    # repair already uses, so `crops.ink` needs no change: the
                    # gap in the sequence is the record of the run.
                    "at": [-1 if t.at is None else group[t.at][0] for t in toks],
                    # Sparse, and for the same reason `at` sits out here: most
                    # words were read the same way by everybody and have nothing
                    # to say. Writing the empty case would triple the file to
                    # record that twenty-seven thousand times.
                    "alt": {str(i): [list(a) for a in t.alt]
                            for i, t in enumerate(toks) if t.alt},
                    "was": {str(i): t.was for i, t in enumerate(toks) if t.was},
                    "notes": "\n".join(t for t, _ in p["notes"])})
    every = [Token(t, w) for p in out for t, w in p["body"]]
    return {"pages": out, "restored": fixed, "collated": collated,
            "damage": damage, **report(every, lex)}


def as_scan(data: dict) -> str:
    """The arbitrated text in the shape the structural pass already reads —
    lines and all, since the structure is partly written in the lines."""
    out = []
    for p in data["pages"]:
        brk = set(p.get("breaks", ()))
        body = "".join(("\n" if i in brk else " " if i else "") + t
                       for i, (t, _) in enumerate(p["body"]))
        out.append(f"===== PDF3 page {p['page']:03d} =====\n{body}\n")
    return "".join(out)


if __name__ == "__main__":
    base = sys.argv[1] if len(sys.argv) > 1 else "."
    data = run(base)
    # The arbitrated text is a stage, not the edition: `repair.py` reads this
    # file and writes `ensemble.json`. Keeping the two apart means either pass
    # can be re-run over the other's input without the pipeline eating its own
    # output, and the stage table downstream can quote both.
    json.dump(data, open(f"{base}/data/ensemble_arbitrated.json", "w",
                         encoding="utf-8"), ensure_ascii=False)
    print(f"{data['words']:,} words   {data['rate']:.2%} unattested   "
          f"{data['sure']:.1%} certain\n"
          f"  inside a quotation      {data[GUIDE]:>7,}  "
          f"({data['restored']:,} mended from the Guide, "
          f"{data['collated']:,} differ from it and stand)\n"
          f"  every reader agrees     {data[AGREE]:>7,}\n"
          f"  most readers agree      {data[MOST]:>7,}\n"
          f"  lexicon broke the tie   {data[LEX]:>7,}\n"
          f"  several plausible       {data[KEEP]:>7,}\n"
          f"  none is a word          {data[DOUBT]:>7,}", file=sys.stderr)
