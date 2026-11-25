"""The per-exercise pages, and the generator that fills their blocks.

The staleness gate lives in the sweep, which runs
`gen_exercise_pages.py --check`. What is here is everything that gate cannot
say: that both editions of a page agree about which rows apply, that every
page sends a learner to at least one manual, and that a damaged marker is an
error rather than something quietly repaired into the wrong place.

Every test reads the real registers. A fixture would pass while the data and
the code disagreed about what a field means, which is exactly how the
assistant came to be told nothing for the life of the course.
"""

import io
import json
import os
import re
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(HERE)
sys.path.insert(0, os.path.join(ROOT, "tools"))

import gen_exercise_pages as gen  # noqa: E402

EXERCISES = os.path.join(ROOT, "exercises")


def exercises():
    return sorted(name for name in os.listdir(EXERCISES)
                  if os.path.isdir(os.path.join(EXERCISES, name)))


def page(exercise, filename):
    with io.open(os.path.join(EXERCISES, exercise, filename),
                 encoding="utf-8") as handle:
        return handle.read()


def block(body, name):
    start = gen.OPEN % name
    return body.split(start, 1)[1].split(gen.CLOSE, 1)[0]


def ids_in(text):
    """Bold tokens that look like an id: RM0368, open-drain-ignored.

    Only the one that opens a list item. Uppercase matters -- the manual ids
    are uppercase and the divergence ids are not, and matching only lowercase
    made the manual tests compare two empty sets and pass, which is the
    failure this whole change is about. Anchoring to the list item matters
    too: the English block bolds the section name to click, and without the
    anchor that counted as an id and the two editions never agreed.
    """
    return set(re.findall(r"^- \*\*([A-Za-z0-9][A-Za-z0-9-]*[A-Za-z0-9])\*\*",
                          text, re.MULTILINE))


def test_there_are_exercises_and_pages_to_check():
    """Or every test below passes on an empty list."""
    names = exercises()
    assert len(names) >= 4, names
    for name in names:
        for filename in ("README.md", "README.ja.md"):
            path = os.path.join(EXERCISES, name, filename)
            assert os.path.isfile(path), "%s is missing" % path


def test_both_editions_name_the_same_divergences():
    """One pass, one set of rows, so the two cannot drift apart.

    Whether they say the same thing is not checkable by machine. Whether
    they are about the same rows is, and that is the half that went wrong
    before: two exercises carried a warning and two did not.
    """
    looked = 0
    for name in exercises():
        english = ids_in(block(page(name, "README.md"), "divergences"))
        japanese = ids_in(block(page(name, "README.ja.md"), "divergences"))
        assert english, "%s: README.md names no divergence" % name
        assert english == japanese, (
            "%s: the two editions name different divergences: %s"
            % (name, english ^ japanese))
        looked += 1
    assert looked >= 4


def test_both_editions_name_the_same_manuals():
    looked = 0
    for name in exercises():
        english = ids_in(block(page(name, "README.md"), "references"))
        japanese = ids_in(block(page(name, "README.ja.md"), "references"))
        assert english, "%s: README.md names no manual" % name
        assert english == japanese, (
            "%s: the two editions name different manuals: %s"
            % (name, english ^ japanese))
        looked += 1
    assert looked >= 4


def test_every_page_sends_the_learner_to_a_manual():
    """An exercise naming no manual is an exercise with nowhere to look."""
    for name in exercises():
        for filename in ("README.md", "README.ja.md"):
            named = ids_in(block(page(name, filename), "references"))
            assert named, (
                "%s/%s names no manual. Every exercise needs a value from "
                "one of them." % (name, filename))


def test_a_reference_block_names_no_section_or_register():
    """ADR-0003: the substance a learner is sent to find is not generated.

    A section number or a register name in a reference would hand over the
    part that is the exercise. This cannot catch every phrasing; it catches
    the shapes a pointer would take if somebody decided to be helpful.
    """
    forbidden = re.compile(r"§|\bsection \d|\bchapter \d|"
                           r"\b[A-Z]{2,}[0-9]*->|\bRCC_|\bGPIO[A-Z]_",
                           re.IGNORECASE)
    for name in exercises():
        for filename in ("README.md", "README.ja.md"):
            text = block(page(name, filename), "references")
            found = forbidden.search(text)
            assert not found, (
                "%s/%s: the reference block names %r, which is the part the "
                "learner is supposed to find" % (name, filename, found.group(0)))


def test_a_missing_marker_is_an_error():
    body = "# A page\n\nno markers here at all\n"
    try:
        gen.splice(body, "references", ["x"], "references.json", "en", "<test>")
    except SystemExit as why:
        assert "expected exactly one" in str(why)
    else:
        raise AssertionError("a page with no marker was spliced anyway")


def test_a_duplicated_marker_is_an_error():
    start = gen.OPEN % "references"
    body = "%s\n%s\n%s\n%s\n" % (start, gen.CLOSE, start, gen.CLOSE)
    try:
        gen.splice(body, "references", ["x"], "references.json", "en", "<test>")
    except SystemExit as why:
        assert "expected exactly one" in str(why)
    else:
        raise AssertionError("a page with two markers was spliced anyway")


def test_an_unclosed_marker_is_an_error():
    body = "%s\nand nothing closes it\n" % (gen.OPEN % "references")
    try:
        gen.splice(body, "references", ["x"], "references.json", "en", "<test>")
    except SystemExit as why:
        assert "never closed" in str(why)
    else:
        raise AssertionError("an unclosed marker was spliced anyway")


def test_splice_leaves_everything_outside_the_markers_alone():
    start = gen.OPEN % "references"
    body = "before\n\n%s\nold\n%s\n\nafter\n" % (start, gen.CLOSE)
    out = gen.splice(body, "references", ["new"], "references.json", "en", "t")
    assert out.startswith("before\n\n")
    assert out.endswith("\n\nafter\n")
    assert "new" in out
    assert "old" not in out


def test_the_registers_agree_about_which_exercises_exist():
    """Both files name exercises. Neither may name one that is not there."""
    names = set(exercises())
    for path, key in ((os.path.join(ROOT, "divergences.json"), "divergences"),
                      (os.path.join(ROOT, "references.json"), "documents")):
        with io.open(path, encoding="utf-8") as handle:
            rows = json.load(handle)[key]
        assert rows
        for row in rows:
            for named in row.get("exercises") or []:
                assert named in names, (
                    "%s: %s names %s, which is not an exercise"
                    % (os.path.basename(path), row.get("id"), named))
