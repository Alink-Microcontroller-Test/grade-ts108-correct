"""Does the LED blink, once a second, driven by TIM2?

Exercise 2 differs from exercise 1 in where the timing comes from, so a
check that only watched the LED would pass a delay loop and miss the point
of the exercise entirely.

Four things are checked:
  - the LED blinks at all
  - it blinks at one second on, one second off, which the exercise states
    exactly and which a counting loop cannot hold
  - TIM2 is running and asking for an interrupt. NOT that it is the thing
    driving the LED -- see the note at that check, which says what these
    two bits do and do not show
  - the blinking stops when the timer is stopped from outside, which is
    what shows the timer is driving it. The three above are all satisfied
    by a program that configures TIM2, ignores it, and blinks from a
    delay loop at one second

The period is checked with a wide tolerance. The exercise asks for one
second and the arithmetic gives exactly that, but a learner who reaches
0.98s through a slightly different prescaler has understood everything the
exercise teaches.

    python check.py --elf firmware.elf
"""

import os
import sys

sys.path.insert(0, os.path.join(
    os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))),
    "tools"))

import checklib as cl  # noqa: E402

STEP = 0.1
COUNT = 55          # 5.5s: enough for five half-cycles at one second

# After the timer is stopped from outside, how long to watch a pin that
# should now be still. 2.5s is long enough to catch two changes from a
# program blinking at the one second this exercise asks for, which is what
# a delay loop pretending to be a timer looks like.
AFTER = 25

# A timer stopped between its last update and our write can leave one
# interrupt already pending, and the handler is entitled to run it -- so
# one change after the stop is the program finishing what the timer
# started, not the timer still running. Two is a program that never needed
# the timer at all.
ALLOWED_AFTER_STOP = 1

WANT = 1.0
TOLERANCE = 0.35    # generous on purpose; see the note above

# What the board's timer counts in a second. Named here because the hint
# below quotes it, and a number quoted as prose beside the constant it
# describes is how the two come apart. Exercise 3 holds the same figure
# under the same name.
TIMER_TICK = 84000000.0

# Said twice below -- once when the period is wrong and once when there
# were too few changes to measure it -- and derived from WANT, because a
# label reading "1 秒点灯、1 秒消灯" beside a WANT of 2.0 would tell the
# learner the exercise wants something it does not.
PERIOD_LABEL = "%g 秒点灯、%g 秒消灯" % (WANT, WANT)


def body(elf, report):
    steps = []
    for _ in range(COUNT):
        steps.append(cl.run_for(STEP))
        steps.append(cl.read("led", cl.led()))
    steps.append(cl.read("cr1", cl.word(cl.TIM2_CR1)))
    steps.append(cl.read("dier", cl.word(cl.TIM2_DIER)))
    steps.append(cl.read("psc", cl.word(cl.TIM2_PSC)))
    steps.append(cl.read("arr", cl.word(cl.TIM2_ARR)))

    # Now take the timer away and watch what the program does without it.
    #
    # CEN and UIE being set says the timer was configured; it does not say
    # the blinking comes FROM the timer. A program that sets both and then
    # blinks from a counting loop satisfies every other check here, which
    # is the whole difference between this exercise and exercise 1. So the
    # timer is stopped from outside and the pin must go still with it.
    # ADR-0049.
    #
    # The whole of CR1 is written rather than just CEN cleared, because
    # the script is built before the run and cannot know what else the
    # learner put in that register. Nothing in CR1 restarts a stopped
    # timer, so zeroing it stops the timer and no more.
    steps.append(cl.write(cl.TIM2_CR1, 0))
    for _ in range(AFTER):
        steps.append(cl.run_for(STEP))
        steps.append(cl.read("stopped", cl.led()))

    values, seconds = cl.simulate(elf, steps)
    lit = cl.series(values, "led")
    stopped = cl.series(values, "stopped")

    report.note("PA5 をボード時間で %.1f 秒間（実時間 %.1f 秒）観測しました"
                % (STEP * COUNT, seconds))
    report.note("波形  %s" % cl.trace(lit))

    changes = cl.transitions(lit)
    report.check(changes >= 3, "LED が点滅する",
                 "LED の状態が %.1f 秒間で %d 回しか変化しませんでした。"
                 % (STEP * COUNT, changes))

    # Whole runs only: the first and last are cut short by when sampling
    # started and stopped, so their length means nothing.
    runs = cl.half_periods(lit, STEP)
    if runs:
        average = sum(runs) / len(runs)
        worst = max(abs(r - WANT) for r in runs)
        report.check(
            worst <= TOLERANCE,
            PERIOD_LABEL,
            "半周期は %s 秒でした（平均 %.2f 秒）。\n"
            "この課題が求めているのはどちらも %g 秒で、"
            "許容範囲は ±%g 秒です。\n"
            "タイマーは毎秒 %s 回数えます。PSC がそれを分周し、"
            "ARR がその結果を\n"
            "数えます。どちらも、欲しい数より 1 小さい値を入れます。"
            % (", ".join("%.2f" % r for r in runs), average,
               WANT, TOLERANCE, "{:,}".format(int(TIMER_TICK))))
    else:
        report.check(False, PERIOD_LABEL,
                     "LED の状態変化が少なすぎて、周期を測れませんでした。")

    cr1 = cl.as_int(cl.first(values, "cr1"))
    dier = cl.as_int(cl.first(values, "dier"))
    psc = cl.as_int(cl.first(values, "psc"))
    arr = cl.as_int(cl.first(values, "arr"))

    running = bool(cr1 is not None and cr1 & 0x1)          # CEN
    asking = bool(dier is not None and dier & 0x1)         # UIE

    # Named for exactly what these two bits prove and no more. This test
    # used to say "raising an interrupt", which these bits do NOT show: a
    # timer can be counting and requesting an interrupt the processor was
    # never told to accept. A submission missing NVIC_EnableIRQ passed
    # this while its LED never moved, and the assistant, told the timer
    # was fine, went looking elsewhere and invented two faults that were
    # not there. A check that claims more than it verified is worse than
    # no check, because it misdirects.
    report.check(
        running and asking,
        "TIM2 が動作し、割り込みを要求している",
        "TIM2 CR1=%s DIER=%s PSC=%s ARR=%s\n"
        "CEN（CR1 の bit 0）でタイマーが数え始め、UIE（DIER の bit 0）で\n"
        "割り込みを要求できるようになります。タイマーではなく遅延ループで\n"
        "点滅させている場合、ここはどちらも 0 のままになります。それが\n"
        "前の課題との違いです。"
        % (_hex(cr1), _hex(dier), _hex(psc), _hex(arr)))

    # Does the blinking actually come from the timer?
    #
    # Everything above is satisfied by a program that sets CEN and UIE,
    # never enables the interrupt in the NVIC, and blinks from a counting
    # loop at one second. This is the check that tells the two apart.
    # A PIN THAT NEVER MOVED PASSES THE QUESTION ABOVE WITHOUT ANSWERING IT.
    #
    # Stopping the timer and seeing nothing change is what a correct program
    # looks like. It is also what a program whose LED never lit looks like,
    # and this used to report 成功 for it: on 2026-11-20 a submission that
    # set PSC, ARR, DIER and the NVIC but never set CEN was told 「点滅は
    # タイマーによって作られている」 while its LED had not moved once.
    #
    # Nobody could pass by it -- 「LED が点滅する」 fails in the same run, so
    # the check still exits 1 -- but a learner reads the lines, not the exit
    # code, and that line sent them looking for a causation fault they did
    # not have. A verdict that reports 成功 on something it did not observe
    # is the fault three comments were deleted for on 2026-11-19.
    #
    # So the requirement needs blinking to attribute. With none, it is not
    # met: not "unknown", because the requirement is that THE BLINKING comes
    # from the timer, and there is no blinking.
    after = cl.transitions(stopped)
    if changes == 0:
        report.check(
            False, "点滅はタイマーによって作られている",
            "LED が一度も変化していないため、その点滅をタイマーが作って\n"
            "いるとは言えません。まず LED を点滅させてください。上の\n"
            "確認結果に、どのレジスタがまだ 0 のままかが出ています。\n"
            "ここで見ているのは、点滅がタイマーによって作られているか\n"
            "どうかなので、点滅が始まってから判断できるようになります。")
    else:
        report.check(
            after <= ALLOWED_AFTER_STOP,
            "点滅はタイマーによって作られている",
            "TIM2 を停止させたあとも、LED は %.1f 秒間で %d 回変化しました。\n"
            "波形  %s\n"
            "タイマーを止めれば点滅も止まるはずです。止まらないということは、\n"
            "点滅させているのはタイマーではなく、遅延ループなどの別の仕組み\n"
            "だということです。CEN と UIE を立ててあっても、そこから LED\n"
            "までが繋がっていなければこの課題にはなりません。割り込みを\n"
            "受け付けるよう NVIC に設定しているか、ハンドラ名がベクタ\n"
            "テーブルの期待どおりかを確認してください。"
            % (STEP * AFTER, after, cl.trace(stopped)))

    # The gap between asking and being heard. Not read from the NVIC --
    # Renode does not answer for it on the bus -- but inferred, and the
    # inference is sound: a correctly configured timer whose LED never
    # moves has essentially one cause.
    if running and asking and changes == 0:
        report.note(
            "注意: タイマーは数えており割り込みも要求していますが、"
            "LED は一度も変化しませんでした。要求することと受け取られ"
            "ることは別です。この割り込みを受け付けるようプロセッサに"
            "伝える必要があり、ハンドラの名前もベクタテーブルが"
            "期待するものと正確に一致している必要があります。")


def _hex(value):
    return "unreadable" if value is None else "0x%08X" % value


if __name__ == "__main__":
    sys.exit(cl.main("課題 2 - タイマー割り込みで LD2 を点滅させる", body))
