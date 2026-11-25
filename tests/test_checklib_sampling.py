"""A sample is never lost quietly, and a short series is never measured.

The fault these tests pin down was found by the nightly stability proof on
2026-10-15, on its first scheduled run. Every reference solution for
exercise 2 failed three times out of three, reporting half-periods of
0.10, 0.30, 0.70 seconds for a program that toggles the LED once a second.

The cause was ours, not Renode's and not GitHub's. Renode logs "Machine
paused."/"Machine resumed." at INFO for every RunFor, from a different
thread than the one echoing our markers, and the two streams splice:

    @led08:28:19.6173 [INFO] check: Machine paused.

Every value arrived -- 55 of 55. Only the markers were damaged, 5 to 15 of
them per run on GitHub's runners and about 1 in 150 locally. `_tagged`
keyed on the marker, so a damaged marker discarded the good value beneath
it, and `half_periods` multiplied the surviving count by the sample
interval as though no time had gone missing. The check then reported,
confidently, a blink that was never on the pin.

Three defences, one per class below: stop the splice, survive it anyway,
and refuse to measure a series that came back short.
"""

import os
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, os.path.join(os.path.dirname(HERE), "tools"))

import pytest  # noqa: E402

import checklib  # noqa: E402

PAUSED = "08:28:19.6173 [INFO] check: Machine paused."


def fake_renode(monkeypatch, output):
    """Make simulate() run against canned console output."""

    class Done:
        stdout = output
        stderr = ""

    monkeypatch.setattr(checklib, "find_renode", lambda: "renode")
    monkeypatch.setattr(os.path, "isfile", lambda path: True)
    monkeypatch.setattr(checklib.subprocess, "run",
                        lambda *a, **k: Done())


def sampling_steps(count):
    steps = []
    for _ in range(count):
        steps.append(checklib.run_for(0.1))
        steps.append(checklib.read("led", checklib.led()))
    return steps


class TestTheSpliceIsNotInvited:
    """The log is silenced, because it is the only writer we race."""

    def test_the_script_turns_the_log_down(self, monkeypatch):
        written = {}

        class Done:
            stdout = "@led\nTrue\n"
            stderr = ""

        def capture(argv, **kwargs):
            path = argv[argv.index("-e") + 1].split("@", 1)[1]
            with open(path) as script:
                written["script"] = script.read()
            return Done()

        monkeypatch.setattr(checklib, "find_renode", lambda: "renode")
        monkeypatch.setattr(os.path, "isfile", lambda path: True)
        monkeypatch.setattr(checklib.subprocess, "run", capture)

        checklib.simulate("firmware.elf", sampling_steps(1))
        assert "logLevel 3" in written["script"]

    def test_the_log_is_turned_down_before_the_board_is_loaded(
            self, monkeypatch):
        """Too late afterwards: loading the board logs, and so does RunFor."""
        written = {}

        class Done:
            stdout = "@led\nTrue\n"
            stderr = ""

        def capture(argv, **kwargs):
            path = argv[argv.index("-e") + 1].split("@", 1)[1]
            with open(path) as script:
                written["script"] = script.read().splitlines()
            return Done()

        monkeypatch.setattr(checklib, "find_renode", lambda: "renode")
        monkeypatch.setattr(os.path, "isfile", lambda path: True)
        monkeypatch.setattr(checklib.subprocess, "run", capture)

        checklib.simulate("firmware.elf", sampling_steps(1))
        lines = written["script"]
        assert lines.index("logLevel 3") < next(
            i for i, line in enumerate(lines)
            if "LoadPlatformDescription" in line)


class TestASplicedLineStillReadsCorrectly:
    """If something ever races us again, it must not cost a sample."""

    def test_a_marker_with_a_log_line_glued_on_keeps_its_value(self):
        got = checklib._tagged("@led" + PAUSED + "\nTrue\n")
        assert got == [("led", "True")]

    def test_the_label_is_not_read_as_the_leading_letters(self):
        """'cr1' has a digit in it, so the label cannot be [a-z]+."""
        got = checklib._tagged("@cr1" + PAUSED + "\n0x00000001\n")
        assert got == [("cr1", "0x00000001")]

    def test_a_value_with_a_log_line_glued_on_is_not_read_as_the_state(self):
        """Otherwise 'True<log>' is not 'True', and the pin reads as unlit."""
        got = checklib._tagged("@led\nTrue" + PAUSED + "\n")
        assert got == [("led", "True")]

    def test_a_whole_log_line_is_still_skipped(self):
        got = checklib._tagged("@led\n" + PAUSED + "\nTrue\n")
        assert got == [("led", "True")]

    def test_the_ordinary_case_is_unchanged(self):
        got = checklib._tagged("@led\n\n\nTrue\n\n@arr\n0x00001387\n")
        assert got == [("led", "True"), ("arr", "0x00001387")]


class TestAShortSeriesIsNotMeasured:
    """A lost sample does not blur a measurement -- it moves it."""

    def test_fewer_values_than_asked_for_cannot_be_told(self, monkeypatch):
        fake_renode(monkeypatch, ("@led\nTrue\n" * 54))
        with pytest.raises(checklib.CouldNotRun):
            checklib.simulate("firmware.elf", sampling_steps(55))

    def test_it_says_how_many_went_missing(self, monkeypatch):
        fake_renode(monkeypatch, ("@led\nTrue\n" * 40))
        with pytest.raises(checklib.CouldNotRun) as raised:
            checklib.simulate("firmware.elf", sampling_steps(55))
        said = str(raised.value)
        assert "55" in said and "40" in said

    def test_it_is_not_recorded_as_a_failed_exercise(self, monkeypatch):
        """Exit 2, not exit 1. The learner's code is not the question."""
        fake_renode(monkeypatch, ("@led\nTrue\n" * 54))

        def body(elf, report):
            checklib.simulate(elf, sampling_steps(55))

        monkeypatch.setattr(sys, "argv",
                            ["check.py", "--elf", "firmware.elf", "--no-retry"])
        assert checklib.main("課題 2 - テスト", body) == 2

    def test_a_complete_series_is_measured(self, monkeypatch):
        fake_renode(monkeypatch, ("@led\nTrue\n" * 55))
        values, _ = checklib.simulate("firmware.elf", sampling_steps(55))
        assert len(checklib.series(values, "led")) == 55

    def test_a_series_that_came_back_long_is_not_refused(self, monkeypatch):
        """Only short series are dangerous; extra output is Renode's own."""
        fake_renode(monkeypatch, ("@led\nTrue\n" * 56))
        values, _ = checklib.simulate("firmware.elf", sampling_steps(55))
        assert len(checklib.series(values, "led")) >= 55

    def test_the_register_reads_are_counted_too(self, monkeypatch):
        steps = sampling_steps(2)
        steps.append(checklib.read("arr", checklib.word(checklib.TIM2_ARR)))
        fake_renode(monkeypatch, "@led\nTrue\n@led\nTrue\n")
        with pytest.raises(checklib.CouldNotRun):
            checklib.simulate("firmware.elf", steps)


class TestWhatTheFaultLookedLike:
    """The shape of the misreport, so a regression is recognisable."""

    def test_a_lost_marker_used_to_shorten_the_measured_period(self):
        """Documents the arithmetic that made a 1.0s blink read as 0.7s.

        Ten samples at 0.1s is one second. Lose three markers inside that
        run and half_periods reports 0.7 -- outside exercise 2's 0.35
        tolerance, and reported as the learner's fault.
        """
        whole = ["True"] * 10 + ["False"] * 10 + ["True"] * 10
        assert checklib.half_periods(whole, 0.1) == pytest.approx([1.0])

        damaged = ["True"] * 7 + ["False"] * 10 + ["True"] * 10
        assert checklib.half_periods(damaged, 0.1) == pytest.approx([1.0])

        inside = ["True"] * 10 + ["False"] * 7 + ["True"] * 10
        assert inside.count("False") == 7
        assert checklib.half_periods(inside, 0.1) == pytest.approx([0.7])
