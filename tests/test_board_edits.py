"""Taking an added part out of board.repl must leave a board that loads.

The removal logic understood only one of the two shapes a part can take.
Removing a button deleted its first line and orphaned the rest, and the
board description then failed to load -- a learner who added a button and
changed their mind was left with a board that would not start.

The function under test is pure, so both shapes are checked here without
a running simulator. vis_f401re.py itself targets the IronPython 2 inside
Renode, so only this one function is imported, by source.
"""

import os
import re
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
PLUGIN = os.path.join(os.path.dirname(HERE), "vis", "vis_f401re.py")

# Lift the one function out rather than import the module: the rest of it
# calls into Renode and cannot run here.
source = open(PLUGIN, encoding="utf-8").read()
start = source.index("def _without_part(")
end = source.index("def remove_part(")
namespace = {}
exec(compile(source[start:end], PLUGIN, "exec"), namespace)
without = namespace["_without_part"]

BASE = """// The board, plus anything added from the board view.
using "boards/nucleo_f401re.repl"
"""

LED = BASE + """
// added from the board view
led_d10: Miscellaneous.LED @ gpioPortB 6

gpioPortB:
    6 -> led_d10@0
"""

BUTTON = BASE + """
// added from the board view
button_d2: Miscellaneous.Button @ gpioPortA
    invert: true
    -> gpioPortA@10
"""

BOTH = BASE + """
// added from the board view
led_d10: Miscellaneous.LED @ gpioPortB 6

gpioPortB:
    6 -> led_d10@0

// added from the board view
button_d2: Miscellaneous.Button @ gpioPortA
    invert: true
    -> gpioPortA@10
"""


def orphans(text):
    """Indented lines with no declaration above them: what breaks the load."""
    bad, seen_header = [], False
    for line in text.splitlines():
        if not line.strip():
            continue
        if not line[:1].isspace():
            seen_header = True
            continue
        if not seen_header:
            bad.append(line)
    return bad


class TestRemovingAButton:
    """The shape that was broken."""

    def test_nothing_of_it_is_left(self):
        out = without(BUTTON, "button_d2")
        assert "button_d2" not in out
        assert "invert: true" not in out
        assert "gpioPortA@10" not in out

    def test_the_board_is_still_well_formed(self):
        out = without(BUTTON, "button_d2")
        assert orphans(out) == [], "indented lines left with no declaration"

    def test_the_original_board_survives(self):
        out = without(BUTTON, "button_d2")
        assert 'using "boards/nucleo_f401re.repl"' in out


class TestRemovingAnLed:
    """The shape that already worked, which must keep working."""

    def test_nothing_of_it_is_left(self):
        out = without(LED, "led_d10")
        assert "led_d10" not in out

    def test_the_empty_port_block_goes_too(self):
        """A block that existed only to wire that part is not valid empty."""
        out = without(LED, "led_d10")
        assert "gpioPortB:" not in out
        assert orphans(out) == []


class TestRemovingOneOfTwo:
    def test_the_other_part_is_untouched(self):
        out = without(BOTH, "button_d2")
        assert "led_d10" in out
        assert "6 -> led_d10@0" in out
        assert "button_d2" not in out
        assert orphans(out) == []

    def test_removing_both_leaves_a_clean_board(self):
        out = without(without(BOTH, "button_d2"), "led_d10")
        assert 'using "boards/nucleo_f401re.repl"' in out
        assert "led_d10" not in out and "button_d2" not in out
        assert orphans(out) == []
        assert "gpioPortB:" not in out

    def test_a_name_that_is_not_there_changes_nothing(self):
        assert without(BOTH, "nothing_like_this").strip() == BOTH.strip()


class TestLineEndings:
    def test_a_windows_file_is_handled(self):
        """The file is CRLF on a Windows checkout, which is where learners
        on the archive route are."""
        out = without(BUTTON.replace("\n", "\r\n"), "button_d2")
        assert "button_d2" not in out
        assert orphans(out) == []
