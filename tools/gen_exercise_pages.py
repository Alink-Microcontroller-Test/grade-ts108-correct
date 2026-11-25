"""Fill the generated blocks in each exercise's page, and the central list.

Sibling of gen_divergence_table.py, which generates whole documents. These
pages cannot be: most of each one is prose a person wrote, and only two
blocks come from data. So the blocks are delimited, this writes between the
markers, and everything outside them is left exactly as it was found.

    python tools/gen_exercise_pages.py           # write the blocks
    python tools/gen_exercise_pages.py --check   # fail if any is stale

The sweep runs --check, so an edit to either register that was not
regenerated is caught rather than read by a learner.

TWO SOURCES, ONE PASS, BOTH LANGUAGES
-------------------------------------
divergences.json says which differences reach an exercise; references.json
says which manuals it needs and how to reach them. Both carry their own
Japanese, so the two editions of a page are written from the same rows in
the same pass and cannot disagree about which rows apply. Whether the prose
around them agrees is not something this can check -- ADR-0002 said so about
its own tables and it is still true here.

WHAT MAY NOT APPEAR HERE
------------------------
A chapter, a register name or a value. ADR-0003: the substance a learner is
sent to the datasheet to find may not be generated for them. This names the
document and the row to click, and stops.
"""

import argparse
import io
import json
import os
import sys

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
REGISTER = os.path.join(ROOT, "divergences.json")
REFERENCES = os.path.join(ROOT, "references.json")
EXERCISES = os.path.join(ROOT, "exercises")

OPEN = "<!-- generated: %s -->"
CLOSE = "<!-- /generated -->"

EDITIONS = (
    ("en", "README.md"),
    ("ja", "README.ja.md"),
)

WORDS = {
    "en": {
        "no_divergences": "Nothing in the simulator misleads you on this "
                          "exercise. The full list is in "
                          "[`DIVERGENCES.md`](../../DIVERGENCES.md).",
        "on_hardware": "On real hardware",
        "traps_head": "**These can let wrong code look right.** The "
                      "simulator is more permissive than the board here, so "
                      "it will not tell you:",
        "rest_head": "Also true here, and worth knowing:",
        "rest_tail": "The full text of each is in "
                     "[`DIVERGENCES.md`](../../DIVERGENCES.md).",
        "open": "Open the",
        "page": "documentation page",
        "find_in": "find the",
        "section": "section, and click",
        "generated": "<!-- This block is generated from %s. Do not edit it "
                     "by hand; run python tools/gen_exercise_pages.py -->",
    },
    "ja": {
        "no_divergences": "この課題で、シミュレータが誤解を招く点はありません。"
                          "全一覧は [`DIVERGENCES.ja.md`](../../DIVERGENCES.ja.md) "
                          "にあります。",
        "on_hardware": "実機では",
        "traps_head": "**誤ったコードが正しく見えてしまう点です。**"
                      "ここではシミュレータのほうが実機より寛容なため、"
                      "何も知らせてくれません。",
        "rest_head": "そのほか、知っておく価値のある違いです。",
        "rest_tail": "それぞれの全文は "
                     "[`DIVERGENCES.ja.md`](../../DIVERGENCES.ja.md) "
                     "にあります。",
        "generated": "<!-- このブロックは %s から生成されています。手で編集せず、"
                     "python tools/gen_exercise_pages.py を実行してください -->",
    },
}


def load(path, key):
    with io.open(path, encoding="utf-8") as handle:
        return json.load(handle)[key]


def exercises_in_order():
    return sorted(name for name in os.listdir(EXERCISES)
                  if os.path.isdir(os.path.join(EXERCISES, name)))


def reference_lines(documents, exercise, lang):
    """How to reach each manual this exercise needs.

    The Japanese page is not a translation of the English one. Two of the
    three documents are reached differently there, and the difference is in
    the data rather than in anybody's memory: the datasheet's identifier is
    missing from the Japanese listing, and the board manual is absent from
    it altogether.
    """
    out = []
    for doc in documents:
        if exercise not in doc["exercises"]:
            continue
        title = doc["title_ja"] if lang == "ja" else doc["title"]
        purpose = doc["what_for_ja"] if lang == "ja" else doc["what_for"]
        url = doc["listing"].get(lang) or doc["listing"]["en"]
        page = doc["page"].get(lang) or doc["page"]["en"]
        find = doc["find"].get(lang) or doc["find"]["en"]

        # The link is named after the PAGE it opens, never after the
        # document. st.com has no per-document page, so a link labelled
        # with the document's own title lands the learner on a list and
        # tells them they have arrived.
        if lang == "ja":
            out.append("- **%s** — %s。%s" % (doc["id"], title, purpose))
            out.append("  [%s](%s) を開き、%s。" % (page, url, find))
        else:
            out.append("- **%s** — %s. %s" % (doc["id"], title, purpose))
            out.append("  Open [%s](%s) and %s." % (page, url, find))
    return out


def first_sentence(text, lang):
    """Enough to know whether it matters to you, not the whole row.

    The full text of seven rows on one page is a wall, and a wall is what
    DIVERGENCES.md already is -- the document nobody reads, which is the
    problem this change exists to solve rather than to reproduce. Traps keep
    their full text because they can cost a learner a pass they did not earn.
    Everything else gets its first sentence and a pointer.
    """
    stop = "。" if lang == "ja" else ". "
    at = text.find(stop)
    if at < 0:
        return text
    return text[:at + (1 if lang == "ja" else 1)].strip()


def divergence_lines(rows, exercise, lang):
    """What the simulator gets wrong here, traps first.

    Traps first because they are the ones that let working code be wrong.
    The rest are worth knowing and will not cost a learner a passing
    exercise, so they come second rather than being left out -- leaving them
    out is what this change exists to stop.
    """
    mine = [row for row in rows if exercise in (row.get("exercises") or [])]
    mine.sort(key=lambda row: (not row.get("hides_mistake"), row["id"]))

    if not mine:
        return [WORDS[lang]["no_divergences"]]

    traps = [row for row in mine if row.get("hides_mistake")]

    # A `fixed` row is one the board description has already corrected, so
    # it is not "also true here" -- it is the opposite of true here, and
    # printing its `renode` sentence under that heading tells the learner
    # the reverse of what their own board does. Two cases were doing exactly
    # that, in both languages:
    #
    #   declared-clock-rate   "every timer is declared at 10 MHz", while
    #                         exercise 2's main.c says 84,000,000 and its
    #                         check grades on 84,000,000. The correcting
    #                         sentence is cut by first_sentence.
    #   button-polarity       "drives its pin high while pressed", against
    #                         exercise 3's own main.c, its own check, and
    #                         boards/nucleo_f401re.repl, which sets invert.
    #
    # Emitting the status instead of filtering would keep the information,
    # at the cost of putting a correction the learner does not need under a
    # heading that promises things that are true. They lose nothing: the
    # polarity is in exercise 3's main.c three times, and the timer rate is
    # the premise the exercise is built on.
    rest = [row for row in mine if not row.get("hides_mistake")
            and row.get("status") != "fixed"]

    if not traps and not rest:
        return [WORDS[lang]["no_divergences"]]

    out = []
    if traps:
        out.append(WORDS[lang]["traps_head"])
        out.append("")
    for row in traps:
        renode = (row["renode_ja"] if lang == "ja" else row["renode"]).strip()
        board = (row["board_ja"] if lang == "ja" else row["board"]).strip()
        out.append("- **%s** — %s" % (row["id"], renode))
        out.append("  %s: %s" % (WORDS[lang]["on_hardware"], board))

    if rest:
        if traps:
            out.append("")
        out.append(WORDS[lang]["rest_head"])
        out.append("")
        for row in rest:
            renode = (row["renode_ja"] if lang == "ja"
                      else row["renode"]).strip()
            out.append("- **%s** — %s" % (row["id"], first_sentence(renode,
                                                                   lang)))
        out.append("")
        out.append(WORDS[lang]["rest_tail"])
    return out


def central_lines(documents, lang):
    """Every manual, for the page that is about all four exercises."""
    out = []
    for doc in documents:
        title = doc["title_ja"] if lang == "ja" else doc["title"]
        purpose = doc["what_for_ja"] if lang == "ja" else doc["what_for"]
        url = doc["listing"].get(lang) or doc["listing"]["en"]
        page = doc["page"].get(lang) or doc["page"]["en"]
        out.append("- **%s** — %s" % (doc["id"], title))
        out.append("  %s [%s](%s)" % (purpose, page, url))
    return out


def splice(body, name, lines, source, lang, where):
    """Replace what sits between one pair of markers.

    A missing or unpaired marker is an error, not something to repair. The
    page would otherwise be regenerated into the wrong place, which is worse
    than being told the page is broken.
    """
    start = OPEN % name
    if body.count(start) != 1:
        raise SystemExit("%s: expected exactly one %s" % (where, start))
    head, rest = body.split(start, 1)
    if rest.count(CLOSE) < 1:
        raise SystemExit("%s: %s is never closed" % (where, start))
    _, tail = rest.split(CLOSE, 1)

    note = WORDS[lang]["generated"] % source
    block = "\n".join([start, note, ""] + lines + ["", CLOSE])
    return head + block + tail


def page_for(path, lang, exercise, rows, documents):
    body = io.open(path, encoding="utf-8").read()
    body = splice(body, "references",
                  reference_lines(documents, exercise, lang),
                  "references.json", lang, path)
    body = splice(body, "divergences",
                  divergence_lines(rows, exercise, lang),
                  "divergences.json", lang, path)
    return body


def main(argv=None):
    parser = argparse.ArgumentParser()
    parser.add_argument("--check", action="store_true",
                        help="fail if any generated block is stale")
    args = parser.parse_args(argv)

    rows = load(REGISTER, "divergences")
    documents = load(REFERENCES, "documents")

    stale = []
    written = 0

    for exercise in exercises_in_order():
        for lang, filename in EDITIONS:
            path = os.path.join(EXERCISES, exercise, filename)
            if not os.path.isfile(path):
                stale.append("%s/%s is missing" % (exercise, filename))
                continue
            want = page_for(path, lang, exercise, rows, documents)
            have = io.open(path, encoding="utf-8").read()
            if want == have:
                continue
            if args.check:
                stale.append("%s/%s" % (exercise, filename))
            else:
                io.open(path, "w", encoding="utf-8", newline="").write(want)
                written += 1

    for lang, filename in EDITIONS:
        path = os.path.join(EXERCISES, filename)
        if not os.path.isfile(path):
            stale.append("exercises/%s is missing" % filename)
            continue
        have = io.open(path, encoding="utf-8").read()
        if (OPEN % "manuals") not in have:
            continue
        want = splice(have, "manuals", central_lines(documents, lang),
                      "references.json", lang, path)
        if want == have:
            continue
        if args.check:
            stale.append("exercises/%s" % filename)
        else:
            io.open(path, "w", encoding="utf-8", newline="").write(want)
            written += 1

    if args.check:
        if stale:
            print("stale, regenerate with python tools/gen_exercise_pages.py:")
            for item in stale:
                print("  %s" % item)
            return 1
        print("exercise pages: generated blocks match their sources")
        return 0

    if stale:
        print("could not generate:")
        for item in stale:
            print("  %s" % item)
        return 1
    print("exercise pages: %d block(s) written" % written)
    return 0


if __name__ == "__main__":
    sys.exit(main())
