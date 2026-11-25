"""Swapping the firmware on a running board, measured rather than assumed.

The board view is going to load firmware a learner has just built, on a board
that is already running -- `board.resc` ends with `start`. How to do that is
not in Renode's documentation. It is in Renode's source, and the three facts
below were measured here, inside the course image, on 2026-11-11 against
Renode 1.16.1 and this repository's own `boards/nucleo_f401re.repl`.

WHAT WAS MEASURED
-----------------
1. The sequence that works is `$bin=@<elf>`, a `reset` macro that loads `$bin`,
   then `machine Reset`. The reset pauses the machine itself, runs the macro --
   so the load is legal -- re-derives the vector table from the newly loaded
   image, and resumes. `board.resc` already defines exactly that macro, so the
   plugin reuses it rather than inventing a load path.

2. `sysbus LoadELF` on a machine that is running is refused:

       There was an error executing command 'sysbus LoadELF @...'
       Cannot load ELF on an unpaused machine.

   Refused by printing, not by raising. Inside an included script it also
   abandons every remaining line, so a naive implementation does not merely
   fail to load -- it stops doing anything else it was asked to do.

3. The plausible-looking alternative -- pause, load, reset, start -- **halts the
   processor**:

       [ERROR] cpu: PC does not lay in memory or PC and SP are equal to zero.
       CPU was halted.

   because the reset clears the symbol lookup that the load had just
   established, leaving nothing to derive a start address from. Memory is not
   cleared by a reset, so the previous program's state is still there: the
   board freezes displaying what the old firmware last did. Loud in the log,
   quiet on the board -- a learner sees a stuck board rather than a failed
   load.

   Research from the source could not say whether this halts or boots from a
   flash alias on this particular board description. It halts. That is the
   better of the two, and it is why this file exists: the answer was not
   derivable, and the next person to reorder these lines needs the test rather
   than the reasoning.

WHY FIXTURES RATHER THAN EXERCISES
----------------------------------
Each fixture writes a different word to the same SRAM address and spins. A
reset does not clear SRAM, so reading that address distinguishes three
outcomes, not two: the new word means the swap worked, the old word means it
did not, and anything else means neither program is running. An exercise whose
scaffolding does nothing would have made a failed swap indistinguishable from a
successful load of a program with nothing to show.
"""

import os
import subprocess
import sys

import pytest

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(HERE)
sys.path.insert(0, os.path.join(ROOT, "tools"))

import checklib as cl  # noqa: E402

# Must match tests/fixtures/reload-*/main.c.
MARK = 0x20008000
FIXTURE_A = 0xAAAA0001
FIXTURE_B = 0xBBBB0002

SETTLE = 0.05          # board-seconds; the fixtures write their word at once


def _fixture(name):
    """The path to a built fixture, building it if it is not there.

    Built on demand rather than committed: `.gitignore` excludes `*.elf`, and
    a test that skipped itself because somebody forgot a build step would be a
    test that had silently stopped running.
    """
    directory = os.path.join(ROOT, "tests", "fixtures", name)
    elf = os.path.join(directory, "firmware.elf")
    if os.path.isfile(elf):
        return elf

    script = os.path.join(ROOT, "tools", "build.sh")
    done = subprocess.run(["sh", script, os.path.join("tests", "fixtures", name)],
                          cwd=ROOT, capture_output=True, text=True,
                          encoding="utf-8", errors="replace")
    if not os.path.isfile(elf):
        pytest.skip("could not build the %s fixture, so the reload cannot be "
                    "measured here:\n%s" % (name, (done.stdout or "")
                                            + (done.stderr or "")))
    return elf


def _swap_to(elf):
    """The sequence the plugin will use, as monitor commands.

    `board.resc` already defines this macro. It is defined again here because
    this test builds its own machine rather than including that script, and
    `machine Reset` with no macro registered reports only a warning -- `No
    action for reset - macro <machine>.reset is not registered` -- and leaves
    the board broken. Observed while measuring finding 3.
    """
    return [
        ("$bin=@%s" % elf.replace("\\", "/"),),
        ('macro reset "sysbus LoadELF $bin"',),
        ("machine Reset",),
    ]


def test_the_documented_sequence_swaps_firmware_on_a_running_board():
    """Finding 1. This is the guard on the plugin's load path.

    If somebody reorders these commands, or reaches for `sysbus LoadELF`
    directly, this fails -- which is the whole point, because by hand the
    failure looks like a board that has stopped rather than a load that did
    not happen.
    """
    first, second = _fixture("reload-a"), _fixture("reload-b")

    steps = [
        cl.run_for(SETTLE),
        cl.read("before", cl.word(MARK)),
        ("start",),                      # running, as board.resc leaves it
    ] + _swap_to(second) + [
        ("pause",),                      # RunFor advances from a paused machine
        cl.run_for(SETTLE),
        cl.read("after", cl.word(MARK)),
    ]

    try:
        values, _ = cl.simulate(first, steps)
    except cl.CouldNotRun as why:
        pytest.skip("no simulator here: %s" % why)

    assert cl.as_int(cl.first(values, "before")) == FIXTURE_A, (
        "the first firmware did not run, so nothing after this means anything")
    assert cl.as_int(cl.first(values, "after")) == FIXTURE_B, (
        "the board is not running the firmware that was loaded second")


def test_loading_onto_a_running_board_is_refused_and_abandons_the_script():
    """Finding 2.

    Only one read is asked for, and it is after the load that fails. Nothing
    comes back, which is how the refusal's own words reach the message this
    asserts on -- the simulator abandons the rest of the script.
    """
    first, second = _fixture("reload-a"), _fixture("reload-b")

    steps = [
        ("start",),
        ("sysbus LoadELF @%s" % second.replace("\\", "/"),),
        cl.read("after", cl.word(MARK)),
    ]

    with pytest.raises(cl.CouldNotRun) as refused:
        cl.simulate(first, steps)

    message = str(refused.value)
    if "Renode" in message and "入ってい" in message:
        pytest.skip("no simulator here")
    assert "unpaused" in message, (
        "expected the simulator to refuse a load onto a running machine; "
        "it said:\n%s" % message)


def test_resetting_before_loading_leaves_the_old_firmware_in_place():
    """Finding 3, kept as a test rather than a comment.

    Asserts that the wrong order does **not** swap the firmware. If a later
    Renode makes this work, this test fails -- and that is the signal to
    re-read finding 3 rather than to delete the ordering it argues for.
    """
    first, second = _fixture("reload-a"), _fixture("reload-b")

    steps = [
        cl.run_for(SETTLE),
        cl.read("before", cl.word(MARK)),
        ("start",),
        ("pause",),
        ("sysbus LoadELF @%s" % second.replace("\\", "/"),),
        ("machine Reset",),              # clears the lookup the load just made
        ("start",),
        ("pause",),
        cl.run_for(SETTLE),
        cl.read("after", cl.word(MARK)),
    ]

    try:
        values, _ = cl.simulate(first, steps)
    except cl.CouldNotRun as why:
        pytest.skip("no simulator here: %s" % why)

    assert cl.as_int(cl.first(values, "before")) == FIXTURE_A
    assert cl.as_int(cl.first(values, "after")) == FIXTURE_A, (
        "the wrong order appears to have worked. It did not when this was "
        "measured: the processor halted and the old firmware's memory was "
        "left in place. Re-read finding 3 in this file's docstring before "
        "changing the plugin's load path on the strength of this.")
