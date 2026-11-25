# -*- coding: utf-8 -*-
"""Every tracked text file is valid UTF-8, checked before anything is built.

WHY THIS RUNS BEFORE THE COMPILER
---------------------------------
A learner on this course writes Japanese comments, and an editor that
re-saves a file as Shift-JIS produces a fault the compiler reports badly
or not at all. Outside the C sources it is worse than badly:

  a Shift-JIS byte 0x5C in a Makefile is a backslash, which is a line
  continuation, which silently swallows the line after it

  a JSON file in another encoding cannot be parsed at all, and the error
  names the parser rather than the file

So the check covers every tracked text file, not only .c and .h. Tracked
rather than a list of extensions, because a list is a thing to maintain
and a file added next month would not be on it. Binaries are skipped by
the same NUL-byte heuristic git uses.

WHAT IT REPORTS
---------------
The file, and the byte offset of the first byte that is not UTF-8. The
offset matters: "this file is not UTF-8" sends somebody to re-save a
whole file, and the offset sends them to the character they typed.

In both languages, because a learner reading this is already confused and
the course is bilingual everywhere else.

EXIT CODES
----------
  0  every tracked text file decodes -- or this is not a tree where the
     question can be asked, which is not the same thing, but is not a
     build failure either
  2  a tracked text file is not UTF-8

Never 1. One means "the compiler rejected the code", and this runs before
the compiler.

WHERE IT DOES NOT APPLY, AND WHY THAT IS A PASS
-----------------------------------------------
The grader builds a submission in a temporary directory holding the
course extracted from a downloaded archive, not a clone. git has no
index to read there. The first version of this rebuild exited 2 for
that, and exit 2 from the build script means "could not be attempted",
which the grader records as the course's own defect -- so every exercise
of every learner would have come back as our fault, with the real output
discarded and nobody told anything.

So a tree that is not a checkout is a reported skip, not a failure.

Nothing is lost by that. A learner's own repository is a clone, and
check-my-work.yml runs on actions/checkout, so the check runs in both
places where the file is theirs to fix. In the grader only their main.c
crosses over and the rest of the tree is the course's own, so the
repository-wide question is not the one worth asking there.

THIS WAS BUILT ONCE BEFORE
--------------------------
It shipped on 2026-08-27 and was lost when the repositories were
restructured, along with .editorconfig. Nothing noticed for seven weeks,
because the specification that required it was not being read. If it goes
again, tests/test_check_encoding.py is what should fail.
"""

import os
import subprocess
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(HERE)


NO_GIT = "no-git"
UNPACKED = "unpacked"


def tracked(root):
    """Every file git tracks, or why that question has no answer here.

    A list of paths, or NO_GIT when git is not installed, or UNPACKED
    when root is a tree that arrived some other way than by cloning.
    The two are told apart because they are different situations and
    the earlier version of this reported both as the first one, which
    was a lie in the case that actually happens.
    """
    try:
        done = subprocess.run(["git", "-C", root, "ls-files", "-z"],
                              capture_output=True)
    except OSError:
        return NO_GIT
    if done.returncode != 0:
        return UNPACKED
    names = done.stdout.split(b"\0")
    return [n.decode("utf-8", "replace") for n in names if n]


# A file that opens with one of these is text in the wrong encoding, not
# a binary, however many NUL bytes follow.
UNICODE_BOMS = (b"\xff\xfe", b"\xfe\xff")


def is_binary(data):
    """git's own heuristic: a NUL byte in the first 8000 means binary.

    Except where the file announces itself as UTF-16 or UTF-32. Notepad
    offers "Unicode" as a save format and means UTF-16 LE, which is half
    NUL bytes, so the heuristic on its own calls a learner's main.c binary
    and skips it -- and UTF-16 is the wrong encoding a Japanese learner on
    Windows is most likely to produce by accident. Decoding it as UTF-8
    then fails at byte 0, which is both true and the first thing they need
    to know.
    """
    if data[:2] in UNICODE_BOMS or data[:4] == b"\x00\x00\xfe\xff":
        return False
    return b"\0" in data[:8000]


def first_bad_byte(data):
    """Where decoding fails, or None. Returns a 0-based byte offset."""
    try:
        data.decode("utf-8")
    except UnicodeDecodeError as bad:
        return bad.start
    return None


def check(root):
    """A list of (path, offset), or whatever tracked() said instead.

    Empty means every file decodes. NO_GIT or UNPACKED means the
    question was not asked, which main() turns into a pass.
    """
    names = tracked(root)
    if names in (NO_GIT, UNPACKED):
        return names
    faults = []
    for name in names:
        path = os.path.join(root, name)
        if not os.path.isfile(path):
            continue                      # deleted but still in the index
        with open(path, "rb") as handle:
            data = handle.read()
        if is_binary(data):
            continue
        offset = first_bad_byte(data)
        if offset is not None:
            faults.append((name, offset))
    return faults


def main(argv=None):
    argv = sys.argv[1:] if argv is None else argv
    root = argv[0] if argv else ROOT

    # Half of every message here is Japanese, and without this it arrives
    # as backslash escapes. When stderr is not a console Python falls back
    # to errors="backslashreplace", and stderr is never a console where it
    # matters most: check-my-work.yml writes this script's output to a file
    # and prints the file, and the grader captures it. So the half of the
    # message written for a Japanese learner was reaching them as a row of
    # backslash-u escapes, which is unreadable and looks like a bug in the
    # course rather than a file they can fix. tests/ has the case; it runs
    # the script as a program, because capsys captures text and cannot see
    # the difference. Guarded because reconfigure needs Python 3.7 and a
    # stream that has not been replaced by something without one.
    try:
        sys.stderr.reconfigure(encoding="utf-8", errors="replace")
    except (AttributeError, OSError, ValueError):
        pass

    faults = check(root)

    if faults == NO_GIT:
        sys.stderr.write(
            "git is not installed, so the encoding check was skipped.\n"
            "git が無いため、"
            "文字コードの確認を"
            "省略しました"
            "。\n")
        return 0

    if faults == UNPACKED:
        sys.stderr.write(
            "This tree is not a git checkout, so the encoding check was\n"
            "skipped. It runs in the repository this was copied from.\n"
            "このツリーは git の作業ツリー"
            "ではないため、文字コードの"
            "確認を省略しました"
            "。\n")
        return 0

    if not faults:
        return 0

    for name, offset in faults:
        sys.stderr.write(
            "%s is not valid UTF-8. The first bad byte is at offset %d.\n"
            % (name, offset))
        sys.stderr.write(
            "%s は UTF-8 ではありません"
            "。%d バイト目から読め"
            "ません。\n" % (name, offset))
    sys.stderr.write(
        "\nRe-save the file as UTF-8 in your editor, then build again.\n"
        "エディタで UTF-8 として"
        "保存し直してから、"
        "もう一度ビルドして"
        "ください。\n")
    return 2


if __name__ == "__main__":
    sys.exit(main())
