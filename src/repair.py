#!/usr/bin/env python3
"""Mend the words no reading got right, using only what the volume itself proves.

After arbitration and collation about one word in eleven of the Kaspi zone is
still a form no clean Hebrew text attests. Most of them are not mysterious.
Hebrew square type of 1848 has a handful of letter pairs that a scanner at this
resolution cannot keep apart, and the residue is full of ‏רבר‎ for ‏דבר‎ and
‏אהר‎ for ‏אחר‎ — words that are one stroke away from being right and are wrong
in the same way over and over.

The usual way to fix this is a table of confusions copied out of the OCR
literature. That table would be about a different typeface, a different
scanner and a different century, and there would be no way to tell which of its
entries applied here. This module does not use one. It *derives* the table from
the volume, out of evidence the edition has already produced and thrown away:

*The collation is a labelled sample.* Where `ensemble.restore` recognised a
lemma and replaced it with Ibn Tibbon's text, the true reading of those words
is known — not guessed, known — so every word it had to correct is an example
of how this print fails, with an answer attached. Four hundred and fifty-two of
them, and the letter-level diffs are unambiguous: ‏ר‎ read for ‏ד‎ seventy-two
times, ‏כ‎ for ‏ב‎ twenty-two, then ‏ה‎/‏ח‎ for ‏ת‎ and a thin tail. That is this
scan's confusion table, measured on this scan.

*The corrections are more of the same.* A confusion the collation happened not
to witness is still a confusion, so the pass runs twice: the first round's
accepted repairs are themselves labelled pairs, and they extend the table for
the second. Bootstrapping is only safe behind a strict gate, which is the next
paragraph.

Three repairs are attempted, in this order, and each must be *unique* to be
accepted:

*Substitution.* Up to two letters replaced from the derived table. If exactly
one candidate is an attested Hebrew word, it is taken; if several are, the pass
declines unless one is commoner in the clean corpus than all the rest together
by a wide margin, because a coin-flip dressed as a correction is worse than an
honest flag.

*Splitting.* The scanner drops spaces. A run of letters that is not a word,
that falls into two attested words at exactly one point, *and* that a reader of
the page read as two words with a space between them, is two words. The last
clause is not decoration: without it the rule fabricated, and what it fabricated
is described where it is implemented.

*Joining.* It also invents them, mostly around a maqaf. Two adjacent unattested
tokens whose letters together make one attested word were one word.

What the pass will not do is guess. It never touches a word that is already
attested, never touches a word restored from the Guide, and where more than one
answer is possible it leaves the word alone and marked, for the human pass with
the page image beside it. Every word it does change carries the reason `fix`,
so the edition can show exactly which words it mended and the reader can
disbelieve any of them.

Dependencies: none. Standard library only.
"""
from __future__ import annotations

import collections
import json
import sys

import ensemble
import ocrqual
from ensemble import FIX, GUIDE, Token

CONF_MIN = 2        # a confusion witnessed once is an accident, not a habit
STRONG_MIN = 10     # ...and this is one the volume commits constantly
MAX_SUBS = 2        # two bad letters in one short word is already unlikely
DOMINANCE = 8       # how far ahead a frequent candidate must be to win a tie
MIN_LEN = 3         # below this every string is some word; repairing is noise
MEDIAL = str.maketrans("כמנפצ", "ךםןףץ")

# The readings the lexicon is not allowed a free hand with.
#
# This was `agree` alone, and the `was` field is what showed that to be wrong.
# Once every correction recorded what it had overwritten, page 4 read: ‏מחקריו‎
# turned into ‏מחקרים‎, ‏המתחסדים‎ into ‏המהחסרים‎, ‏פרושיו‎ into ‏פרושנו‎, and
# ‏אשר יפטירו בשפה יניעו ראש‎ — Psalm 22:8, quoted correctly by every reader but
# one — into ‏אשר הפטירה‎. None of the four was unanimous, so all four fell
# outside the gate and were handed the full confusion table at two
# substitutions' depth; and a six-letter word with two free substitutions
# reaches some hundreds of forms, among which finding exactly one commoner
# Hebrew word is not evidence of anything.
#
# The distinction the gate was reaching for is not unanimity. It is whether any
# reader of the ink supports the form on the page. `agree` means all of them
# did, `most` that a majority did, `seen` that the one reader who can read
# Hebrew did and the machines were blind at exactly those letters. `lex`, `keep`
# and `fix` reach the gate only in the second round, and are held for a
# different reason: something has already decided them, and a repair stacked on
# a repair is the bootstrapping this module's docstring says is only safe behind
# a strict gate.
#
# That leaves `doubt` — no reading was a word and the readers did not agree on
# one either — and the first draft of this fix let the lexicon work freely
# there, on the ground that there was nothing to overturn. There is. `decide`
# sorts the readings by RANK before its last clause, so a `doubt` token is
# usually the eye's reading, and the eye is the most accurate reader in the
# volume. Of the 114 words the free hand mended, 46 overwrote a form the eye had
# returned, and reading them is enough: ‏מציאותות‎→‏מציאויות‎ and ‏דמיין‎→‏דמיון‎
# are right, ‏רשימות‎→‏רוממות‎ and ‏המעתיקים‎→‏המעמוקים‎ and ‏בהדרו‎→‏בהדרב‎ are
# inventions. That is a coin flip, and this module's own standard is that a
# coin-flip dressed as a correction is worse than an honest flag.
#
# So the gate is not only the reason. A form that any reader of *this page*
# returned is protected however the arbitration labelled it, and the free hand
# is left with the words that no reader vouches for — the ones assembled by the
# machinery, where a lexicon is the only evidence there is.
SURE = (ensemble.AGREE, ensemble.MOST, ensemble.SEEN,
        ensemble.LEX, ensemble.KEEP, FIX)


def witnessed(pages: list[dict], lex: set[str]) -> list[list[str]]:
    """Labelled misreadings, taken from the arbitration itself.

    A confusion table has to be learned from something, and what this one was
    learned from was the collation against the Guide — the places where a
    quotation differed from Ibn Tibbon. Ten of those were misreadings. The
    other four hundred and fifty-six were two editions of a fourteenth-century
    text differing the way editions do, so the table said less about this
    scanner than about the transmission of the Guide; and at the ten-witness
    floor it said nothing whatever. `strong` came out empty, which means the
    one rule in `mend` that depends on it — the rule its docstring describes at
    length, naming the letters — had never fired, not once, on this volume.

    The arbitration knew better all along. Every word two instruments read two
    ways carries the readings that lost, and where the reading that won is a
    Hebrew word and the one that lost is not, the loser is a misreading of the
    winner by definition: no judgement about Kaspi's vocabulary is being made
    about a form that is not a form. Twenty-one thousand of those against four
    hundred and sixty-six, every one of them this scanner failing on this ink,
    and all of it already in the file.

    Readings the Guide rejected are skipped. Those are textual, and a textual
    variant is not evidence about an optical instrument — which is the whole
    lesson of the table this one replaces.
    """
    out: list[list[str]] = []
    for p in pages:
        alt = p.get("alt", {})
        for i, (text, _) in enumerate(p["body"]):
            won = ensemble.bare(text)
            if not won or not ocrqual.attested(won, lex):
                continue
            for form, src in alt.get(str(i), ()):
                lost = ensemble.bare(form)
                if src != GUIDE and lost and not ocrqual.attested(lost, lex):
                    out.append([lost, won])
    return out


def confusions(damage: list[list[str]], floor: int = CONF_MIN) -> dict[str, set[str]]:
    """What this scan reads for what, learned from `witnessed` pairs."""
    seen: collections.Counter = collections.Counter()
    for read, true in damage:
        if len(read) != len(true):
            continue
        diff = [(a, b) for a, b in zip(read, true) if a != b]
        if len(diff) == 1:
            seen[diff[0]] += 1
    tab: dict[str, set[str]] = {}
    for (a, b), n in seen.items():
        if n >= floor:
            tab.setdefault(a, set()).add(b)
    return tab


def variants(word: str, tab: dict[str, set[str]], depth: int) -> set[str]:
    """Every word reachable by *depth* substitutions from the derived table."""
    out = {word}
    for _ in range(depth):
        for w in list(out):
            for i, c in enumerate(w):
                for r in tab.get(c, ()):
                    out.add(w[:i] + r + w[i + 1:])
    out.discard(word)
    return out


def pick(cands: set[str], lex: set[str], freq: collections.Counter) -> str | None:
    """The one attested candidate, or the one that dwarfs the others."""
    good = sorted((w for w in cands if ocrqual.attested(w, lex)),
                  key=lambda w: -freq[w])
    if len(good) == 1:
        return good[0]
    if len(good) > 1 and freq[good[0]] >= DOMINANCE * max(1, sum(freq[w] for w in good[1:])):
        return good[0]
    return None


def seams(readings: list[list[str]]) -> set[tuple[str, str]]:
    """Every pair of words a reader of this page set side by side."""
    return {(a, b) for r in readings for a, b in zip(r, r[1:])}


def split(word: str, lex: set[str], seam: set[tuple[str, str]]) -> str | None:
    """One lost space, where a reader of the page saw one.

    The lexicon alone cannot license this repair, and letting it try was a
    fabrication engine. Hebrew is dense with short words, so almost any form can
    be cut somewhere into two that a corpus attests: over this volume the test
    fired 280 times and 275 of those were a space no reader of the page had put
    there — ‏התנצלתי‎ cut into ‏התנצל תי‎, ‏מחקריו‎ into ‏מחקר יו‎, ‏בים‎ into
    ‏בי ים‎. What made every one of them look plausible is that Kaspi's own
    vocabulary is largely outside a lexicon built from other authors, so the
    whole word is unattested and both halves are, which is the test exactly.

    The words that genuinely need it are the ones the publisher's layer fused
    when it lost a space — ‏יעוייןשמה‎, ‏בס׳הנקרא‎ — and those are visible to a
    reader that looked at the page: it reads two words with a gap between them.
    So the space must be witnessed. The lexicon still has to agree, but it no
    longer decides alone, and a repair with no evidence outside the word is not
    made at all.
    """
    cuts = [i for i in range(2, len(word) - 1)
            if (word[:i], word[i:]) in seam
            and ocrqual.attested(word[:i], lex) and ocrqual.attested(word[i:], lex)]
    return f"{word[:cuts[0]]} {word[cuts[0]:]}" if len(cuts) == 1 else None


def runs(text: str) -> list[str]:
    return ocrqual.LETTERS.findall(ocrqual.NIQQUD.sub("", text))


def clean(text: str, lex: set[str], seen: set[str]) -> str | None:
    """That word with the damage taken out — closed up, or opened to a space.

    Two readings of the mark are possible and the evidence has to choose. It may
    stand where the compositor set nothing, in which case the letters close up;
    or where he set a space that the scanner then read as ink, in which case it
    becomes one. Guessing between them is not repair, so each has to be
    witnessed: *seen* is every word another reader of this same page returned,
    and a form that one of them read is a form this ink can carry.

    Closing up may also be accepted on the lexicon alone, and opening may not.
    That asymmetry is the whole caution of the pass. Closing up deletes a mark
    the page did not print and adds nothing; opening asserts a word division,
    which is the repair that fabricated two hundred and seventy-five splits the
    last time this edition let a lexicon license one unwitnessed.
    """
    part = ocrqual.pieces(text)
    if not part:
        return None
    shut = "".join(part)
    if ensemble.bare(shut) in seen or ocrqual.attested(ocrqual.fold(shut), lex):
        return shut
    if all(ensemble.bare(p) in seen for p in part):
        return " ".join(part)
    return None


def spell(word: str) -> str:
    """Put back the final forms folding took off. Not a guess — a rule."""
    return " ".join(w[:-1] + w[-1].translate(MEDIAL) for w in word.split() if w)


def mend(tokens: list[Token], lex: set[str], freq: collections.Counter,
         tab: dict[str, set[str]], strong: dict[str, set[str]],
         seam: set[tuple[str, str]] = frozenset(),
         seen: set[str] = frozenset()
         ) -> tuple[list[Token], list[list[str]], dict]:
    """One pass of repair over a page. Returns the text, and what it learned.

    A token is repaired in place, so that whatever punctuation the compositor
    set around the word survives the correction: only the letters change. That
    restricts the pass to tokens holding a single run of letters, which is
    almost all of them, and leaves the ones spelling two words around a maqaf
    to the join rule or to the human.

    A word all three readings returned identically is treated differently from
    one they fought over, and the difference matters more than it looks.
    Unanimity is evidence about the ink; the lexicon is evidence about the
    language; and where they conflict, an edition that lets the lexicon win has
    started quietly normalising the book it is supposed to report. Kaspi's
    Hebrew is full of forms the clean corpus never happens to use — the floor
    measurement says so — and every one of them is a word a careless repair
    would turn into a commoner one.

    So a unanimous reading is only overruled where the volume misreads
    constantly anyway: one substitution, drawn from the confusions witnessed
    ten times or more, which on this scan means ‏ר‎ for ‏ד‎, ‏כ‎ for ‏ב‎, ‏ה‎ for
    ‏ח‎ and seventy-odd more. Three engines agreeing on a broken descender is
    exactly what those look like. Everything else unanimous stands as printed
    and is flagged, not mended.

    That table was empty until `witnessed` replaced the source it was learned
    from, so this paragraph described a rule that had never run. It runs now.
    """
    out: list[Token] = []
    learnt: list[list[str]] = []
    tally: collections.Counter = collections.Counter()
    skip = False
    for i, t in enumerate(tokens):
        if skip:
            skip = False
            continue
        if t.why == GUIDE or ensemble.ok(t.text, lex):
            out.append(t)
            continue

        # Damage inside the letters comes out before anything else is tried.
        # Until it does the token is not a word at all, so no confusion table
        # can be applied to it and the substitution pass below would step over
        # it — which is why a hundred and forty-four of these survived every
        # earlier round of repair untouched.
        if (fresh := clean(t.text, lex, seen)) is not None:
            out.append(Token(fresh, FIX, t.nl, t.at, t.alt, t.was or t.text))
            tally[FIX] += 1
            continue

        part = runs(t.text)
        if len(part) != 1:
            out.append(t)
            tally["left"] += 1
            continue
        bare = ocrqual.fold(part[0])
        nxt = tokens[i + 1] if i + 1 < len(tokens) else None

        # Joining first: it is the only repair with evidence outside the word.
        # Never across a line opening — where the line broke is a fact about
        # the page, and no correction of ours is worth deleting one.
        if (nxt is not None and not nxt.nl and nxt.why != GUIDE
                and not ensemble.ok(nxt.text, lex) and len(runs(nxt.text)) == 1
                and len(bare) >= 2
                and ocrqual.attested(bare + ocrqual.fold(runs(nxt.text)[0]), lex)):
            out.append(Token(t.text.rstrip("־-‐-") + nxt.text, FIX, t.nl, t.at,
                             t.alt + nxt.alt, f"{t.text} {nxt.text}"))
            tally[FIX] += 1
            skip = True
            continue

        # The split rule shares the gate, though its witness looks independent.
        # A reader who set two words apart is evidence, but `seams` collects
        # them over the whole page, so the pair licensing a cut may have been
        # read somewhere else entirely; whereas a reading that agrees here
        # agrees *here*, and what it says is that there was no space. Positional
        # testimony beats a coincidence of vocabulary. Freeing the rule mends
        # one more word in the volume and puts every unanimous reading at risk
        # of being cut in two, which is not a trade.
        sure = t.why in SURE or ensemble.bare(t.text) in seen
        use, depth = (strong, 1) if sure else (tab, MAX_SUBS)
        got = None
        if len(bare) >= MIN_LEN:
            got = pick(variants(bare, use, depth), lex, freq)
            if got is None and not sure:
                got = split(bare, lex, seam)
        if got is None:
            out.append(t)
            tally["left"] += 1
            continue
        if " " not in got:
            learnt.append([bare, got])
        out.append(Token(t.text.replace(part[0], spell(got), 1), FIX, t.nl, t.at,
                         t.alt, t.was or t.text))
        tally[FIX] += 1
    return out, learnt, tally


def run(base: str = ".", rounds: int = 2) -> dict:
    data = json.load(open(f"{base}/data/ensemble_arbitrated.json", encoding="utf-8"))
    corpus = json.load(open(f"{base}/data/corpus.json", encoding="utf-8"))
    lex = ensemble.lexicon(corpus)
    freq = collections.Counter(
        ocrqual.fold(w) for ps in corpus.values() for pp in ps.values()
        for p in pp for w in ocrqual.LETTERS.findall(ocrqual.NIQQUD.sub("", p)))

    # Where the readers put spaces, page by page. The split rule needs evidence
    # from outside the word it is repairing, and this is the only evidence there
    # is: another reader of the same ink, who saw a gap.
    seam = {}
    for src in ("book_eyes.json", "book_tess.json", "book_tess300.json"):
        for page, text in ensemble.reading(f"{base}/data/{src}").items():
            seam.setdefault(page, []).append(
                [ensemble.bare(w) for w in text.split()])

    # The scanner's own record first, the collation's ten genuine misreadings
    # after it. Both are pairs of the same kind — read *this*, meant *that* —
    # and they are kept in one list because the rounds below append to it.
    damage = witnessed(data["pages"], lex) + list(data["damage"])
    seen_pairs = len(damage)
    # The join rule below merges two tokens into one, so a token's position in
    # the page stops being its position on the page. What each token was read
    # from travels with it instead, and a token that ate its neighbour keeps
    # the earlier of the two: the ink then runs from there to wherever the next
    # surviving token starts, which is exactly what `crops.py` reads off.
    pages = [[Token(t, w, i in set(p.get("breaks", ())), at,
                    tuple(tuple(a) for a in p.get("alt", {}).get(str(i), ())),
                    p.get("was", {}).get(str(i), ""))
              for i, ((t, w), at) in enumerate(zip(p["body"], p["at"]))]
             for p in data["pages"]]

    strong = confusions(damage, STRONG_MIN)   # learned once, before any repair
    for r in range(rounds):
        tab = confusions(damage)
        total: collections.Counter = collections.Counter()
        for k, toks in enumerate(pages):
            read = seam.get(data["pages"][k]["page"], [])
            pages[k], learnt, tally = mend(
                toks, lex, freq, tab, strong, seams(read),
                {w for r in read for w in r})
            damage += learnt
            total += tally
        print(f"  round {r + 1}: {sum(len(v) for v in tab.values())} confusions "
              f"known, {total[FIX]:,} words mended, {total['left']:,} left flagged",
              file=sys.stderr)
        if not total[FIX]:
            break

    for p, toks in zip(data["pages"], pages):
        p["body"] = [[t.text, t.why] for t in toks]
        p["breaks"] = [i for i, t in enumerate(toks) if t.nl and i]
        p["at"] = [t.at for t in toks]
        # Rebuilt rather than carried: the join rule merges two tokens into one,
        # so every index after the first join has moved.
        p["alt"] = {str(i): [list(a) for a in t.alt]
                    for i, t in enumerate(toks) if t.alt}
        p["was"] = {str(i): t.was for i, t in enumerate(toks) if t.was}
    every = [t for toks in pages for t in toks]
    data.update(ensemble.report(every, lex))
    data["fixed"] = sum(1 for t in every if t.why == FIX)
    data["confusions"] = {a: sorted(b) for a, b in sorted(confusions(damage).items())}
    # What the edition says about its own method, measured here and printed
    # there. The page used to carry these figures as prose, and prose does not
    # get recomputed: it went on naming the four hundred and fifty-two Guide
    # collations long after the table had stopped being learned from them.
    tally: collections.Counter = collections.Counter()
    for a, b in damage:
        if len(a) == len(b):
            d = [p for p in zip(a, b) if p[0] != p[1]]
            if len(d) == 1:
                tally[d[0]] += 1
    data["witnessed"] = seen_pairs
    data["conftop"] = [[a, b, n] for (a, b), n in tally.most_common(3)]
    return data


if __name__ == "__main__":
    base = sys.argv[1] if len(sys.argv) > 1 else "."
    data = run(base)
    json.dump(data, open(f"{base}/data/ensemble.json", "w", encoding="utf-8"),
              ensure_ascii=False)
    open(f"{base}/out/AmudeiKesef_ensemble_OCR.txt", "w",
         encoding="utf-8").write(ensemble.as_scan(data))
    print(f"{data['words']:,} words   {data['rate']:.2%} unattested   "
          f"{data['fixed']:,} mended", file=sys.stderr)
