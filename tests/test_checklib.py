"""The three exit codes a check may leave through, and nothing else.

0 did what the exercise asks, 1 did not, 2 could not tell. The grader reads
these and nothing else, and it reports anything that is not 0 or 1 as
unobserved rather than as the learner's mistake -- so the codes are a
contract between two repositories, not an internal detail.

The case worth testing is the one that was wrong: a check that throws used to
leave through 1, because that is Python's exit code for an uncaught
exception. A bug in our own check was then indistinguishable from the
learner's program being wrong, in this repository and in the grader, and a
learner could be told their exercise failed because our code raised a
KeyError.
"""

import os
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, os.path.join(os.path.dirname(HERE), "tools"))
import checklib  # noqa: E402


def run(body, monkeypatch, argv=("check.py", "--elf", "firmware.elf")):
    monkeypatch.setattr(sys, "argv", list(argv))
    return checklib.main("課題 1 - テスト", body)


def flat(said):
    """Output with the wrapping taken back out.

    The report wraps at 68 columns and Japanese breaks mid-phrase, so a
    sentence is split wherever it happens to land. Asserting against the
    raw text makes a test that fails when somebody changes the indent.
    """
    return "".join(said.split())


class TestTheExitCodes:

    def test_everything_passing_is_zero(self, monkeypatch):
        def body(_elf, report):
            report.check(True, "それらしく動いた")
        assert run(body, monkeypatch) == 0

    def test_something_failing_is_one(self, monkeypatch):
        def body(_elf, report):
            report.check(False, "動かなかった")
        assert run(body, monkeypatch) == 1

    def test_a_check_that_could_not_look_is_two(self, monkeypatch):
        def body(_elf, _report):
            raise checklib.CouldNotRun("シミュレータがありません")
        assert run(body, monkeypatch) == 2


class TestACheckThatIsItselfBroken:
    """Our bug must not read as the learner's mistake."""

    def body(self, _elf, _report):
        raise KeyError("uart")

    def test_it_leaves_through_two_not_one(self, monkeypatch):
        assert run(self.body, monkeypatch) == 2

    def test_it_says_the_check_broke_rather_than_the_exercise(
            self, monkeypatch, capsys):
        run(self.body, monkeypatch)
        said = flat(capsys.readouterr().out)
        assert "確認用スクリプト自体がエラーで停止しました" in said
        assert "不合格としては記録されません" in said

    def test_it_names_the_error_so_it_can_be_reported(self, monkeypatch,
                                                     capsys):
        """The learner can run this check themselves, so they are the one
        who will report it. A bare 'it broke' wastes that."""
        run(self.body, monkeypatch)
        said = capsys.readouterr().out
        assert "KeyError" in said
        assert "uart" in said

    def test_no_traceback_reaches_the_reader(self, monkeypatch, capsys):
        said = (run(self.body, monkeypatch), capsys.readouterr().out)[1]
        assert "Traceback" not in said
        assert "File \"" not in said

    def test_a_report_of_failures_is_not_swallowed(self, monkeypatch):
        """The new branch must not catch its way over a genuine failure."""
        def body(_elf, report):
            report.check(False, "本当に失敗した")
        assert run(body, monkeypatch) == 1


class TestWhatMODERSays:
    """Two bits per pin, and three answers that are not the same answer.

    01 is a plain output, 10 is handed to a peripheral, and anything else
    is neither. These feed verdicts now rather than only wording
    (ADR-0050, ADR-0052), so a pin read as alternate when it is an output
    would pass somebody who never reached alternate-function mode.
    """

    def test_output_mode_is_an_output(self):
        assert checklib.pin_is_output(0x1 << (5 * 2), 5) is True

    def test_output_mode_is_not_alternate(self):
        assert checklib.pin_is_alternate(0x1 << (5 * 2), 5) is False

    def test_alternate_mode_is_alternate(self):
        assert checklib.pin_is_alternate(0x2 << (8 * 2), 8) is True

    def test_alternate_mode_is_not_an_output(self):
        assert checklib.pin_is_output(0x2 << (8 * 2), 8) is False

    def test_input_mode_is_neither(self):
        assert checklib.pin_is_output(0x0, 8) is False
        assert checklib.pin_is_alternate(0x0, 8) is False

    def test_analogue_mode_is_neither(self):
        moder = 0x3 << (8 * 2)
        assert checklib.pin_is_output(moder, 8) is False
        assert checklib.pin_is_alternate(moder, 8) is False

    def test_a_register_nobody_could_read_supports_no_claim(self):
        assert checklib.pin_is_output(None, 8) is None
        assert checklib.pin_is_alternate(None, 8) is None

    def test_one_pin_does_not_answer_for_its_neighbour(self):
        """PB8 and PB9 are read separately, and the real register holds
        both. A shift off by one pin reads the wrong two bits and the
        verdict is then about a pin nobody asked about."""
        moder = 0x2 << (8 * 2)          # PB8 alternate, PB9 untouched
        assert checklib.pin_is_alternate(moder, 8) is True
        assert checklib.pin_is_alternate(moder, 9) is False

    def test_the_measured_register_reads_as_expected(self):
        """0x000A0280 is what GPIOB_MODER actually held after a run on
        2026-11-19, with PB8 and PB9 in alternate-function mode. The low
        bits are the board's own, and a helper that cannot ignore them is
        no use."""
        moder = 0x000A0280
        assert checklib.pin_is_alternate(moder, 8) is True
        assert checklib.pin_is_alternate(moder, 9) is True
        assert checklib.pin_is_output(moder, 8) is False


class TestWhichAlternateFunction:
    """Four bits per pin, pins 8-15 in AFRH with the nibble picked by
    pin % 8. Getting that arithmetic wrong reads a neighbouring pin's
    function and passes a program that selected the wrong one."""

    def test_the_right_function_is_accepted(self):
        afrh = (4 << 0) | (4 << 4)      # PB8, PB9 -> AF4
        assert checklib.pin_alternate_is(afrh, 8, checklib.AF_I2C1) is True
        assert checklib.pin_alternate_is(afrh, 9, checklib.AF_I2C1) is True

    def test_a_wrong_function_is_rejected(self):
        afrh = (7 << 0) | (7 << 4)      # AF7 is USART, not I2C1
        assert checklib.pin_alternate_is(afrh, 8, checklib.AF_I2C1) is False

    def test_an_unset_register_is_rejected(self):
        assert checklib.pin_alternate_is(0x0, 8, checklib.AF_I2C1) is False

    def test_one_pin_does_not_answer_for_its_neighbour(self):
        afrh = 4 << 0                   # PB8 only
        assert checklib.pin_alternate_is(afrh, 8, checklib.AF_I2C1) is True
        assert checklib.pin_alternate_is(afrh, 9, checklib.AF_I2C1) is False

    def test_a_low_pin_is_read_from_its_own_nibble(self):
        """AFRL holds pins 0-7, so pin 3 is the fourth nibble of the
        register it was given rather than the eleventh of a wider one."""
        afrl = 4 << (3 * 4)
        assert checklib.pin_alternate_is(afrl, 3, 4) is True
        assert checklib.pin_alternate_is(afrl, 4, 4) is False

    def test_a_register_nobody_could_read_supports_no_claim(self):
        assert checklib.pin_alternate_is(None, 8, checklib.AF_I2C1) is None

    def test_the_measured_register_reads_as_expected(self):
        """0x00000044 is what GPIOB_AFRH actually held after a run on
        2026-11-19. This value is the whole reason ADR-0052 supersedes
        ADR-0050, so it is worth a test of its own."""
        assert checklib.pin_alternate_is(0x00000044, 8,
                                         checklib.AF_I2C1) is True
        assert checklib.pin_alternate_is(0x00000044, 9,
                                         checklib.AF_I2C1) is True


class TestChangingARegisterMidRun:

    def test_it_asks_the_bus_to_write(self):
        assert checklib.write(checklib.TIM2_CR1, 0) == (
            "sysbus WriteDoubleWord 0x40000000 0x00000000",)

    def test_it_is_not_counted_as_a_value_to_read_back(self):
        """simulate() refuses to judge a run that lost a sample, counting
        what the script asked to be printed. A write asks for nothing, so
        a check that stops a timer must not be reported as unobservable."""
        lines = list(checklib.write(checklib.TIM2_CR1, 0))
        assert checklib._asked_for(lines) == 0

    def test_a_read_in_the_same_script_is_still_counted(self):
        lines = list(checklib.read("cr1", checklib.word(checklib.TIM2_CR1)))
        lines += list(checklib.write(checklib.TIM2_CR1, 0))
        assert checklib._asked_for(lines) == 1
