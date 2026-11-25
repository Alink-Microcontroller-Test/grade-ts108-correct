"""A failing check looks twice before it reports (ADR-0028).

On 2026-10-14 every reference solution passed 26 times on one machine and
failed on GitHub's runners, with correct one-second half-periods interleaved
with 0.1 second blips. Grading runs on those runners, so a single
observation was telling learners their correct programs were wrong.

These tests are about the decision, not the fault: how many times the body
is observed, and which observation is believed when the two disagree.
"""

import os
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, os.path.join(os.path.dirname(HERE), "tools"))

import checklib  # noqa: E402

EXERCISE = "課題 1 - テスト"


def run(body, monkeypatch, argv=("check.py", "--elf", "firmware.elf")):
    monkeypatch.setattr(sys, "argv", list(argv))
    return checklib.main(EXERCISE, body)


def scripted(*verdicts):
    """A body that behaves differently on each observation.

    Each verdict is 'pass', 'fail' or 'cannot'. The list of observations it
    actually received is left on the function, so a test can say how many
    times it was looked at.
    """
    seen = []

    def body(elf, report):
        verdict = verdicts[min(len(seen), len(verdicts) - 1)]
        seen.append(verdict)
        if verdict == "pass":
            report.check(True, "it worked")
        elif verdict == "fail":
            report.check(False, "it worked", "it did not")
        else:
            raise checklib.CouldNotRun("nobody could watch it")

    body.seen = seen
    return body


class TestHowManyTimesItLooks:
    def test_a_pass_is_observed_once(self, monkeypatch):
        """The common case must not cost twice as much."""
        body = scripted("pass")
        assert run(body, monkeypatch) == 0
        assert body.seen == ["pass"]

    def test_a_failure_is_observed_twice(self, monkeypatch):
        body = scripted("fail")
        assert run(body, monkeypatch) == 1
        assert body.seen == ["fail", "fail"]

    def test_a_could_not_tell_is_observed_twice(self, monkeypatch):
        """The same exit code also covers the checker falling over, where a
        second look costs almost nothing and is worth having."""
        body = scripted("cannot")
        assert run(body, monkeypatch) == 2
        assert body.seen == ["cannot", "cannot"]

    def test_it_never_looks_a_third_time(self, monkeypatch):
        """One retry, not a loop: two observations bound the cost and keep
        the rule explainable in a sentence."""
        body = scripted("fail", "cannot")
        run(body, monkeypatch)
        assert len(body.seen) == 2


class TestWhichObservationIsBelieved:
    def test_fail_then_pass_is_a_pass(self, monkeypatch):
        """The whole point. A glitch on one observation must not tell a
        learner their correct program is wrong."""
        body = scripted("fail", "pass")
        assert run(body, monkeypatch) == 0

    def test_could_not_tell_then_pass_is_a_pass(self, monkeypatch):
        body = scripted("cannot", "pass")
        assert run(body, monkeypatch) == 0

    def test_fail_then_could_not_tell_is_could_not_tell(self, monkeypatch):
        """A disagreement is never resolved towards accusing the learner, so
        two different non-passes settle on the one that accuses nobody."""
        body = scripted("fail", "cannot")
        assert run(body, monkeypatch) == 2

    def test_two_failures_are_a_failure(self, monkeypatch):
        """And the hint ladder is untouched: a genuinely broken program is
        still reported broken, so the learner still gets help."""
        body = scripted("fail", "fail")
        assert run(body, monkeypatch) == 1


class TestWhatTheReaderIsTold:
    def test_the_report_says_it_looked_twice(self, monkeypatch, capsys):
        body = scripted("fail", "pass")
        run(body, monkeypatch)
        out = capsys.readouterr().out
        assert "2 回観測" in out
        assert "不合格" in out and "合格" in out

    def test_the_workings_are_not_printed_twice(self, monkeypatch, capsys):
        """A retried check shows the observation that was reported, not
        both. Two copies of a trace in one Issue comment is noise to the one
        person reading it."""
        body = scripted("fail", "fail")
        run(body, monkeypatch)
        out = capsys.readouterr().out
        assert out.count(EXERCISE) == 1

    def test_a_single_observation_says_nothing_about_looking_twice(
            self, monkeypatch, capsys):
        body = scripted("pass")
        run(body, monkeypatch)
        assert "2 回観測" not in capsys.readouterr().out


class TestMeasuringTheUnmitigatedBehaviour:
    """--no-retry, for the nightly proof.

    The retry is a bandage, and a bandage that hides the wound is how this
    gets forgotten. The nightly measures how often a known-correct program
    is misreported, which is the one number nobody has.
    """

    ARGV = ("check.py", "--elf", "firmware.elf", "--no-retry")

    def test_a_failure_is_observed_once(self, monkeypatch):
        body = scripted("fail", "pass")
        assert run(body, monkeypatch, argv=self.ARGV) == 1
        assert body.seen == ["fail"]

    def test_a_could_not_tell_is_observed_once(self, monkeypatch):
        body = scripted("cannot", "pass")
        assert run(body, monkeypatch, argv=self.ARGV) == 2
        assert body.seen == ["cannot"]

    def test_a_pass_is_still_a_pass(self, monkeypatch):
        body = scripted("pass")
        assert run(body, monkeypatch, argv=self.ARGV) == 0

    def test_it_says_nothing_about_looking_twice(self, monkeypatch, capsys):
        body = scripted("fail")
        run(body, monkeypatch, argv=self.ARGV)
        assert "2 回観測" not in capsys.readouterr().out
