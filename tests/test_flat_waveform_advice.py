"""A flat LED has two causes, and the advice for one is wrong for the other.

Exercise 1's check used to answer a never-moving LED with one sentence:
check the clock, the mode register and the write to ODR. That is right for
somebody who has written nothing yet, and useless for somebody whose setup
is already correct and whose program stops before it reaches the toggle --
an endless loop with no toggle in it, or a handler that trapped. Told to
check the clock they already enabled, the second learner goes hunting for a
mistake they did not make.

Measured on 2026-10-15 by building four programs and running the check on
each:

    the scaffolding, unchanged         pin not set up    -> set it up
    while(1){} with no setup           pin not set up    -> set it up
    setup, then while(1){} no toggle   pin set up        -> you are stuck
    setup, timer interrupt, no handler pin set up        -> you are stuck

The same reasoning, and the same shape of fix, as exercise 2's note about a
correctly configured timer whose LED never moves (ADR-0028).
"""

import os
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, os.path.join(os.path.dirname(HERE), "tools"))

import checklib  # noqa: E402

# PA5 as a general-purpose output is 01 in bits 11:10.
PA5_OUTPUT = 0x1 << (5 * 2)
PA5_INPUT = 0x0
PA5_ALTERNATE = 0x2 << (5 * 2)
PA5_ANALOG = 0x3 << (5 * 2)


class TestReadingTheModeRegister:
    def test_output_is_recognised(self):
        assert checklib.pin_is_output(PA5_OUTPUT) is True

    def test_input_is_not_an_output(self):
        assert checklib.pin_is_output(PA5_INPUT) is False

    def test_alternate_function_is_not_an_output(self):
        """The trap exercise 4 warns about: alternate function looks
        configured and does not drive the pin from ODR."""
        assert checklib.pin_is_output(PA5_ALTERNATE) is False

    def test_analog_is_not_an_output(self):
        assert checklib.pin_is_output(PA5_ANALOG) is False

    def test_another_pin_being_an_output_is_not_PA5(self):
        """Bits two per pin, so a neighbour must not be read as PA5."""
        assert checklib.pin_is_output(0x1 << (4 * 2)) is False
        assert checklib.pin_is_output(0x1 << (6 * 2)) is False

    def test_a_register_nobody_could_read_supports_no_claim(self):
        """None, not False: 'we could not read it' is not 'it is wrong'.
        False here would send the stuck learner the wrong advice."""
        assert checklib.pin_is_output(None) is None

    def test_the_pin_is_configurable(self):
        assert checklib.pin_is_output(0x1 << (13 * 2), pin=13) is True


class TestTheClockBit:
    def test_gpioa_enable_is_bit_zero(self):
        """From RM0368 section 6.3.10. Wrong bit, wrong advice."""
        assert checklib.RCC_AHB1ENR_GPIOAEN == 1

    def test_the_addresses_are_the_ones_the_reference_manual_gives(self):
        """These are read over the bus, so a wrong address reads as
        zero and every learner is told their setup is missing."""
        assert checklib.GPIOA == 0x40020000
        assert checklib.GPIOA_MODER == 0x40020000
        assert checklib.GPIOA_ODR == 0x40020014
        assert checklib.RCC_AHB1ENR == 0x40023830


class TestWhichAdviceIsChosen:
    """The decision itself, as the check makes it."""

    def advice(self, ahb1enr, moder):
        clocked = bool(ahb1enr is not None
                       and ahb1enr & checklib.RCC_AHB1ENR_GPIOAEN)
        an_output = checklib.pin_is_output(moder)
        return "stuck" if (clocked and an_output) else "set-it-up"

    def test_nothing_configured_is_told_to_set_the_pin_up(self):
        assert self.advice(0x0, 0x0) == "set-it-up"

    def test_clock_on_but_pin_not_an_output_is_told_to_set_it_up(self):
        assert self.advice(0x1, PA5_INPUT) == "set-it-up"

    def test_pin_an_output_but_clock_off_is_told_to_set_it_up(self):
        """Writing MODER with the clock off does nothing on real
        hardware, so this learner has not finished the setup."""
        assert self.advice(0x0, PA5_OUTPUT) == "set-it-up"

    def test_both_configured_is_told_they_are_stuck(self):
        assert self.advice(0x1, PA5_OUTPUT) == "stuck"

    def test_unreadable_registers_fall_back_to_the_safe_advice(self):
        """If the registers could not be read, nothing is known about
        the setup, and the older advice is the one that cannot mislead."""
        assert self.advice(None, None) == "set-it-up"
        assert self.advice(0x1, None) == "set-it-up"


class TestExerciseThreeAndFour:
    """The same gap in the other two checks that can show it."""

    def test_gpiob_is_where_the_reference_manual_puts_it(self):
        """D3, D4 and D5 are on port B. A wrong base reads as zero and
        every exercise-4 learner is told to check pins they set up."""
        assert checklib.GPIOB == 0x40020400
        assert checklib.GPIOB_MODER == 0x40020400
        assert checklib.RCC_AHB1ENR_GPIOBEN == 2

    def test_exercise_three_notes_a_running_timer_with_a_still_pin(self):
        """Mirrors exercise 2. The condition, as the check computes it."""
        def should_note(total, cr1):
            return bool(total == 0 and cr1 is not None and cr1 & 0x1)

        assert should_note(0, 0x1) is True          # counting, pin still
        assert should_note(0, 0x0) is False         # timer off: say so
        assert should_note(4, 0x1) is False         # blinking: nothing odd
        assert should_note(0, None) is False        # unreadable: claim less

    def test_exercise_four_reads_four_pins_across_two_ports(self):
        """D2 on port A bit 10; D3, D4, D5 on port B bits 3, 4 and 5.
        Getting a pin number wrong silently picks the wrong advice."""
        moder_a = 0x1 << (10 * 2)
        moder_b = (0x1 << (3 * 2)) | (0x1 << (4 * 2)) | (0x1 << (5 * 2))
        ready = all([checklib.pin_is_output(moder_a, 10),
                     checklib.pin_is_output(moder_b, 3),
                     checklib.pin_is_output(moder_b, 4),
                     checklib.pin_is_output(moder_b, 5)])
        assert ready is True

    def test_exercise_four_one_pin_short_is_not_ready(self):
        moder_a = 0x1 << (10 * 2)
        moder_b = (0x1 << (3 * 2)) | (0x1 << (4 * 2))      # D5 missing
        ready = all([checklib.pin_is_output(moder_a, 10),
                     checklib.pin_is_output(moder_b, 3),
                     checklib.pin_is_output(moder_b, 4),
                     checklib.pin_is_output(moder_b, 5)])
        assert ready is False

    def test_exercise_four_never_fails_on_pin_configuration(self):
        """Renode does not enforce pin configuration
        ('pin-configuration-not-enforced'), so requiring it would fail a
        program that works here and pass one that would not work on the
        board. The registers choose wording, never a verdict."""
        with open(os.path.join(os.path.dirname(HERE), "exercises",
                               "04-read-the-sensor", "check.py"),
                  encoding="utf-8") as handle:
            source = handle.read()
        after = source.split("pins_ready = ", 1)[1]
        assert "report.check(pins_ready" not in after
        assert "pins_ready," not in after.split("if pins_ready:")[0][:200]


def source_of(exercise):
    path = os.path.join(os.path.dirname(HERE), "exercises", exercise,
                        "check.py")
    with open(path, encoding="utf-8") as handle:
        return handle.read()


class TestTheAdviceIsActuallyWiredIn:
    """The classes above test the conditions. These test that the checks
    still contain them -- a condition nobody calls is a condition that
    silently stops applying."""

    def test_exercise_one_chooses_between_two_messages(self):
        source = source_of("01-blink-with-a-delay")
        assert "RCC_AHB1ENR" in source and "GPIOA_MODER" in source
        assert "pin_is_output" in source
        assert source.count("PA5 が一度も High") == 2, \
            "there should be two wordings to choose between"

    def test_exercise_three_keeps_its_note(self):
        source = source_of("03-change-the-interval")
        assert "total == 0" in source, "the note's guard is gone"
        assert "report.note(" in source.split("total == 0")[1][:200]

    def test_exercise_four_chooses_between_two_messages(self):
        source = source_of("04-read-the-sensor")
        assert "pins_ready" in source
        assert source.count("D2〜D5 がすべて消灯") == 2, \
            "there should be two wordings to choose between"

    def test_no_check_fails_a_learner_on_pin_configuration(self):
        """Renode does not enforce it, so a verdict based on it would
        fail a program that works here and pass one that would not work
        on the board. These registers pick wording only."""
        for exercise in ("01-blink-with-a-delay", "04-read-the-sensor"):
            source = source_of(exercise)
            for line in source.splitlines():
                if "report.check(" not in line:
                    continue
                assert "pin_is_output" not in line, \
                    "%s makes pin configuration a verdict: %s" % (
                        exercise, line.strip())
                assert "pins_ready" not in line, \
                    "%s makes pin configuration a verdict: %s" % (
                        exercise, line.strip())
