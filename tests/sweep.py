"""Verification sweep for the NUCLEO-F401RE board description.

Three halves, which is one too many but is what there is. The first checks
that divergences.json is well formed and internally consistent. The second
checks the things around it that go stale without erring: the English and
Japanese documents against each other, the generated tables against the
register, the board view against the plugin that feeds it. The third starts
Renode and asserts every claim the register marks as 'fixed', because a
claim about running software goes stale without erring either.

Exits non-zero if anything fails. That is the whole point of it: a sweep that
reports a failure and exits 0 is a sweep that CI treats as a pass.

    python tests/sweep.py [--renode PATH]
"""

import argparse
import glob
import io
import json
import os
import re
import shutil
import subprocess
import sys
import tempfile

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))

sys.path.insert(0, os.path.join(ROOT, "tools"))
import checklib as CHECKLIB  # noqa: E402  (after ROOT, which locates it)

REQUIRED = ("id", "renode", "board", "renode_ja", "board_ja", "source", "status")
STATUSES = ("permanent", "outstanding", "fixed")

GENERATED = (".git", "__pycache__", ".pytest_cache")

# The one document that is bilingual in one file rather than a pair. It is
# named here, one entry, rather than inferred from a document's contents: a
# rule that read "contains Japanese, so it needs no partner" would pass any
# document that lost its English or Japanese side while keeping a single
# Japanese word, which is the failure this check exists to catch.
BILINGUAL = ("README",)

failures = []
checks = 0


def check(condition, message):
    global checks
    checks += 1
    if not condition:
        failures.append(message)
    return condition


def load_register():
    with open(os.path.join(ROOT, "divergences.json"), encoding="utf-8") as handle:
        return json.load(handle)["divergences"]


def check_register(rows):
    seen = set()

    for row in rows:
        rid = row.get("id", "<no id>")

        for field in REQUIRED:
            check(row.get(field), f"{rid}: missing required field '{field}'")

        check(rid not in seen, f"{rid}: duplicate id")
        seen.add(rid)

        check(
            row.get("status") in STATUSES,
            f"{rid}: status {row.get('status')!r} is not one of {STATUSES}",
        )

        # A row claiming to be fixed must say what fixed it, or nobody can
        # check whether the fix is still there.
        if row.get("status") == "fixed":
            check(row.get("fixed_by"), f"{rid}: status is 'fixed' but fixed_by is missing")

        # ADR-0015: a divergence that lets incorrect code look correct is only
        # handled if the learner is warned where they meet it.
        if row.get("hides_mistake"):
            check(
                row.get("warn_in"),
                f"{rid}: hides_mistake is set but warn_in names no exercise",
            )

        # Both languages or neither. A row with one is a fact written down
        # once and a half.
        check(
            bool(row.get("renode")) == bool(row.get("renode_ja")),
            f"{rid}: renode and renode_ja must both be present",
        )
        check(
            bool(row.get("board")) == bool(row.get("board_ja")),
            f"{rid}: board and board_ja must both be present",
        )


def check_doc_pairs():
    """Every shipped document has a Japanese partner, and vice versa.

    Documentation in a source repository is bilingual from the first commit on
    this project. A pair that loses one side does not error anywhere, so only
    a check finds it.

    BILINGUAL names the documents that carry both languages in one file and so
    have no partner to lose. Everything not named there is still a pair.
    """
    english, japanese = set(), set()
    for dirpath, dirnames, filenames in os.walk(ROOT):
        dirnames[:] = [d for d in dirnames
                      if d not in GENERATED + ("verify", "tests")]
        for name in filenames:
            if not name.endswith(".md"):
                continue
            rel = os.path.relpath(os.path.join(dirpath, name), ROOT)
            if name.endswith(".ja.md"):
                japanese.add(rel[:-len(".ja.md")])
            else:
                english.add(rel[:-len(".md")])

    exempt = set(os.path.normpath(stem) for stem in BILINGUAL)
    for stem in sorted(english - japanese - exempt):
        check(False, f"docs: {stem}.md has no {stem}.ja.md")
    for stem in sorted(japanese - english - exempt):
        check(False, f"docs: {stem}.ja.md has no {stem}.md")
    check(True, "docs: pairs checked")


ANCHOR = re.compile(r"^<!--\s*section:\s*([a-z0-9][a-z0-9-]*)\s*-->\s*$")
HEADING = re.compile(r"^(#{1,6})\s+(\S.*?)\s*$")


def sections_of(path):
    """Every heading below the title, as (level, id, line, text).

    `id` is read from the `<!-- section: ... -->` comment that must sit
    directly above the heading, and is None when there is none. The ids are
    what makes a comparison between two languages possible at all: the
    heading text cannot be compared, because the whole point of the pair is
    that it differs.

    The anchor has to be the line immediately above, with only blank lines
    between. An anchor separated from its heading by prose is not an anchor
    for it, and treating it as one would let a section be renamed into
    somebody else's identity.
    """
    found = []
    pending = None
    fenced = False
    with io.open(path, encoding="utf-8") as handle:
        for number, line in enumerate(handle, 1):
            if line.startswith("```"):
                fenced = not fenced
                continue
            if fenced:
                continue
            anchor = ANCHOR.match(line)
            if anchor:
                pending = anchor.group(1)
                continue
            head = HEADING.match(line)
            if head is None:
                if line.strip():
                    pending = None
                continue
            level = len(head.group(1))
            if level == 1:
                pending = None
                continue
            found.append((level, pending, number, head.group(2)))
            pending = None
    return found


def check_bilingual_page_structure():
    """The two languages of an exercise's page carry the same sections.

    STRUCTURE, NOT MEANING. This compares the sections and their order and
    nothing else. A mistranslated section passes it, and a section whose two
    languages say different things passes it. Saying so is part of the check:
    ADR-0051 and the 2026-11-19 deletion of three comments that claimed
    checks nobody had written are both about the same failure, which is a
    guard believed to do more than it does.

    Until this existed the only thing verified about a pair was that both
    files are present -- `check_doc_pairs` above, which compares no content.
    A section added to one language and forgotten on the other was invisible.
    That was an editorial problem while both sides were read by people. It is
    more than that now that the Japanese page is given to the assistant: the
    learner and the model would then hold different documents, which is the
    one thing these pages exist to prevent.

    The exercises are discovered rather than listed, so an exercise added
    later is covered without anybody remembering to add it. The other
    bilingual pairs in this repository are NOT covered -- they carry no
    anchors, and `check_doc_pairs` still only asserts both sides exist.
    """
    pages = sorted(glob.glob(os.path.join(ROOT, "exercises", "*", "README.md")))
    check(bool(pages), "exercises: no exercise pages found to compare")

    for english in pages:
        exercise = os.path.basename(os.path.dirname(english))
        japanese = english[:-len(".md")] + ".ja.md"
        if not os.path.isfile(japanese):
            # check_doc_pairs reports the missing partner; nothing to compare.
            continue

        both = {}
        for lang, path in (("en", english), ("ja", japanese)):
            sections = sections_of(path)
            for level, anchor, number, text in sections:
                check(anchor is not None,
                      "%s: %s line %d, heading %r has no "
                      "<!-- section: ... --> above it. Without one the two "
                      "languages cannot be compared at all."
                      % (exercise, os.path.basename(path), number, text))
            ids = [anchor for _, anchor, _, _ in sections]
            duplicated = sorted(set(i for i in ids if i and ids.count(i) > 1))
            for dupe in duplicated:
                check(False, "%s: %s uses the section id %r more than once"
                             % (exercise, os.path.basename(path), dupe))
            both[lang] = [(level, anchor) for level, anchor, _, _ in sections]

        if any(anchor is None for _, anchor in both["en"] + both["ja"]):
            continue

        english_ids = [anchor for _, anchor in both["en"]]
        japanese_ids = [anchor for _, anchor in both["ja"]]

        for missing in [i for i in english_ids if i not in japanese_ids]:
            check(False, "%s: section %r is in README.md and not in "
                         "README.ja.md" % (exercise, missing))
        for missing in [i for i in japanese_ids if i not in english_ids]:
            check(False, "%s: section %r is in README.ja.md and not in "
                         "README.md" % (exercise, missing))

        if sorted(english_ids) == sorted(japanese_ids):
            check(english_ids == japanese_ids,
                  "%s: the sections are in a different order in the two "
                  "languages. README.md has %s; README.ja.md has %s."
                  % (exercise, " -> ".join(english_ids),
                     " -> ".join(japanese_ids)))
            for (en_level, anchor), (ja_level, _) in zip(both["en"],
                                                         both["ja"]):
                if english_ids != japanese_ids:
                    break
                check(en_level == ja_level,
                      "%s: section %r is a level-%d heading in README.md and "
                      "level-%d in README.ja.md"
                      % (exercise, anchor, en_level, ja_level))

    # Says what was compared, not that it matched: this line prints before
    # main() reports failures. And it names the limit, because the thing a
    # reader will otherwise assume is that two pages agreeing structurally
    # means they say the same thing.
    print("exercises: %d page pair(s) compared for sections and their order "
          "-- STRUCTURE ONLY, a mistranslation passes this" % len(pages))


def check_traps_are_cited(rows):
    """Every divergence that hides a mistake is named in the exercise material.

    ADR-0015 says the warning must be where the learner meets it, not only in
    a register written for maintainers. Without this check that decision is an
    intention: the material could quietly stop mentioning a trap and nothing
    would say so.

    Citation is by the divergence's own id, so the link is exact rather than a
    guess at whether some paragraph is about the right thing.

    Each file named in `warn_in` is checked separately. This used to pour
    every exercise file into one string and ask only whether the id appeared
    somewhere in it, which is not the decision ADR-0015 asks for: one mention
    in exercise 4 satisfied it for all four, and `warn_in` -- the field that
    says which material needs the warning -- was not read at all.

    That was not hypothetical. `pin-configuration-not-enforced` was cited in
    exercise 4 and nowhere else, while exercises 1 to 3 have the same trap and
    said nothing. Measured 2026-09-30: firmware that writes only to
    GPIOA->ODR, with no clock enable and no mode register, passes exercise 1's
    own check 3 of 3. A learner could delete both steps of the exercise and be
    told they had done it correctly.

    What this does NOT check: that both language versions carry the warning,
    unless `warn_in` names both. Whether two documents say the same thing is
    not something a string search can settle.
    """
    for row in rows:
        if not row.get("hides_mistake"):
            continue
        rid = row.get("id", "?")
        where = row.get("warn_in") or []
        check(bool(where),
              "%s hides a mistake and warn_in names nothing. Say which "
              "material must carry the warning, or drop the flag." % rid)
        for rel in where:
            path = os.path.join(ROOT, *rel.split("/"))
            if not os.path.isfile(path):
                check(False, "%s: warn_in names %s, which does not exist"
                             % (rid, rel))
                continue
            with io.open(path, encoding="utf-8") as handle:
                body = handle.read()
            check(rid in body,
                  "%s hides a mistake and %s does not name it. A learner "
                  "meets this trap there and is told nothing."
                  % (rid, rel))
    print("traps: cited in every file their warn_in names")


def check_exercise_relevance(rows):
    """Which exercises a row reaches, and whether every exercise is reached.

    `exercises` answers "would a learner doing this exercise want to know".
    `warn_in` answers "which files carry the warning". They are different
    questions, and this project has already paid for conflating them twice.
    The selector feeding the assistant looked for a topic word in `warn_in`,
    which holds paths, so it returned nothing for every exercise for the life
    of the course. And `check_traps_are_cited` above covers only rows flagged
    `hides_mistake`, so `button-polarity` -- the user button is active low on
    hardware and is not in the simulator -- reached nobody, on the one
    exercise that reads the button.

    Three assertions, and the third is what makes the first two mean
    anything. A name matching no directory fails, so renaming an exercise
    cannot quietly select a different set, which is how the old selector was
    correct only by accident of the folder names. Every exercise is reached
    by at least one row, because every exercise drives a GPIO pin and the
    simulator does not enforce pin configuration, so zero is always wrong.
    And the register must be non-empty and contain at least one trap, because
    without that both of the above pass on an empty file -- which is exactly
    how the assistant's selector went unnoticed.
    """
    exercises_dir = os.path.join(ROOT, "exercises")
    here = [name for name in sorted(os.listdir(exercises_dir))
            if os.path.isdir(os.path.join(exercises_dir, name))]

    check(bool(here), "exercises: no exercise directories found")
    check(bool(rows), "register: no rows, so every check over it is vacuous")
    check(any(row.get("hides_mistake") for row in rows),
          "register: no row hides a mistake, so the trap checks above assert "
          "nothing")

    reached = set()
    for row in rows:
        rid = row.get("id", "<no id>")
        named = row.get("exercises")
        if not check(named is not None,
                     "%s: no `exercises` field. Say which exercises it "
                     "reaches, or give it an empty list to say it reaches "
                     "none of them." % rid):
            continue
        for name in named:
            check(name in here,
                  "%s: `exercises` names %s, which is not an exercise "
                  "directory. A rename must fail here rather than silently "
                  "selecting a different set." % (rid, name))
            reached.add(name)

    for name in here:
        check(name in reached,
              "exercises: %s is reached by no divergence row. Every exercise "
              "drives a GPIO pin and the simulator does not enforce pin "
              "configuration, so none is wrong." % name)


def check_links():
    """Every local link in a document points at something that exists.

    Documents get renamed and links do not follow. Nothing errors when that
    happens: a reader simply lands nowhere, and the person it fails for is the
    one who did not already know where to go.
    """
    pattern = re.compile(r"\[[^\]]*\]\(([^)]+)\)")
    checked = 0
    for dirpath, dirnames, filenames in os.walk(ROOT):
        dirnames[:] = [d for d in dirnames if d not in GENERATED + ("lib",)]
        for name in filenames:
            if not name.endswith(".md"):
                continue
            path = os.path.join(dirpath, name)
            with io.open(path, encoding="utf-8") as handle:
                body = handle.read()
            for target in pattern.findall(body):
                target = target.split("#")[0].strip()
                if not target or "://" in target or target.startswith("mailto:"):
                    continue
                resolved = os.path.normpath(os.path.join(dirpath, target))
                checked += 1
                check(os.path.exists(resolved),
                      "%s links to %s, which does not exist"
                      % (os.path.relpath(path, ROOT), target))
    print("docs: %d local links checked" % checked)



def check_the_learners_check_ignores_tags():
    """`on: push` in check-my-work.yml must name branches, not everything.

    A bare `push:` fires on tag pushes too, and the course creates one tag
    per passing build when it publishes the firmware as a release on a
    learner's repository. A GitHub App's token starts workflows where the
    automatic GITHUB_TOKEN would not, so that tag started this workflow.

    Measured once, on 2026-11-02, which is why this check exists: a
    learner who had just passed got a run against
    `ref=passed/01-blink-with-a-delay`, costing a billed minute nobody
    asked for and showing a red cross moments after they were told they
    had passed.

    One assertion rather than one per line: this is a property of the
    file, and a per-line check would report the same fault many times.
    """
    path = os.path.join(ROOT, ".github", "workflows", "check-my-work.yml")
    with io.open(path, encoding="utf-8") as handle:
        body = handle.read()
    live = [line for line in body.splitlines()
            if line.strip() and not line.lstrip().startswith("#")]
    try:
        at = next(i for i, line in enumerate(live) if line.startswith("on:"))
    except StopIteration:
        check(False, "check-my-work.yml has no `on:` block")
        return
    block = "\n".join(live[at:at + 6])
    check("branches:" in block,
          "check-my-work.yml triggers on a bare push, so the course's "
          "passed/<exercise> tag will start a learner's own check")

def check_grading_is_automatic_and_the_learner_can_stop_it():
    """Graded on every push by default, and the learner can switch it off.

    Four properties of three files, all of which fail silently and
    expensively rather than loudly:

      - the template MUST ship `.grade-on-push`, because a learner who is
        not graded until they find a file they were never told about is
        not being graded. The allowance of ten a day is what bounds the
        cost of that, rather than the learner's ignorance of a switch.

        This asserted the opposite until 2026-11-09 -- that the template
        must NOT ship it -- which was right until
        `grade-on-push-by-default` inverted the default and was not
        updated with it. `sweep.yml` runs `on: push`, so the course
        repository's own sweep was red on every push from that day, and
        nothing reports on it.

      - the marker must stay the learner's own: not in `.gitignore`, so
        that deleting it is a commit that persists rather than a local
        change the next pull undoes.
      - the dispatch step must be `continue-on-error`. Without it, a
        course that cannot be reached turns a learner's passing compile
        check red, which tells them their code is wrong. It is not.
      - it must be `if: always()`, so that code which does not compile is
        still sent. Somebody stuck on a compiler error is exactly who
        needs a written explanation on their Issue.
      - both workflows must read the credential by the one name the
        grading secret is set under. A typo here 404s every request
        and says nothing to anybody.
    """
    marker = os.path.join(ROOT, ".grade-on-push")
    check(os.path.exists(marker),
          ".grade-on-push is missing from the course template, so a newly "
          "enrolled learner would not be graded until they found a file "
          "nothing told them about")

    # Not ignored. A marker the learner cannot delete in a way that
    # survives is not theirs: `git rm` has to be a commit the course's
    # own refresh will not quietly undo.
    ignore = os.path.join(ROOT, ".gitignore")
    ignored = ""
    if os.path.isfile(ignore):
        with io.open(ignore, encoding="utf-8") as handle:
            ignored = handle.read()
    check(".grade-on-push" not in ignored,
          ".grade-on-push is in .gitignore, so a learner who deletes it "
          "has made a change that does not persist and automatic grading "
          "comes back")

    path = os.path.join(ROOT, ".github", "workflows", "check-my-work.yml")
    with io.open(path, encoding="utf-8") as handle:
        body = handle.read()
    live = [line for line in body.splitlines()
            if line.strip() and not line.lstrip().startswith("#")]
    try:
        at = next(i for i, line in enumerate(live)
                  if line.strip() == "- name: Ask for feedback")
    except StopIteration:
        check(False, "check-my-work.yml has no 'Ask for feedback' step, so "
                     "pushing can never ask the course for anything")
        return
    block = "\n".join(live[at:at + 8])
    check("continue-on-error: true" in block,
          "the 'Ask for feedback' step is not continue-on-error, so a "
          "course it cannot reach will turn a passing check red")
    check("if: always()" in block,
          "the 'Ask for feedback' step is not `if: always()`, so code "
          "that does not compile is never sent for feedback -- which is "
          "the learner who most needs it")

    button = os.path.join(ROOT, ".github", "workflows", "ask-for-feedback.yml")
    check(os.path.exists(button),
          "there is no ask-for-feedback.yml, so a learner cannot ask for "
          "feedback without pushing")
    if not os.path.exists(button):
        return
    with io.open(button, encoding="utf-8") as handle:
        asked = handle.read()
    for name, text in (("check-my-work.yml", body),
                       ("ask-for-feedback.yml", asked)):
        check("secrets.COURSE_GRADE_TRIGGER" in text,
              "%s does not read secrets.COURSE_GRADE_TRIGGER, so its "
              "requests will 404 and say nothing" % name)


def check_no_bom():
    """No byte-order mark in the files Renode parses.

    A BOM is invisible in an editor and survives copy and paste. Some tools on
    Windows add one without being asked -- PowerShell's Out-File does. It is
    worth one check rather than an afternoon.
    """
    for dirpath, dirnames, filenames in os.walk(ROOT):
        dirnames[:] = [d for d in dirnames if d not in GENERATED]
        for name in filenames:
            if not name.endswith((".repl", ".resc")):
                continue
            path = os.path.join(dirpath, name)
            with open(path, "rb") as handle:
                head = handle.read(3)
            check(head != b"\xef\xbb\xbf",
                  "%s starts with a byte-order mark"
                  % os.path.relpath(path, ROOT))
    check(True, "no byte-order marks")


def check_documented_commands():
    """The commands the documents give must do what they say.

    Two of them did not, and both failed by appearing to work.

    A `docker run` that maps only 8000 gives a page that loads and then shows
    an empty board: the drawing is served over 8000 and everything on it --
    pins, LEDs, sensor readings -- arrives over 9001. It reads as the drawing
    being broken.

    `-e "$bin=@..."` in double quotes lets the shell expand `$bin` to nothing
    before Renode sees it, leaving `=@...`, which is not a command. Renode
    abandons the whole line, so board.resc never runs and nothing loads.

    This used to say the simulator started and silently ran the self-test.
    Measured on 1.16.1 it does not start at all -- the line dies on
    `No such command or device: =`. The silent case is the positional form
    below, where the board does come up running the wrong firmware.
    """
    # tools/ is in scope because that is where this check was missed.
    # tools/build.sh printed the double-quoted, positional form -- both
    # faults described above, in one line -- from the day this check was
    # written until 2026-10-27. It was found by following the handover
    # document against a package, not by anything here, because the only
    # files searched were documents and the two the faults were found in.
    # A command is as published in a script's usage comment as in a .md,
    # and more likely to be copied: it is the line sitting on screen
    # directly after the build the learner just ran.
    paths = sorted(glob.glob(os.path.join(ROOT, "*.md"))
                   + glob.glob(os.path.join(ROOT, "exercises", "*.md"))
                   + glob.glob(os.path.join(ROOT, "tools", "*.sh"))
                   + glob.glob(os.path.join(ROOT, "tools", "*.ps1"))
                   + glob.glob(os.path.join(ROOT, "tools", "*.py"))
                   + [os.path.join(ROOT, "Dockerfile"),
                      os.path.join(ROOT, "board.resc")])
    runs = binds = 0
    for path in paths:
        rel = os.path.relpath(path, ROOT)
        for number, line in enumerate(io.open(path, encoding="utf-8"), 1):
            if "docker run" in line and "nucleo-f401re" in line:
                runs += 1
                for port in ("8000:8000", "9001:9001"):
                    check(port in line,
                          "%s:%d documents a docker run without -p %s. The "
                          "board view needs both: the page is on 8000, its "
                          "data on 9001" % (rel, number, port))
            if "$bin=@" in line:
                binds += 1
                check('"$bin=@' not in line,
                      "%s:%d quotes $bin with double quotes. The shell eats "
                      "it, Renode rejects the line, and nothing loads at all"
                      % (rel, number))
                # Renode runs a script named on the command line before any
                # -e, so setting $bin in a -e alongside a positional
                # board.resc sets it after the board has already loaded. The
                # board then takes its own default, which is the self-test.
                # A comment marker first: these commands are published in
                # shell comments (#) and in .resc comments (:) as often as
                # in prose, and a wrong command teaches the same wrong
                # thing whichever one it sits behind.
                bare = line.strip().lstrip("#:").strip()
                if bare.startswith("renode"):
                    positional = re.search(r"renode\s+(?:--\S+\s+)*board\.resc",
                                           line)
                    check(positional is None,
                          "%s:%d passes board.resc positionally and sets $bin "
                          "in a -e. Renode runs the script first, so the "
                          "board loads the self-test instead. Use -e for both"
                          % (rel, number))

    check(runs > 0, "no docker run command is documented anywhere")
    check(binds > 0, "no example of passing $bin is documented anywhere")
    print("commands: %d docker runs and %d firmware arguments checked"
          % (runs, binds))

    # And the container route asks a learner to type neither of them.
    #
    # The commands are not gone: NATIVE-SETUP.md is built on them, tools
    # publish their own usage, and both still work inside the container. So
    # everything above would be perfectly happy to see them reappear in
    # SETUP, where following them now means doing by hand what the page does
    # for you -- and where this check was watching the wrong thing until
    # 2026-11-11. What the change was about was this one route, so this is
    # what gets asserted about it.
    for name in ("SETUP.md", "SETUP.ja.md"):
        with open(os.path.join(ROOT, name), encoding="utf-8") as handle:
            body = handle.read()
        for typed, instead in (
                ("tools/build.sh exercises", "the board view builds it"),
                ("renode --console -e", "the board view starts the board")):
            check(typed not in body,
                  "%s tells a learner to type `%s`, but %s. The command still "
                  "works and NATIVE-SETUP.md is where it belongs"
                  % (name, typed, instead))
    print("commands: SETUP asks a learner to type neither a build nor a run")


def check_line_endings():
    """No carriage return in anything Linux has to read.

    A shell script whose shebang ends `#!/bin/sh\\r` cannot be run: the kernel
    looks for an interpreter of that name, does not find one, and the shell
    reports

        cannot execute: required file not found

    which names neither the script nor the reason. This is what a Windows
    learner met on the first command inside the container.

    Nothing was wrong with what git stored -- the blobs have always been LF.
    Git converted them on checkout, because core.autocrlf defaults to true on
    Windows and no .gitattributes said otherwise. So the repository looked
    correct to everybody who could have noticed, and broke only for the people
    it happened to. .gitattributes now pins eol=lf; this asserts the result on
    disk, which is the thing a learner actually runs.

    PowerShell is excluded: it is read only on Windows, where CRLF is the
    convention, and .gitattributes pins it the other way on purpose.
    """
    checked = 0
    for dirpath, dirnames, filenames in os.walk(ROOT):
        dirnames[:] = [d for d in dirnames if d not in GENERATED]
        for name in filenames:
            if name.endswith((".ps1", ".elf", ".bin", ".hex", ".png", ".pdf")):
                continue
            path = os.path.join(dirpath, name)
            try:
                with open(path, "rb") as handle:
                    body = handle.read()
            except OSError:
                continue
            if b"\0" in body[:8000]:
                continue                       # binary, whatever its name
            checked += 1
            check(b"\r" not in body,
                  "%s has CRLF line endings. Anything Linux parses must be LF "
                  "- see .gitattributes" % os.path.relpath(path, ROOT))
    print("line endings: %d files checked for CRLF" % checked)


def check_unit_tests():
    """The pure functions that have tests, run as part of the sweep.

    Added when the board-file editor turned out to be wrong: removing a
    part a learner had added left orphaned lines and the board stopped
    loading. That logic is pure and testable, and nothing here was
    running its tests.
    """
    done = subprocess.run([sys.executable, "-m", "pytest", "tests", "-q",
                           "--no-header"],
                          cwd=ROOT, capture_output=True, text=True,
                          encoding="utf-8", errors="replace")
    if "no tests ran" in (done.stdout or "") and done.returncode != 0:
        check(True, "no unit tests present")
        print("unit tests: none")
        return

    # stderr as well as stdout. When pytest is not installed at all it says so
    # on stderr and prints nothing on stdout, so this check failed with an
    # empty message -- red on every push from 2026-09-29, and the build log
    # said only "unit tests failed:" with nothing after the colon. A check
    # that cannot say why it failed wastes exactly the time it was meant to
    # save.
    said = ((done.stdout or "") + (done.stderr or "")).strip()
    check(done.returncode == 0,
          "unit tests failed:\n" + (said[-1500:] or
                                    "(pytest produced no output at all; "
                                    "exit code %d)" % done.returncode))
    tail = [l.strip() for l in (done.stdout or "").splitlines()
            if "passed" in l or "failed" in l]
    print("unit tests: %s" % (tail[-1] if tail else "ran"))


def check_scripts_are_executable():
    """Every shell script must carry the executable bit in git.

    Windows sets core.filemode=false, so `chmod +x` on a checkout here
    changes nothing that reaches a commit. A script added from this machine
    therefore arrives on the Linux runner as mode 100644 and fails with
    'Permission denied', exit 126 -- which is what happened, ten runs in a
    row, and it is invisible in a diff. The fix is
    `git update-index --chmod=+x <path>`; this is what notices it was
    forgotten.
    """
    # git is not installed in the course container, which is where CI runs
    # this. A missing git raises rather than returning non-zero, and an
    # unhandled exception here would take down the whole sweep -- it did.
    try:
        listing = subprocess.run(["git", "ls-files", "-s", "--", "*.sh"],
                                 cwd=ROOT, capture_output=True, text=True)
    except OSError:
        check(True, "git is not available, so file modes were not checked")
        print("scripts: NOT checked (no git here)")
        return
    if listing.returncode != 0:
        check(True, "not a git checkout, so file modes were not checked")
        print("scripts: NOT checked (not a git checkout)")
        return
    counted = 0
    for line in listing.stdout.splitlines():
        if not line.strip():
            continue
        mode, rest = line.split(" ", 1)
        path = rest.split("\t", 1)[-1]
        counted += 1
        check(mode == "100755",
              "%s is mode %s in git, not 100755. It will fail with "
              "'Permission denied' on Linux. Fix with: "
              "git update-index --chmod=+x %s" % (path, mode, path))
    print("scripts: %d shell script(s) checked for the executable bit"
          % counted)


def find_renode(explicit):
    if explicit:
        return explicit
    guesses = [
        os.path.join(ROOT, "..", "..", "tools", "renode",
                     "renode_1.16.1-dotnet_portable", "renode.exe"),
        os.path.join(ROOT, "..", "tools", "renode",
                     "renode_1.16.1-dotnet_portable", "renode.exe"),
    ]
    for guess in guesses:
        if os.path.isfile(guess):
            return os.path.abspath(guess)
    return None


def run_renode(renode):
    """Load the board and report the values the 'fixed' rows claim."""
    script = "\n".join([
        'mach create "sweep"',
        "machine LoadPlatformDescription @boards/nucleo_f401re.repl",
        'echo "FLASH"', "sysbus.flash Size",
        'echo "SRAM"', "sysbus.sram Size",
        'echo "CPU"', "sysbus.cpu Model",
        'echo "TIMER2"', "sysbus.timer2 Frequency",
        'echo "PERIPHERALS"', "peripherals",
        "",
    ])
    handle, path = tempfile.mkstemp(suffix=".resc")
    try:
        with os.fdopen(handle, "w") as out:
            out.write(script)
        result = subprocess.run(
            [renode, "--console", "--disable-xwt", "--plain",
             "-e", "i @" + path.replace("\\", "/"), "-e", "quit"],
            cwd=ROOT, capture_output=True, text=True, timeout=300,
            # Renode's console banner carries bytes from the Windows code
            # page, and text=True decodes with whatever the locale says.
            # Under `python -X utf8` that decode fails -- on 0xb3, in a
            # box-drawing rule -- inside subprocess's reader thread, where
            # the exception is printed and dropped. What reaches here is
            # stdout=None, and the next line raises TypeError on it: a
            # UTF-8 flag on the command line, reported as an unrelated bug
            # 20 frames away. Nothing in the output is read for its
            # characters, only grepped for labels, so a replaced byte
            # costs nothing and a strict decode costs an afternoon.
            errors="replace",
        )
        return result.stdout + result.stderr
    finally:
        os.unlink(path)


def value_after(output, label):
    """The first non-empty, non-log line following an echoed label."""
    lines = output.splitlines()
    for index, line in enumerate(lines):
        if line.strip() == label:
            for candidate in lines[index + 1:]:
                candidate = candidate.strip()
                if candidate and not re.match(r"^\d{2}:\d{2}:\d{2}", candidate):
                    return candidate
    return None


def check_board(output):
    # These mirror the fixed_by claims in divergences.json. If a row's fix is
    # reverted, the sweep must name it rather than quietly passing.
    check(value_after(output, "FLASH") == "0x0000000000080000",
          "oversized-flash: flash is not 512 KB "
          f"(got {value_after(output, 'FLASH')})")

    check(value_after(output, "SRAM") == "0x0000000000018000",
          "oversized-sram: SRAM is not 96 KB "
          f"(got {value_after(output, 'SRAM')})")

    check(value_after(output, "CPU") == "cortex-m4f",
          "missing-fpu: core is not cortex-m4f "
          f"(got {value_after(output, 'CPU')})")

    check(value_after(output, "TIMER2") == "0x000000000501BD00",
          "declared-clock-rate: TIM2 is not 84 MHz "
          f"(got {value_after(output, 'TIMER2')})")

    # button-polarity's fix is the invert flag, which is not readable as a
    # property; its presence in the board description is what the firmware
    # test exercises. Assert the wiring exists at least.
    check("led" in output, "board wiring: no LED in the peripheral tree")
    check("button" in output, "button-polarity: no button in the peripheral tree")
    # The other direction from the rest of these: the fix was taking something
    # out. A sensor back on the board would look harmless -- every exercise
    # would still pass -- and would put a part on every learner's board that
    # the board in their hand does not have.
    check("si7021" not in output,
          "si7021-not-fitted: the board declares a sensor on I2C1, and a real "
          "NUCLEO-F401RE carries none")


def check_exercise_checks_discriminate():
    """Every shipped behaviour check must reject the untouched scaffolding.

    A check that passes whatever it is given is worse than no check: it
    tells a learner their empty exercise is correct, and it tells a teacher
    the cohort is doing fine. The scaffolding is the one submission we know
    is not finished, so it is the one case we can assert without shipping a
    solution -- which we must never do, because the solution is the
    exercise.

    Exit 2 is accepted as well as 1. It means the check could not observe
    the program, which is honest; what is not acceptable is exit 0.

    But an exit 2 is not a verification either, and this used to count it as
    one: with no simulator present every check exits 2, every assertion
    below holds, and the line printed at the end claimed four checks had
    been verified to reject unfinished work when none had been run. A check
    broken into permanent exit 2 is indistinguishable from one that
    discriminates, which is the opposite of what this exists to detect.

    So the two outcomes are counted separately and the summary says which
    it got. If nothing was observed at all, that is a failure: this project
    has shipped a sweep that reported a problem and exited 0 before, and
    "verified nothing, said it verified four" is the same fault.
    """
    exercises = sorted(glob.glob(os.path.join(ROOT, "exercises", "*", "check.py")))
    if not exercises:
        print("exercise checks: none shipped")
        return

    rejected, unobserved = [], []

    for check_py in exercises:
        directory = os.path.dirname(check_py)
        name = os.path.basename(directory)
        rel = os.path.join("exercises", name)

        built = subprocess.run(
            [_bash(), os.path.join("tools", "build.sh"), rel],
            cwd=ROOT, capture_output=True, encoding="utf-8",
            errors="replace", timeout=300)
        if not check(built.returncode == 0,
                     "exercise checks: %s scaffolding does not compile" % name):
            continue

        # UTF-8 explicitly: these checks speak Japanese, and the locale
        # codec on a Windows machine mangles it or fails outright.
        done = subprocess.run(
            [sys.executable, os.path.join(rel, "check.py"),
             "--elf", os.path.join(rel, "firmware.elf")],
            cwd=ROOT, capture_output=True, encoding="utf-8",
            errors="replace", timeout=600)
        if not check(done.returncode != 0,
                     "exercise checks: %s/check.py PASSES the untouched "
                     "scaffolding. It is not testing anything.\n%s"
                     % (name, (done.stdout or "")[-600:])):
            continue
        if done.returncode == 2:
            unobserved.append(name)
        else:
            rejected.append(name)
            # AND NOT ONE VERDICT MAY SAY 成功 ON IT.
            #
            # The exit code is the whole verdict only to the grader. A
            # learner reads the lines, and so does the assistant, which is
            # sent this output verbatim. The untouched scaffolding does
            # nothing at all, so every line should be 失敗 -- and a line
            # that says 成功 here is a verdict that reported a pass without
            # observing anything.
            #
            # That is not hypothetical. Until 2026-11-20 three verdicts did
            # it: exercise 2's and exercise 3's 「点滅はタイマーによって
            # 作られている」 (stopping a timer that was never started
            # changes nothing, which is indistinguishable from a correct
            # program) and exercise 4's 「暖かくなるほど点灯数が減らない」
            # and 「同じ温度に戻ると表示も戻る」 (nothing falls in a row of
            # zeroes, and zero equals zero). None let anybody pass, because
            # a prerequisite verdict failed in the same run -- which is
            # exactly why the exit code could not catch them and why this
            # reads the lines instead.
            passed = [line for line in (done.stdout or "").splitlines()
                      if line.startswith("  成功  ")]
            check(not passed,
                  "exercise checks: %s/check.py reports 成功 on the "
                  "untouched scaffolding, which does nothing at all. A "
                  "verdict that passes without observing anything "
                  "misdirects the learner and the assistant both:\n%s"
                  % (name, "\n".join(passed)))

    check(bool(rejected),
          "exercise checks: not one check observed the program (%s). Every "
          "one exited 2, so nothing here was verified -- most likely the "
          "simulator is missing. Reporting this as a pass is what the check "
          "exists to prevent." % ", ".join(unobserved))

    print("exercise checks: %d rejected unfinished work%s"
          % (len(rejected),
             (", %d could not observe it (%s)"
              % (len(unobserved), ", ".join(unobserved)))
             if unobserved else ""))


def check_the_guarantees_hold():
    """Every guarantee checklib declares must be demonstrated, not asserted.

    The check above proves each check rejects the untouched scaffolding,
    which proves only that it is not vacuous. This proves the harder
    direction: a program that produces the right observable the WRONG way
    is rejected too.

    That is the whole content of the 'causal-checks' guarantee, and the
    guarantee is recorded against verdicts and used to mark which passes
    predate it. A declaration nothing demonstrates would be the fourth of
    the comments removed on 2026-11-19 that claimed checks nobody had
    written, and the worst of them, because more people would rely on it.

    So this does not read the declaration and does not assert that it
    names four exercises. It runs the fakes.

    Exit 2 is counted separately from exit 1 and demonstrating nothing is
    a failure, for the reason check_exercise_checks_discriminate() states
    at length: a sweep that reports four guarantees proved while the
    simulator was absent is the fault this exists to prevent.
    """
    if "causal-checks" not in CHECKLIB.GUARANTEES:
        print("guarantees: 'causal-checks' not declared, nothing to prove")
        return

    exercises = sorted(glob.glob(os.path.join(ROOT, "exercises", "*", "check.py")))
    fakes_root = os.path.join(ROOT, "tests", "fixtures", "fakes")

    rejected, unobserved, accepted = [], [], []

    for check_py in exercises:
        name = os.path.basename(os.path.dirname(check_py))
        mine = sorted(glob.glob(os.path.join(fakes_root, name, "*", "main.c")))
        if not check(bool(mine),
                     "guarantees: %s declares 'causal-checks' and has no "
                     "program that cheats in tests/fixtures/fakes/%s/. The "
                     "guarantee would be claimed and never demonstrated."
                     % (name, name)):
            continue

        for main_c in mine:
            fake = os.path.dirname(main_c)
            label = "%s/%s" % (name, os.path.basename(fake))
            rel = os.path.relpath(fake, ROOT)

            built = subprocess.run(
                [_bash(), os.path.join("tools", "build.sh"), rel],
                cwd=ROOT, capture_output=True, encoding="utf-8",
                errors="replace", timeout=300)
            if not check(built.returncode == 0,
                         "guarantees: %s does not compile, so nothing about "
                         "%s was demonstrated.\n%s"
                         % (label, name, (built.stdout or "")[-400:])):
                continue

            done = subprocess.run(
                [sys.executable, os.path.join("exercises", name, "check.py"),
                 "--elf", os.path.join(rel, "firmware.elf")],
                cwd=ROOT, capture_output=True, encoding="utf-8",
                errors="replace", timeout=900)

            if done.returncode == 2:
                unobserved.append(label)
            elif done.returncode == 0:
                accepted.append(label)
                check(False,
                      "guarantees: %s ACCEPTS %s, which does not do the "
                      "exercise. 'causal-checks' is declared and is not "
                      "true.\n%s"
                      % (name, label, (done.stdout or "")[-700:]))
            else:
                rejected.append(label)

    check(bool(rejected),
          "guarantees: not one check observed a program that cheats (%s). "
          "Every one exited 2, so 'causal-checks' was demonstrated nowhere "
          "-- most likely the simulator is missing. Reporting that as proof "
          "is what this check exists to prevent." % ", ".join(unobserved))

    print("guarantees: causal-checks demonstrated on %d program(s) that "
          "cheat%s"
          % (len(rejected),
             (", %d could not be observed (%s)"
              % (len(unobserved), ", ".join(unobserved)))
             if unobserved else ""))


def _bash():
    """Git's bash on Windows; plain bash elsewhere. The `bash` on PATH under
    Windows is often WSL's shim, which cannot see this filesystem."""
    if os.name == "nt":
        for candidate in (r"C:\Program Files\Git\bin\bash.exe",
                          r"C:\Program Files (x86)\Git\bin\bash.exe"):
            if os.path.isfile(candidate):
                return candidate
    return shutil.which("bash") or "bash"


def check_container():
    """Build the container and run the environment check inside it.

    ADR-0014 makes the container a supported route rather than a fallback,
    because Intel Macs have no other one. A supported route that nothing
    exercises stops working without anybody noticing, and the people who would
    find out first are the learners who depend on it.
    """
    build = subprocess.run(
        ["docker", "build", "-t", "nucleo-f401re:sweep", "."],
        cwd=ROOT, capture_output=True, text=True, timeout=1800,
    )
    if not check(build.returncode == 0, "container: image did not build"):
        print(build.stderr[-2000:])
        return

    # Deliberately 'bash -c' and not 'bash -lc'. A login shell re-reads
    # /etc/profile, which replaces PATH and hides both tools.
    run = subprocess.run(
        ["docker", "run", "--rm", "nucleo-f401re:sweep",
         "bash", "-c", "cd /work 2>/dev/null; command -v renode && command -v arm-none-eabi-gcc"],
        capture_output=True, text=True, timeout=600,
    )
    check("renode" in run.stdout, "container: renode is not on PATH in the image")
    check("arm-none-eabi-gcc" in run.stdout,
          "container: the cross-compiler is not on PATH in the image")


ARCHIVE = re.compile(r"`(renode-[0-9][^`]*?\.(?:zip|tar\.gz|dmg))`")


def check_download_names():
    """Every Renode archive the setup documents name must exist upstream.

    Needs the network, so it is opt-in. It is here because the Windows row
    said `renode-1.16.1.windows-portable.zip`, which has never existed --
    the asset is `renode-1.16.1.windows-portable-dotnet.zip`. The release
    page lists a dozen similar names and the wrong one is not obviously
    wrong; the only way to know is to ask. A learner following the document
    would have hunted for a missing file on the most common platform we
    have, and nothing else here would have caught it.
    """
    import json as _json
    import urllib.request

    version = None
    with io.open(os.path.join(ROOT, "versions.env"), encoding="utf-8") as h:
        for line in h:
            if line.startswith("RENODE_VERSION="):
                version = line.split("=", 1)[1].strip()
    if not check(version, "versions.env does not name a Renode version"):
        return

    url = ("https://api.github.com/repos/renode/renode/releases/tags/v%s"
           % version)
    headers = {"Accept": "application/vnd.github+json",
               "User-Agent": "nucleo-f401re-sweep"}
    # Only to avoid the unauthenticated rate limit, which a shared CI runner's
    # IP can already have exhausted. The endpoint itself is public, and this
    # works without a token from a development machine.
    token = os.environ.get("GITHUB_TOKEN")
    if token:
        headers["Authorization"] = "Bearer " + token
    try:
        request = urllib.request.Request(url, headers=headers)
        with urllib.request.urlopen(request, timeout=60) as response:
            assets = {a["name"] for a in _json.load(response)["assets"]}
    except Exception as exc:
        check(False, "downloads: could not read the Renode release: %s" % exc)
        return

    named = set()
    for name in ("NATIVE-SETUP.md", "NATIVE-SETUP.ja.md"):
        path = os.path.join(ROOT, name)
        if not os.path.isfile(path):
            continue
        with io.open(path, encoding="utf-8") as handle:
            for found in ARCHIVE.findall(handle.read()):
                named.add((name, found))

    check(bool(named), "downloads: no archive names found in the setup docs")
    for document, asset in sorted(named):
        check(asset in assets,
              "downloads: %s tells a learner to download %r, which is not on "
              "the Renode v%s release page" % (document, asset, version))
    print("downloads: %d archive name(s) checked against the release page"
          % len(named))


def check_windows_commands():
    """A Windows command must be its own block, and must run on a stock machine.

    Two ways the documents used to hand a Windows learner something that fails.

    The first is offering the Windows form as a trailing comment inside a shell
    block -- `./tools/check-container.sh  # Windows: tools\\check-container.ps1`.
    A reader on Windows copies the line, comment and all, into the prompt they
    already have open, and cmd answers `'.' is not recognized`. It names the
    dot, not the platform, so it reads as the course being broken.

    The second is telling them to run a .ps1 by path. A Windows machine nobody
    has changed has its execution policy set to Restricted and refuses, and
    that refusal names the policy rather than the script.
    """
    docs = sorted(glob.glob(os.path.join(ROOT, "*.md"))
                  + glob.glob(os.path.join(ROOT, "exercises", "*.md")))
    seen = 0
    for path in docs:
        rel = os.path.relpath(path, ROOT)
        for number, line in enumerate(io.open(path, encoding="utf-8"), 1):
            stripped = line.strip()

            # A command line that also mentions Windows in a comment.
            if stripped.startswith("./") and "#" in stripped:
                check("Windows" not in stripped.split("#", 1)[1],
                      "%s:%d offers the Windows command as a trailing comment. "
                      "It gets pasted whole - give it its own block"
                      % (rel, number))

            if ".ps1" not in stripped:
                continue
            seen += 1
            # Inside a code block, a .ps1 has to carry the policy argument.
            # Prose mentioning a script by name is fine.
            looks_like_a_command = (stripped.startswith(".\\")
                                    or stripped.startswith("powershell ")
                                    or stripped.startswith("tools\\"))
            if looks_like_a_command:
                check("-ExecutionPolicy Bypass" in stripped,
                      "%s:%d runs a .ps1 without -ExecutionPolicy Bypass. A "
                      "stock Windows machine refuses, naming the policy rather "
                      "than the script" % (rel, number))

    # A command under a Windows heading has to work in the shell the reader
    # is in. `$PWD` is not a cmd.exe variable and not a PowerShell one either
    # in that spelling; docker took it literally and reported an invalid
    # volume name, which reads as the image being wrong rather than the
    # command. Each shell gets its own block, and this refuses a block that
    # promises Windows and gives a Unix variable.
    for path in docs:
        rel = os.path.relpath(path, ROOT)
        heading = None
        for number, line in enumerate(io.open(path, encoding="utf-8"), 1):
            stripped = line.strip()
            if stripped.startswith("**") and stripped.endswith("**"):
                heading = stripped.strip("*")
            elif stripped.startswith("#"):
                heading = None
            if heading and "Windows" in heading and "$PWD" in stripped:
                check(False,
                      "%s:%d is under \"%s\" and uses $PWD, which neither "
                      "Command Prompt nor PowerShell expands"
                      % (rel, number, heading))

    print("windows: %d PowerShell references checked in %d documents"
          % (seen, len(docs)))


def check_board_view():
    """The drawing and the plugin that feeds it must still agree.

    Three things, none of which errs anywhere when it goes wrong.

    A reference to a gradient or filter that was never defined draws nothing
    at all -- silently, with no console message. The page this one was ported
    from asked for url(#chip) and defined no #chip, so every sensor on it had
    a transparent hole where its chip belongs, and had for as long as anyone
    had been looking at it.

    A message the plugin sends and the page ignores is a fact the learner is
    never shown. A verb the page sends and the plugin ignores is a control
    that does nothing when clicked. Both halves pass their own tests either
    way, because neither half is wrong on its own.
    """
    page_path = os.path.join(ROOT, "vis", "index.html")
    plugin_path = os.path.join(ROOT, "vis", "vis_f401re.py")
    page = io.open(page_path, encoding="utf-8").read()
    plugin = io.open(plugin_path, encoding="utf-8").read()

    defined = set(re.findall(r'\bid="([A-Za-z0-9_-]+)"', page))
    for ref in sorted(set(re.findall(r"url\(#([A-Za-z0-9_-]+)\)", page))):
        check(ref in defined,
              "board view: url(#%s) is referenced but nothing defines it - "
              "the shape using it draws as nothing, without erring" % ref)

    # What the plugin sends, in either of the two shapes it writes.
    sends = set(re.findall(r'send_(?:to|message)\(\s*(?:client,\s*)?"([A-Z]+)\|',
                           plugin))
    sends |= set(re.findall(r'"\|"\.join\(\["([A-Z]+)"', plugin))
    handled = set(re.findall(r'type === "([A-Z]+)"', page))
    for kind in sorted(sends - handled):
        check(False, "board view: the plugin sends %s and the page does "
                     "nothing with it" % kind)

    # What the page sends, against what message_received understands.
    at = plugin.index("def message_received(")
    body = plugin[at:plugin.index("\ndef ", at + 1)]
    verbs = set(re.findall(r'verb == "([a-z]+)"', body))
    for group in re.findall(r"verb in \(([^)]*)\)", body):
        verbs |= set(re.findall(r'"([a-z]+)"', group))
    for verb in sorted(set(re.findall(r'send\("([a-z]+)', page))):
        check(verb in verbs,
              "board view: the page sends '%s' and the plugin ignores it - "
              "whatever control sends it does nothing" % verb)

    # IronPython's json cannot serialise a unicode character between U+0080 and
    # U+00FF: it reaches for the machine's code page, which inside Renode calls
    # itself 'unknown', and raises. A degree sign in the part catalogue took
    # the whole layout message with it -- the page drew an empty board, and the
    # only sign of it was one line in Renode's console. Japanese is above that
    # range and is fine; it is only this window that has to be written as
    # escapes.
    for char in sorted(set(c for c in plugin if 0x80 <= ord(c) <= 0xFF)):
        check(False,
              "board view: %s carries U+%04X (%s) as a literal. IronPython's "
              "json cannot encode that range - write it as UTF-8 byte escapes "
              "instead, or the whole board layout fails to send"
              % (os.path.relpath(plugin_path, ROOT), ord(char), repr(char)))

    # The page carries its Japanese and its English in one block, the same way
    # a divergence row carries both. That only holds if they stay in step: a
    # key added to one and not the other falls back to English silently, so a
    # Japanese page would show one English sentence among the rest and nothing
    # would report it.
    labels = re.search(
        r'<script type="application/json" id="vis-labels">(.*?)</script>',
        page, re.S)
    check(labels is not None, "board view: the page has no vis-labels block")
    if labels:
        try:
            both = json.loads(labels.group(1))
        except ValueError as e:
            both = None
            check(False, "board view: vis-labels is not valid JSON - %s" % e)
        if both:
            ja, en = set(both.get("ja", {})), set(both.get("en", {}))
            for key in sorted(en - ja):
                check(False, "board view: '%s' has English and no Japanese" % key)
            for key in sorted(ja - en):
                check(False, "board view: '%s' has Japanese and no English" % key)

    # The fourth exercise reads a sensor the learner has to add themselves, and
    # the setup self-test reads one it brings itself. Those are two separate
    # declarations of the same part, and if their addresses drift the exercise
    # stops working while every test still passes -- the self-test would prove
    # I2C works at one address and the exercise would talk to another.
    catalogue = re.search(r'^CATALOGUE = \{.*?^\}', plugin, re.S | re.M)
    check(catalogue is not None, "board view: the plugin has no CATALOGUE")
    if catalogue:
        entry = re.search(r'"SI7021":\s*\{(.*?)\n    \},', catalogue.group(0), re.S)
        check(entry is not None,
              "board view: the palette does not offer an SI7021, and exercise 4 "
              "cannot be done without adding one")
        if entry:
            in_palette = re.search(r'"address":\s*"([^"]+)"', entry.group(1))
            selftest = io.open(os.path.join(ROOT, "verify", "sensor.repl"),
                               encoding="utf-8").read()
            in_selftest = re.search(r"@\s*i2c1\s+(0x[0-9A-Fa-f]+)", selftest)
            check(in_palette and in_selftest
                  and in_palette.group(1).lower() == in_selftest.group(1).lower(),
                  "board view: the palette's SI7021 is at %s and the self-test's "
                  "is at %s - they must be the same part"
                  % (in_palette and in_palette.group(1),
                     in_selftest and in_selftest.group(1)))

    # The page and its data must be reachable from the same place. The bundled
    # websocket server defaults to 127.0.0.1, and the HTTP server binds every
    # interface; with the default, a container maps the data port to an
    # interface nothing is listening on, and the drawing loads and stays empty
    # with no error anywhere.
    check(re.search(r"WebsocketServer\(\s*data_port\s*,\s*host\s*=\s*"
                    r"[\"']0\.0\.0\.0[\"']", plugin) is not None,
          "board view: the data socket must bind 0.0.0.0, as the HTTP server "
          "does. On 127.0.0.1 it is unreachable through a container's port "
          "mapping and the board draws empty")

    print("board view: %d SVG references, %d message types, %d verbs checked"
          % (len(set(re.findall(r"url\(#([A-Za-z0-9_-]+)\)", page))),
             len(sends), len(verbs)))


def check_copy_records():
    """Is the copy of this repository in the other organisation in step?

    This repository exists twice and `git push` cannot carry a change between
    them, so the two can only be kept together by hand -- and for ten days
    nobody knew they had stopped being. Six files differed, including the
    section that tells learners the exercise checks exist.

    Each side runs the direction it holds a record for. The source holds
    COPIES and not PROVENANCE; the copy holds PROVENANCE and not COPIES. This
    file is itself copied, so it runs in both and must be right in each.

    Staleness WARNS. The rehearsal copy is disposable and is allowed to lag,
    and failing the live repository's build because a test organisation is
    behind would block real work -- after which the quickest way to clear the
    red would be to delete the check.

    An edit made in the copy FAILS. That change belongs upstream and is lost
    at the next sync.

    Exit 2 is neither answer: no record, a shallow checkout, or no git at all,
    which is the case inside the container. Reported, never counted as proof
    of anything. A guard that quietly stops guarding is worse than no guard.
    """
    script = os.path.join("tests", "check_copy_drift.py")

    def run(direction):
        done = subprocess.run([sys.executable, script, direction],
                              cwd=ROOT, capture_output=True, text=True,
                              encoding="utf-8", errors="replace")
        for line in (done.stdout or "").strip().splitlines():
            headline = line.startswith(("copy:", "source:"))
            print(line if headline else "  " + line)
        return done

    if os.path.isfile(os.path.join(ROOT, "COPIES")):
        done = run("--source")
        check(done.returncode in (0, 2),
              "the record of the copy is wrong:\n"
              + (done.stdout or "")[-1000:])

    if os.path.isfile(os.path.join(ROOT, "PROVENANCE")):
        done = run("--copy")
        # One check, not two. An earlier draft asserted the exit code twice
        # and reported a single edited file as two failures, which makes a
        # reader hunt for a second problem that is not there.
        check(done.returncode in (0, 2),
              "this copy has been edited rather than its source. The change "
              "belongs upstream and is lost at the next sync:\n"
              + (done.stdout or "")[-1000:])

    if not os.path.isfile(os.path.join(ROOT, "COPIES")) and \
            not os.path.isfile(os.path.join(ROOT, "PROVENANCE")):
        # A learner's repository, generated from the template, holds neither.
        print("copies: nothing recorded here, so nothing compared")


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--renode", help="path to the Renode executable")
    parser.add_argument("--container", action="store_true",
                        help="also build the container and check its toolchain")
    parser.add_argument("--downloads", action="store_true",
                        help="also check the documented archive names exist "
                             "upstream (needs the network)")
    parser.add_argument("--exercise-checks", action="store_true",
                        help="also build each exercise's scaffolding and "
                             "assert its check.py rejects it (slow; CI runs "
                             "this)")
    parser.add_argument("--no-board", action="store_true",
                        help="skip everything needing Renode. For the checks "
                             "that must run OUTSIDE the container, where git "
                             "and the network are but Renode is not")
    args = parser.parse_args()

    rows = load_register()
    check_register(rows)
    print(f"register: {len(rows)} rows")

    check_doc_pairs()
    print("docs: English and Japanese pairs checked")

    check_bilingual_page_structure()

    check_traps_are_cited(rows)
    print("exercises: trap divergences cited where a learner meets them")

    check_exercise_relevance(rows)
    print("exercises: every row names real exercises, every exercise is named")

    check_links()

    check_no_bom()
    check_the_learners_check_ignores_tags()
    check_grading_is_automatic_and_the_learner_can_stop_it()

    check_line_endings()

    check_documented_commands()
    print("files: no byte-order marks in .repl or .resc")

    check_unit_tests()

    check_copy_records()

    check_scripts_are_executable()

    check_windows_commands()

    check_board_view()

    # The readable tables are generated from the register. If somebody edits
    # one and not the other, a reader is told something the data does not say.
    generated = subprocess.run(
        [sys.executable, os.path.join("tools", "gen_divergence_table.py"), "--check"],
        cwd=ROOT, capture_output=True, text=True,
    )
    check(generated.returncode == 0,
          "docs: DIVERGENCES.md/.ja.md are stale - run "
          "python tools/gen_divergence_table.py")
    print("docs: generated divergence tables checked")

    # Same for the per-exercise pages. Their generated blocks come from
    # divergences.json and references.json, and a learner reading a stale
    # one is told which manuals to open and which traps apply by a file that
    # no longer agrees with either register.
    pages = subprocess.run(
        [sys.executable, os.path.join("tools", "gen_exercise_pages.py"),
         "--check"],
        cwd=ROOT, capture_output=True, text=True,
    )
    check(pages.returncode == 0,
          "exercises: a per-exercise page is stale or missing - run "
          "python tools/gen_exercise_pages.py -- %s"
          % (pages.stdout or "").strip())
    print("exercises: per-exercise pages checked")

    if args.no_board:
        # Said loudly, and the final line says it too, so that a run with
        # this flag can never be mistaken for a full sweep.
        print("board: SKIPPED (--no-board). This is NOT a full sweep.")
        renode = None
    else:
        renode = find_renode(args.renode)
        if renode is None:
            failures.append(
                "Renode not found. Pass --renode PATH. The register's 'fixed' "
                "rows were NOT verified against a running simulator."
            )
        else:
            output = run_renode(renode)
            check_board(output)
            print(f"board: checked against {os.path.basename(renode)}")

    if args.exercise_checks:
        check_exercise_checks_discriminate()
        check_the_guarantees_hold()
    else:
        print("exercise checks: NOT run (pass --exercise-checks). CI runs this.")
        print("guarantees: NOT demonstrated (pass --exercise-checks). "
              "CI runs this.")

    if args.container:
        check_container()
        print("container: image built and its toolchain checked")
    else:
        print("container: NOT checked (pass --container). CI runs this.")

    if args.downloads:
        check_download_names()
    else:
        print("downloads: NOT checked (pass --downloads). CI runs this.")

    print()
    if failures:
        print(f"SWEEP FAILED - {len(failures)} of {checks} checks")
        for failure in failures:
            print(f"  - {failure}")
        return 1

    if args.no_board:
        print(f"PARTIAL SWEEP PASSED - {checks} checks, board NOT checked")
        return 0

    print(f"SWEEP PASSED - {checks} checks")
    return 0


if __name__ == "__main__":
    sys.exit(main())
