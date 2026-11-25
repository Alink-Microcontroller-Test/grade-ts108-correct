"""Shared machinery for the exercises' behaviour checks.

Each exercise's check.py says what to observe and what counts as correct.
This says how to observe it: build a Renode script, run it headless, and
read values back out of the output.

WHAT THESE CHECKS ARE FOR, AND WHAT THEY ARE NOT
------------------------------------------------
They answer "does the board do what the exercise asked", which compiling
cannot. They are not a judgement of whether somebody has learned anything,
and they are not a grade -- a teacher decides that.

They are also deliberately tolerant. Where an exercise leaves a choice open,
the check tests the property every permitted answer shares, not the answer
this file's author happened to think of. A check that fails correct work is
worse than no check at all: it teaches a learner to distrust the tooling,
and they are in no position to tell which of them is wrong.

THREE EXIT CODES, NOT TWO
-------------------------
  0  everything asked for was observed
  1  something the exercise asked for did not happen
  2  the check could not run, which is nobody's fault and not a failure

The third exists because the two commonest reasons for not finishing --
no simulator installed, and a submission that simulates too slowly to watch
-- are both wrong to report as "your code is broken".
"""

import io
import os
import re
import shutil
import subprocess
import sys
import tempfile
import time

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(HERE)

# These checks speak Japanese, and a Windows console defaults to a legacy
# codepage that cannot encode it -- printing one character raises
# UnicodeEncodeError and the whole check dies. That matters twice over: a
# learner on the archive route runs this on Windows, and the grader reads
# a non-zero exit as their exercise having failed. So the crash would have
# told somebody their correct code was wrong, on our account.
for _stream in (sys.stdout, sys.stderr):
    try:
        _stream.reconfigure(encoding="utf-8", errors="replace")
    except (AttributeError, ValueError):
        pass  # Python 2, or a stream that cannot be reconfigured

# Leaves headroom under the grader's own 180s limit, so that a submission
# which is simply slow to simulate is reported as slow rather than killed
# without explanation.
RENODE_TIMEOUT = 100

BOARD = "boards/nucleo_f401re.repl"

# TIM2, from RM0368 section 13.4. Read through the bus rather than guessed
# at, so the check says what the hardware actually holds.
TIM2 = 0x40000000
TIM2_CR1 = TIM2 + 0x00
TIM2_DIER = TIM2 + 0x0C
TIM2_PSC = TIM2 + 0x28
TIM2_ARR = TIM2 + 0x2C

# GPIOA and the clock that feeds it, from RM0368 sections 8.4 and 6.3.
# Read so a check can tell "the pin was never set up" from "the pin was
# set up and the program stopped before it moved" -- two failures with
# the same flat waveform and opposite advice.
GPIOA = 0x40020000
GPIOA_MODER = GPIOA + 0x00
GPIOA_ODR = GPIOA + 0x14

GPIOB = 0x40020400
GPIOB_MODER = GPIOB + 0x00
# AFRL covers pins 0-7 and AFRH pins 8-15, four bits each. The bus keeps
# this register: measured 2026-11-19, GPIOB_AFRH reads back 0x00000044
# after firmware selects AF4 on PB8 and PB9. No peripheral model here
# consults it, which is why a transfer succeeds on unconfigured pins, but
# a check can read it -- and that is the distinction ADR-0052 turns on.
GPIOB_AFRL = GPIOB + 0x20
GPIOB_AFRH = GPIOB + 0x24

RCC_AHB1ENR = 0x40023830
RCC_AHB1ENR_GPIOAEN = 1 << 0
RCC_AHB1ENR_GPIOBEN = 1 << 1

LD2_PIN = 5

# I2C1 on PB8/PB9, from the alternate function table in DS10086.
AF_I2C1 = 4

# What the checks in this course promise, beyond not being vacuous.
#
# A name here is a claim the course's own build must DEMONSTRATE, not a
# label (ADR-0051). tests/sweep.py builds a program that produces each
# exercise's observable the wrong way and requires the check to reject it;
# a check that accepts its fake fails the build and is named. Three
# comments in this codebase claimed checks nobody had written and were
# removed on 2026-11-19 -- none of them failed anything, each was found by
# reading, and each had been relied on meanwhile.
#
# So: do not add a name here before the thing that proves it.
#
#   causal-checks  the check tests the mechanism the exercise asks for and
#                  not only its outcome, so a program reaching the right
#                  observable another way is rejected (ADR-0049)
GUARANTEES = ("causal-checks",)


def pin_is_output(moder, pin=LD2_PIN):
    """Does MODER say this pin is a general-purpose output?

    Two bits per pin; 01 is output. None in, None out: a register nobody
    could read supports no claim either way.
    """
    if moder is None:
        return None
    return (moder >> (pin * 2)) & 0x3 == 0x1


def pin_is_alternate(moder, pin):
    """Does MODER say this pin is handed to a peripheral?

    Two bits per pin; 10 is alternate function. None in, None out.

    Says the pin was handed over, never which function was chosen -- that
    is AFRL/AFRH, and pin_alternate_is() reads it. The two are separate
    because the failures want different advice: a pin left as a plain
    output is somebody who has not reached alternate-function mode at all,
    while a pin in alternate-function mode with the wrong number is
    somebody who read the wrong row of the datasheet table.
    """
    if moder is None:
        return None
    return (moder >> (pin * 2)) & 0x3 == 0x2


def pin_alternate_is(afr, pin, function):
    """Does AFRL/AFRH select this alternate function for this pin?

    Four bits per pin. AFRL holds pins 0-7 and AFRH pins 8-15, so the
    caller passes whichever register the pin lives in together with the
    pin's own number; the nibble is picked with pin % 8 either way.
    None in, None out.
    """
    if afr is None:
        return None
    return (afr >> ((pin % 8) * 4)) & 0xF == function


class CouldNotRun(Exception):
    """Not the learner's fault. Exit 2, not 1."""


def find_renode():
    override = os.environ.get("RENODE")
    if override and (os.path.isfile(override) or shutil.which(override)):
        return override
    found = shutil.which("renode") or shutil.which("renode.exe")
    if found:
        return found
    for guess in (
            os.path.join(ROOT, "..", "..", "tools", "renode",
                         "renode_1.16.1-dotnet_portable", "renode.exe"),
            os.path.join(ROOT, "..", "tools", "renode",
                         "renode_1.16.1-dotnet_portable", "renode.exe"),
            "/opt/renode_1.16.1-dotnet_portable/renode"):
        if os.path.isfile(guess):
            return guess
    return None


# --- describing a run -------------------------------------------------------

def run_for(seconds):
    return ('emulation RunFor "%s"' % seconds,)


def press():
    return ("sysbus.gpioPortC.button Press",)


def release():
    return ("sysbus.gpioPortC.button Release",)


def read(label, expression):
    """Print a value, tagged so it can be found again in the output."""
    return ('echo "@%s"' % label, expression)


def led():
    return "sysbus.gpioPortA.led State"


def word(address):
    return "sysbus ReadDoubleWord 0x%08X" % address


def write(address, value):
    """Change a register mid-run, from outside the program.

    This is how a check tests the mechanism rather than the outcome
    (ADR-0049): stop the timer the exercise asked for and see whether the
    blinking stops with it. A program built on the timer freezes; one
    blinking from a counting loop carries on, and the difference is the
    verdict.

    Measured 2026-11-19 that the timer honours this: TIM2 CR1 reads 1
    before the write and 0 after, stays 0, and a correct program's pin
    stops changing.
    """
    return ("sysbus WriteDoubleWord 0x%08X 0x%08X" % (address, value),)


def simulate(elf, steps, extra=()):
    """Run one Renode session and return every tagged value, in order.

    Returns a list of (label, value) pairs -- a list rather than a mapping
    because the same label is read many times when sampling.

    `extra` names further platform descriptions, layered on the board before
    the firmware is loaded. Exercise 4 needs this: its parts -- a sensor and
    four LEDs -- are ones the learner adds in the board view, which writes
    them into their own board.repl. Only exercises/*/main.c crosses from a
    learner into the grading build, so their board.repl never reaches the
    grader and a check cannot depend on it. The check brings the parts
    instead, at the pins the exercise fixes, exactly as verify/verify.resc
    brings a sensor for the setup self-test.

    Order matters: a platform description after LoadELF is too late.
    """
    renode = find_renode()
    if renode is None:
        raise CouldNotRun(
            "この環境には Renode が入っていないため、ボードを動かせません"
            "でした。コードに問題があるわけではありません。この確認には"
            "シミュレータが必要です。")

    if not os.path.isfile(elf):
        raise CouldNotRun(
            "%s に firmware がありません。先にビルドしてください。" % elf)

    # Errors only. Renode logs "Machine paused."/"Machine resumed." at INFO
    # for every RunFor, from a different thread than the one echoing our
    # markers, and the two streams splice into each other mid-line:
    #
    #   @led08:28:19.6173 [INFO] check: Machine paused.
    #   @le08:28:20.3228 [INFO] check: Machine paused.
    #   d
    #
    # A spliced marker used to cost us the sample under it, which shortened
    # the series and made half_periods() report a blink that was never on
    # the pin. Silencing the log removes the only writer we were racing.
    lines = ['mach create "check"',
             "logLevel 3",
             "machine LoadPlatformDescription @%s" % BOARD]
    for description in extra:
        lines.append("machine LoadPlatformDescription @%s" % description)
    lines.append("sysbus LoadELF @%s" % elf.replace("\\", "/"))
    for step in steps:
        lines.extend(step)

    handle, path = tempfile.mkstemp(suffix=".resc")
    os.close(handle)
    with open(path, "w", newline="\n") as script:
        script.write("\n".join(lines) + "\n")

    started = time.time()
    try:
        done = subprocess.run(
            [renode, "--console", "--disable-xwt", "--plain",
             "-e", "i @" + path.replace("\\", "/"), "-e", "quit"],
            cwd=ROOT, capture_output=True, text=True,
            timeout=RENODE_TIMEOUT)
    except subprocess.TimeoutExpired:
        raise CouldNotRun(
            "シミュレータが %d 秒以内に終わらなかったため、プログラムの"
            "動作を観測できませんでした。\n"
            "\n"
            "よくある原因は、main ループが周辺レジスタを間を置かずに読み"
            "続けていることです。ピンをひたすらポーリングしている場合が"
            "これにあたります。実機では問題ありませんが、シミュレーション"
            "は非常に遅くなり、実時間のおよそ 100 倍かかります。読み出しの"
            "間に短い遅延を入れれば解消します。\n"
            "\n"
            "DIVERGENCES.md の 'peripheral-reads-are-slow-to-simulate' を"
            "参照してください。\n"
            "\n"
            "これは課題の不合格としては記録されません。"
            % RENODE_TIMEOUT)
    finally:
        try:
            os.unlink(path)
        except OSError:
            pass

    output = (done.stdout or "") + (done.stderr or "")
    values = _tagged(output)
    if not values:
        raise CouldNotRun(
            "シミュレータから値が返りませんでした。ボードか firmware の"
            "読み込みに失敗している可能性があります。\n\n" + output[-800:])

    # Every read we asked for must have come back. A check that samples a
    # pin converts the number of samples into elapsed time, so a lost
    # sample does not blur the measurement -- it moves it, and the verdict
    # is then about a program nobody wrote. Short series are therefore not
    # measured at all.
    asked = _asked_for(lines)
    if len(values) < asked:
        raise CouldNotRun(
            "シミュレータの出力が %d 件中 %d 件しか読み取れなかったため、"
            "プログラムの動作を観測できませんでした。\n"
            "\n"
            "観測した値の数から時間を数えているので、取りこぼしたまま判定"
            "すると、書かれていないプログラムについての結果になります。"
            "そのため、ここでは判定しません。\n"
            "\n"
            "これは課題の不合格としては記録されません。"
            % (asked, len(values)))
    return values, time.time() - started


def _asked_for(lines):
    """How many values the script asked Renode to print."""
    return sum(1 for line in lines if line.startswith('echo "@'))


def _tagged(output):
    """Every value printed after an @label line.

    Carriage returns are stripped first: Renode's console ends these lines
    with two of them, and an anchored match for the bare label finds
    nothing without this.

    A log line spliced onto the marker is cut off before the label is read.
    Renode's log writes from another thread and can land in the middle of
    the marker, leaving "@led08:28:19.6173 [INFO] check: Machine paused.".
    Slicing off the "@" made that the label "led08:28:19.6173 [INFO] ...",
    which no caller asks for, so the sample under it was dropped silently.
    Cutting at the timestamp recovers "led" without having to assume what
    a label looks like -- "cr1" has a digit in it, so the label cannot
    just be read as the leading letters. `logLevel 3` in simulate() is
    what stops the splice happening; this is what makes it harmless if
    some other line ever races us again.
    """
    out = []
    lines = [_unspliced(line) for line in output.replace("\r", "").splitlines()]
    for index, line in enumerate(lines):
        if not line.startswith("@"):
            continue
        label = line[1:]
        for candidate in lines[index + 1:]:
            if not candidate or re.match(r"^\d\d:\d\d:\d\d", candidate):
                continue
            out.append((label, candidate))
            break
    return out


def _unspliced(line):
    """One output line with any log line that landed inside it removed.

    Applied to values as well as to markers: "True08:28:19.6173 [INFO] ..."
    would otherwise be read as the pin's state and count as not-lit.
    """
    return re.sub(r"\d\d:\d\d:\d\d\.\d+ \[\w+\].*$", "", line.strip()).strip()


# --- reading what came back -------------------------------------------------

def series(values, label):
    return [v for name, v in values if name == label]


def first(values, label):
    got = series(values, label)
    return got[0] if got else None


def as_int(text):
    if text is None:
        return None
    try:
        return int(text, 16) if text.lower().startswith("0x") else int(text)
    except ValueError:
        return None


def transitions(sequence):
    return sum(1 for a, b in zip(sequence, sequence[1:]) if a != b)


def half_periods(sequence, step):
    """How long the LED stayed in each state, in seconds.

    The first and last runs are dropped: sampling started and stopped
    part-way through them, so their length says nothing.
    """
    if not sequence:
        return []
    runs = []
    current, length = sequence[0], 1
    for value in sequence[1:]:
        if value == current:
            length += 1
        else:
            runs.append(length)
            current, length = value, 1
    runs.append(length)
    return [r * step for r in runs[1:-1]]


def trace(sequence):
    """The blink, as something a person can read at a glance."""
    return "".join("#" if v == "True" else "." for v in sequence)


# --- saying what happened ---------------------------------------------------

def _width(text):
    """How many columns this occupies, not how many characters it has.

    A kanji is one character and two columns wide, so wrapping Japanese by
    character count produces lines twice as long as asked for.
    """
    import unicodedata
    return sum(2 if unicodedata.east_asian_width(c) in "WF" else 1
               for c in text)


def wrap(text, columns=72):
    """Wrap to a display width, breaking anywhere when there is no space.

    Japanese does not put spaces between words, so the usual word wrap
    leaves the whole sentence on one line.
    """
    lines, current = [], ""
    for char in text:
        if char == " " and _width(current) >= columns:
            lines.append(current)
            current = ""
            continue
        if _width(current) + _width(char) > columns:
            lines.append(current)
            current = ""
        current += char
    if current:
        lines.append(current)
    return [l.strip() for l in lines if l.strip()] or [text]


class Report(object):
    """Collects results and prints them as a count, which is the shape the
    commissioning party's own design asks for: 'n of m passed'."""

    def __init__(self, exercise):
        self.exercise = exercise
        self.results = []
        self.notes = []

    def check(self, passed, name, detail=""):
        self.results.append((bool(passed), name, detail))
        return bool(passed)

    def note(self, text):
        self.notes.append(text)

    def finish(self):
        passed = [r for r in self.results if r[0]]
        failed = len(self.results) - len(passed)
        print("%s" % self.exercise)
        for note in self.notes:
            # Wrapped, because these are read by a learner in an Issue and
            # by the assistant in a prompt, and one 300-character line
            # serves neither. Japanese does not break on spaces, so the
            # wrapper is told that any character is a break point.
            for line in wrap(note, columns=68):
                print("  %s" % line)
        if self.notes:
            print("")
        for ok, name, detail in self.results:
            print("  %s  %s" % ("成功" if ok else "失敗", name))
            if detail and not ok:
                for line in detail.splitlines():
                    print("        %s" % line)
        print("")
        # The shape the commissioning party's own design asks for:
        # テスト：10件中8件成功、2件失敗
        summary = "テスト: %d件中%d件成功" % (len(self.results), len(passed))
        if failed:
            summary += "、%d件失敗" % failed
        print(summary)
        return 0 if failed == 0 else 1


# What each exit code is called, for the line that says a check looked
# twice. A learner reads this in an Issue.
VERDICT_IN_JAPANESE = {0: "合格", 1: "不合格",
                       2: "確認できず"}


def _observe(exercise, body, elf):
    """One observation. Returns (exit code, what it printed).

    The printing is captured rather than emitted, because a check that
    looks twice must not show its workings twice: the learner is shown the
    observation that was reported, and told there were two.
    """
    captured = io.StringIO()
    previous, sys.stdout = sys.stdout, captured
    try:
        report = Report(exercise)
        try:
            body(elf, report)
        except CouldNotRun as why:
            print("%s" % exercise)
            print("")
            print("確認できませんでした")
            for paragraph in str(why).splitlines():
                if not paragraph.strip():
                    print("")
                    continue
                for line in wrap(paragraph, columns=68):
                    print("  %s" % line)
            return 2, captured.getvalue()
        except Exception as exc:
            # SystemExit and KeyboardInterrupt are not Exception, so --help
            # and Ctrl-C still behave.
            print("%s" % exercise)
            print("")
            print("確認できませんでした")
            for line in wrap("確認用スクリプト"
                             "自体がエラーで停"
                             "止しました。課題"
                             "の不合格としては"
                             "記録されません。"
                             "この表示が出た場"
                             "合は教材側の不具"
                             "合ですので、その"
                             "ままご連絡くださ"
                             "い。", columns=68):
                print("  %s" % line)
            print("")
            print("  %s: %s" % (type(exc).__name__, exc))
            return 2, captured.getvalue()
        return report.finish(), captured.getvalue()
    finally:
        sys.stdout = previous


def main(exercise, body):
    """Wrap a check so the three exit codes are handled in one place.

    Three codes, and the third is the one that needs defending: 0 did what
    the exercise asks, 1 did not, 2 could not tell.

    A check that throws used to leave through code 1, because that is what
    Python exits with on an uncaught exception -- so a bug in our own check
    was indistinguishable from the learner's program being wrong, and the
    grader had no way to tell them apart either. A learner would be told
    their exercise failed because our code raised a KeyError.

    So anything unexpected leaves through 2, like every other case where
    nobody established anything. The exception's type and message are
    printed because the learner can run this check themselves and will want
    to report it; the traceback is not, because it is noise to the one
    person reading it.

    A FAILING VERDICT IS OBSERVED TWICE
    -----------------------------------
    On 2026-10-14 every reference solution passed 26 times on one machine
    and failed on GitHub's runners, with correct one-second half-periods
    interleaved with 0.1 second blips. A single observation was therefore
    telling learners their correct programs were wrong -- on the machines
    where grading actually runs. One glitch is not a verdict (ADR-0028).

    A pass is never re-observed. It would cost twice as much in the common
    case to guard against a false pass that needs the pin to have genuinely
    changed state to exist at all.
    """
    import argparse
    parser = argparse.ArgumentParser()
    parser.add_argument("--elf", required=True)
    parser.add_argument("--no-retry", action="store_true",
                        help="observe once. For measuring how often a "
                             "correct program is misreported; never for "
                             "deciding anything about a learner")
    args = parser.parse_args()

    first, shown = _observe(exercise, body, args.elf)
    if first == 0 or args.no_retry:
        sys.stdout.write(shown)
        return first

    second, again = _observe(exercise, body, args.elf)

    # 0 before 2 before 1. A disagreement is never resolved towards
    # accusing the learner: if either look saw it work, it worked; and if
    # neither did but one could not tell, nobody established a failure.
    if 0 in (first, second):
        code, shown = 0, (shown if first == 0 else again)
    elif 2 in (first, second):
        code, shown = 2, (shown if first == 2 else again)
    else:
        code, shown = 1, again

    sys.stdout.write(shown)
    print("")
    for line in wrap("同じ提出を 2 回観測"
                     "しました（1 回目: %s、"
                     "2 回目: %s）。観測環境"
                     "によるばらつきを避"
                     "けるため、一度だけ"
                     "の観測で不合格とは"
                     "しません。"
                     % (VERDICT_IN_JAPANESE.get(first, first),
                        VERDICT_IN_JAPANESE.get(second, second)),
                     columns=68):
        print("  %s" % line)
    return code
