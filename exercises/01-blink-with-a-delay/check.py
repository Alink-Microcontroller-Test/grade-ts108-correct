"""Does the LED blink?

That is the whole of exercise 1, and the check asks no more than that.

Deliberately nothing about the rate. The exercise supplies the delay
constant rather than asking anybody to derive it, says in its own comments
that a delay written this way is never accurate, and the commissioning
party's brief states no frequency for this exercise. Requiring a period
here would fail correct work over a number nobody was asked to hit.

    python check.py --elf firmware.elf
"""

import os
import sys

sys.path.insert(0, os.path.join(
    os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))),
    "tools"))
sys.path.insert(0, os.path.join(
    os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))))

import checklib as cl  # noqa: E402

# Long enough to see several blinks at the supplied constant (about one
# second each), and short enough to stay well inside the grader's budget.
STEP = 0.1
COUNT = 60


def body(elf, report):
    steps = []
    for _ in range(COUNT):
        steps.append(cl.run_for(STEP))
        steps.append(cl.read("led", cl.led()))
    # Read after the run, not before: the question is what the program
    # left configured, and a learner who sets the pin up inside the loop
    # has still set it up.
    steps.append(cl.read("ahb1enr", cl.word(cl.RCC_AHB1ENR)))
    steps.append(cl.read("moder", cl.word(cl.GPIOA_MODER)))

    values, seconds = cl.simulate(elf, steps)
    lit = cl.series(values, "led")

    report.note("PA5 をボード時間で %.1f 秒間（実時間 %.1f 秒）観測しました"
                % (STEP * COUNT, seconds))
    report.note("波形  %s" % cl.trace(lit))

    # A flat waveform has two unrelated causes, and the advice for one is
    # useless for the other. Nothing written yet: set the pin up. Written
    # and stuck: the setup is already right and the program never reached
    # the part that moves the pin -- an endless loop with no toggle in it,
    # or a fault that trapped. Telling the second learner to check the
    # clock they already enabled sends them hunting for a mistake they
    # did not make, which is the failure mode ADR-0028's exercise-2 note
    # was written about.
    ahb1enr = cl.as_int(cl.first(values, "ahb1enr"))
    moder = cl.as_int(cl.first(values, "moder"))
    if ahb1enr is None or moder is None:
        # These decide a verdict now, not just a choice of words. A
        # register we could not read is our problem, and reporting it as
        # the learner's would fail somebody for our fixture (ADR-0021).
        raise cl.CouldNotRun(
            "RCC_AHB1ENR と GPIOA_MODER を読み取れなかったため、ピンの"
            "設定を確認できませんでした。課題の不合格ではありません。")
    clocked = bool(ahb1enr & cl.RCC_AHB1ENR_GPIOAEN)
    an_output = cl.pin_is_output(moder)

    if clocked and an_output:
        why = ("PA5 が一度も High になりませんでした。ただしクロックは\n"
               "有効で、PA5 は MODER で出力に設定されています。設定は\n"
               "できていて、ピンを動かすところまで到達していない状態\n"
               "です。ODR への書き込みに辿り着く前にループが終わらない\n"
               "か、処理が止まっている可能性があります。main ループが\n"
               "ODR の書き込みに届いているか確認してください。\n"
               "ハンドラ名の誤りなどで停止した場合も同じ波形になります。")
    else:
        why = ("PA5 が一度も High になりませんでした。実行中ずっと消灯\n"
               "したままです。GPIOA のクロックが有効か、PA5 が MODER で\n"
               "出力に設定されているか、ODR に書き込んでいるかを\n"
               "確認してください。")
    report.check("True" in lit, "LED が点灯する", why)

    # "went off again", not "was ever off" -- a pin that never came on is
    # off for the whole run, and reporting that as a pass would be a lie
    # told to somebody who has written nothing yet.
    went_off = any(a == "True" and b == "False" for a, b in zip(lit, lit[1:]))
    report.check(went_off, "LED が消灯する",
                 "PA5 が High から Low になりませんでした。点灯させるだけ\n"
                 "でなく消灯させる処理も必要です。そうでなければ点滅では\n"
                 "なく点灯し続けているだけです。")

    changes = cl.transitions(lit)
    report.check(changes >= 3, "点滅を繰り返す",
                 "LED の状態が %.1f 秒間で %d 回しか変化しませんでした。\n"
                 "点滅とは、点灯と消灯を繰り返すことです。1 回だけの変化\n"
                 "は、一度点いただけの状態です。"
                 % (STEP * COUNT, changes))

    # The exercise is two steps -- set the pin up, then move it -- and
    # until now only the second was judged. Renode drives the LED from
    # ODR alone, so firmware that skips the setup entirely blinks
    # perfectly here and does nothing at all on a board: measured
    # 2026-09-30, it passed this check 3 of 3, and 34 of this course's 39
    # passes were taken under that. Both registers are kept by the bus, so
    # the one thing the simulator will not tell a learner is the one thing
    # this can. ADR-0049 for why a check tests the mechanism, ADR-0052 for
    # why this register and not the output type.
    if not clocked and not an_output:
        missing = ("GPIOA のクロックが有効になっておらず、PA5 も出力に\n"
                   "設定されていません。どちらも必要です。")
    elif not clocked:
        missing = ("PA5 は出力に設定されていますが、GPIOA のクロックが\n"
                   "有効になっていません。クロックのないポートは、"
                   "実機では\n書き込みを受け付けません。")
    else:
        missing = ("GPIOA のクロックは有効ですが、PA5 が MODER で出力に\n"
                   "設定されていません。01 が出力です。")
    report.check(
        clocked and an_output, "PA5 が出力として設定されている",
        "RCC_AHB1ENR=0x%08X GPIOA_MODER=0x%08X\n"
        "%s\n"
        "シミュレータは ODR への書き込みだけで LED を動かすため、設定を\n"
        "省いても画面の上では点滅します。実機では何も起きません。\n"
        "DIVERGENCES.md の 'pin-configuration-not-enforced' を参照して\n"
        "ください。" % (ahb1enr, moder, missing))


if __name__ == "__main__":
    sys.exit(cl.main("課題 1 - ソフトウェアの遅延で LD2 を点滅させる", body))
