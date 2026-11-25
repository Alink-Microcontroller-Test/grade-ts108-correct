"""The build script's exit codes mean three different things.

It used to exit 1 for everything: no argument, no main.c, no compiler, and
code the compiler rejected. The grader turns a non-zero build into "your
code does not compile" and asks the assistant for a hint about it, so a
missing compiler told every learner in that run their code was broken and
then invented advice about an error that was ours.

    0  built
    1  the compiler ran and rejected the code
    2  the build could not be attempted

The same three the checks use. These tests run the real script, because
the contract is the script's and a test of a copy of the logic would not
notice the script changing.
"""

import os
import shutil
import subprocess
import sys

import pytest

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(HERE)
BUILD = os.path.join(ROOT, "tools", "build.sh")

GOOD = """\
#include "stm32f401xe.h"
int main(void) { while (1) { } }
"""

BAD = """\
int main(void) { this is not c }
"""


def bash():
    for candidate in (shutil.which("bash"),
                      r"C:\Program Files\Git\bin\bash.exe",
                      r"C:\Program Files (x86)\Git\bin\bash.exe"):
        if candidate and os.path.isfile(candidate):
            return candidate
    return None


def run(args, course, path=None):
    env = dict(os.environ)
    if path is not None:
        env["PATH"] = path
    return subprocess.run([bash(), os.path.join(course, "tools", "build.sh")]
                          + list(args),
                          cwd=course, env=env,
                          stdout=subprocess.PIPE, stderr=subprocess.STDOUT)


@pytest.fixture
def course(tmp_path):
    """A copy of the course, so a build cannot touch the real tree."""
    target = tmp_path / "course"
    for part in ("tools", "lib", "boards"):
        src = os.path.join(ROOT, part)
        if os.path.isdir(src):
            shutil.copytree(src, target / part)
    (target / "exercises" / "01-x").mkdir(parents=True)
    (target / "exercises" / "01-x" / "main.c").write_text(GOOD)
    return str(target)


@pytest.mark.skipif(bash() is None, reason="no bash on this machine")
class TestTheThreeCodes:
    def test_no_argument_is_two(self, course):
        """A usage mistake is not a statement about anybody's code."""
        assert run([], course).returncode == 2

    def test_no_main_c_is_two(self, course):
        assert run(["exercises/nope"], course).returncode == 2

    def test_no_compiler_is_two(self, course):
        """The one that mattered: this used to be indistinguishable from
        code the compiler rejected."""
        done = run(["exercises/01-x"], course, path="/usr/bin:/bin")
        assert done.returncode == 2
        said = done.stdout.decode("utf-8", "replace")
        assert "not on PATH" in said
        assert "not a problem with the code" in said

    @pytest.mark.skipif(shutil.which("arm-none-eabi-gcc") is None,
                        reason="no ARM toolchain on this machine")
    def test_code_the_compiler_rejects_is_one(self, course):
        with open(os.path.join(course, "exercises", "01-x", "main.c"),
                  "w") as handle:
            handle.write(BAD)
        assert run(["exercises/01-x"], course).returncode == 1

    @pytest.mark.skipif(shutil.which("arm-none-eabi-gcc") is None,
                        reason="no ARM toolchain on this machine")
    def test_code_that_builds_is_zero(self, course):
        assert run(["exercises/01-x"], course).returncode == 0
        assert os.path.isfile(
            os.path.join(course, "exercises", "01-x", "firmware.elf"))


class TestBothScriptsAgree:
    """build.ps1 is the Windows twin and must use the same codes."""

    def test_the_powershell_twin_uses_two_as_well(self):
        with open(os.path.join(ROOT, "tools", "build.ps1"),
                  encoding="utf-8") as handle:
            source = handle.read()
        assert "exit 2" in source, "build.ps1 still exits 1 for everything"
        assert source.count("exit 2") >= 3, \
            "usage, missing main.c and missing compiler should all be 2"
        assert "arm-none-eabi-gcc -ErrorAction" in source or \
               "Get-Command arm-none-eabi-gcc" in source, \
               "build.ps1 does not check for the compiler"

    def test_the_learner_workflow_does_not_call_it_a_compile_error(self):
        """check-my-work.yml is what a learner sees. Exit 2 there means
        the compiler download failed, not that their code is wrong."""
        with open(os.path.join(ROOT, ".github", "workflows",
                               "check-my-work.yml"), encoding="utf-8") as f:
            source = f.read()
        build = source.split("Build every exercise", 1)[1].split("checks=0")[1]
        assert "2)" in build, "the build no longer distinguishes exit 2"
        assert "not your code" in build
