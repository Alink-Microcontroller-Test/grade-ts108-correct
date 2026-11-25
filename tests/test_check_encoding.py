# -*- coding: utf-8 -*-
"""The UTF-8 check, which was built once and then lost.

It shipped on 2026-08-27 and was gone by 2026-10-20, along with
.editorconfig, when the repositories were restructured. Nobody noticed
for seven weeks because the specification requiring it was not being
read.

These tests are the thing that should fail if it goes again, which is
why they assert the behaviour a learner depends on -- the offset, the
widening past .c and .h, the binary skip -- rather than that the module
imports.
"""

import os
import subprocess
import sys

import pytest

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(HERE)
sys.path.insert(0, os.path.join(ROOT, "tools"))

import check_encoding                                    # noqa: E402


def repository(tmp_path, files):
    """A real git checkout, because the check reads git's index."""
    subprocess.run(["git", "init", "-q", str(tmp_path)], check=True)
    for name, data in files.items():
        path = tmp_path / name
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_bytes(data)
    subprocess.run(["git", "-C", str(tmp_path), "add", "-A"], check=True)
    return str(tmp_path)


SHIFT_JIS = "// 温度を読む\n".encode("shift_jis")
JAPANESE = "// 温度を読む\n".encode("utf-8")


class TestWhatItAccepts:
    def test_a_clean_repository_passes(self, tmp_path):
        root = repository(tmp_path, {"main.c": JAPANESE,
                                     "README.md": b"# hello\n"})
        assert check_encoding.check(root) == []

    def test_an_untracked_file_is_not_checked(self, tmp_path):
        root = repository(tmp_path, {"main.c": JAPANESE})
        (tmp_path / "scratch.c").write_bytes(SHIFT_JIS)
        assert check_encoding.check(root) == []

    def test_a_file_deleted_but_still_indexed_is_skipped(self, tmp_path):
        root = repository(tmp_path, {"main.c": JAPANESE, "gone.c": JAPANESE})
        os.remove(os.path.join(root, "gone.c"))
        assert check_encoding.check(root) == []


class TestWhatItRejects:
    def test_a_shift_jis_source_is_reported(self, tmp_path):
        root = repository(tmp_path, {"main.c": SHIFT_JIS})
        assert [name for name, _ in check_encoding.check(root)] == ["main.c"]

    def test_the_offset_points_at_the_first_bad_byte(self, tmp_path):
        root = repository(tmp_path, {"main.c": SHIFT_JIS})
        (name, offset), = check_encoding.check(root)
        # "// " is three ASCII bytes; the Japanese starts straight after.
        assert offset == 3

    def test_it_looks_past_c_and_h(self, tmp_path):
        """The widening that 2.1a added, verified by breaking only a Makefile.

        A Shift-JIS 0x5C is a backslash, which in a Makefile continues the
        line and swallows the next one. The first version of this check
        could not see it.
        """
        root = repository(tmp_path, {"main.c": JAPANESE,
                                     "Makefile": SHIFT_JIS,
                                     "board.json": SHIFT_JIS})
        broken = sorted(name for name, _ in check_encoding.check(root))
        assert broken == ["Makefile", "board.json"]

    def test_every_bad_file_is_reported_not_just_the_first(self, tmp_path):
        root = repository(tmp_path, {"a.c": SHIFT_JIS, "b.c": SHIFT_JIS})
        assert len(check_encoding.check(root)) == 2


class TestBinaries:
    def test_a_binary_file_is_skipped(self, tmp_path):
        """git's own heuristic: a NUL in the first 8000 bytes."""
        png = b"\x89PNG\r\n\x1a\n\x00\x00\x00\rIHDR\xff\xfe\xfd"
        root = repository(tmp_path, {"main.c": JAPANESE, "board.png": png})
        assert check_encoding.check(root) == []

    def test_a_high_byte_without_a_nul_is_still_checked(self, tmp_path):
        """Being undecodable is not the same as being binary."""
        root = repository(tmp_path, {"notes.txt": b"\xff\xfe no nul here"})
        assert [name for name, _ in check_encoding.check(root)] == ["notes.txt"]

    def test_a_utf_16_source_is_reported_not_skipped(self, tmp_path):
        """Notepad's "Unicode" option, which is the likeliest mistake here.

        UTF-16 LE is half NUL bytes, so git's heuristic on its own calls
        it binary and says nothing -- and then the compiler rejects the
        file with a diagnostic about a byte value, which is exactly what
        this check exists to prevent.
        """
        utf16 = "// 温度を読む\n".encode("utf-16")       # BOM included
        assert b"\0" in utf16, "this test is pointless if it has no NULs"
        root = repository(tmp_path, {"main.c": utf16})
        assert [name for name, _ in check_encoding.check(root)] == ["main.c"]

    def test_a_utf_16_big_endian_source_is_reported(self, tmp_path):
        """The other byte order, which carries the other BOM."""
        utf16be = b"\xfe\xff" + "// 温度\n".encode("utf-16-be")
        root = repository(tmp_path, {"main.c": utf16be})
        assert [name for name, _ in check_encoding.check(root)] == ["main.c"]

    def test_a_png_is_still_skipped_after_that(self, tmp_path):
        """The widening must not have turned binaries back on."""
        png = b"\x89PNG\r\n\x1a\n\x00\x00\x00\rIHDR\xff\xfe\xfd"
        root = repository(tmp_path, {"board.png": png})
        assert check_encoding.check(root) == []


class TestHowItExits:
    def test_clean_exits_zero(self, tmp_path):
        root = repository(tmp_path, {"main.c": JAPANESE})
        assert check_encoding.main([root]) == 0

    def test_a_fault_exits_two_never_one(self, tmp_path):
        """One means the compiler rejected the code. This runs before it.

        The grader turns a non-zero build into "your code does not
        compile" and asks the assistant about it. Exit 2 is how this
        repository says not to.
        """
        root = repository(tmp_path, {"main.c": SHIFT_JIS})
        assert check_encoding.main([root]) == 2

    def test_a_tree_that_is_not_a_checkout_says_so(self, tmp_path):
        """Not a fault, and not the same as git being missing."""
        assert check_encoding.check(str(tmp_path)) == check_encoding.UNPACKED


    def test_the_japanese_survives_being_redirected(self, tmp_path):
        """Run as a program with stderr to a pipe, as CI runs it.

        capsys cannot see this one: it captures text, and the fault is in
        the encoding of the bytes. Where stderr is not a console, Python
        falls back to errors="backslashreplace", and stderr is never a
        console where it matters -- check-my-work.yml writes this script's
        output to a file and prints the file. The Japanese half of the
        message was reaching the learner as "\\u306f UTF-8 \\u3067...".
        """
        root = repository(tmp_path, {"main.c": SHIFT_JIS})
        done = subprocess.run(
            [sys.executable, os.path.join(ROOT, "tools", "check_encoding.py"),
             root],
            capture_output=True)
        assert done.returncode == 2
        assert b"\\u306f" not in done.stderr, "escaped instead of encoded"
        said = done.stderr.decode("utf-8")      # raises if it is not UTF-8
        assert "は UTF-8 ではありません" in said

    def test_the_message_names_the_file_in_both_languages(self, tmp_path,
                                                          capsys):
        root = repository(tmp_path, {"main.c": SHIFT_JIS})
        check_encoding.main([root])
        said = capsys.readouterr().err
        assert "main.c is not valid UTF-8" in said
        assert "は UTF-8 ではありません" in said
        assert "offset 3" in said


class TestTheGradersTree:
    """The tree the grader builds in, which is not a clone.

    build_submissions.py extracts the course from a downloaded archive
    into tempfile.mkdtemp(prefix="grade-"). The first version of this
    check exited 2 there, and the build script's exit 2 means "could not
    be attempted", which the grader records as a course defect -- so
    every exercise of every learner would have come back as our fault,
    the real output discarded and nobody told. These two tests are why
    that cannot come back.
    """

    def test_an_unpacked_course_tree_passes(self, tmp_path):
        unpacked = tmp_path / "grade-xyz" / "course"
        (unpacked / "exercises" / "01-blink").mkdir(parents=True)
        (unpacked / "exercises" / "01-blink" / "main.c").write_bytes(JAPANESE)
        assert check_encoding.main([str(unpacked)]) == 0

    def test_it_does_not_claim_git_is_missing_when_git_is_there(self,
                                                               tmp_path,
                                                               capsys):
        check_encoding.main([str(tmp_path)])
        said = capsys.readouterr().err
        assert "not a git checkout" in said
        assert "not installed" not in said


class TestTheRepositoryItself:
    def test_this_repository_is_clean(self):
        """The check, run on the course it protects -- and actually run.

        The two assertions before the last one are the point. Inside the
        course container this is what catches the check skipping instead of
        working: git absent from the image, or git refusing to read a
        checkout owned by whoever mounted it. Either leaves the check
        reporting success without having looked, on the standard route a
        learner builds by (ADR-0016), which is how a guard becomes
        decoration.
        """
        faults = check_encoding.check(ROOT)
        assert faults != check_encoding.NO_GIT, \
            "git is missing here, so the check did not run"
        assert faults != check_encoding.UNPACKED, \
            "git would not read this checkout, so the check did not run"
        assert faults == [], "not valid UTF-8: %s" % faults

    def test_editorconfig_asks_for_utf_8(self):
        """It was lost alongside the check; losing one should fail here."""
        path = os.path.join(ROOT, ".editorconfig")
        assert os.path.isfile(path), ".editorconfig is missing again"
        with open(path, encoding="utf-8") as handle:
            assert "charset = utf-8" in handle.read()
