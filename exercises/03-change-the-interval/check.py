"""Does pressing the button change how fast the LED blinks?

This exercise deliberately leaves the design open -- "two rates that
alternate, or a cycle through three, or fast while held", and polling or
EXTI as you prefer. So the check tests the one thing every permitted answer
has in common: before the press the LED blinks at one rate, and after it,
at another.

It accepts two kinds of evidence, and either alone is enough:

  - the blink visibly changes rate, or
  - the timer's period changes, whether through the reload value or the
    prescaler.

Two, because a learner who picks two rates close together is right and
would be invisible to the first test over any window short enough to run;
and a learner who changes the rate some other way is right and would be
invisible to the second.

The button is pressed and held rather than tapped, because "fast while
held" is one of the designs the exercise offers.

    python check.py --elf firmware.elf
"""

import os
import sys

sys.path.insert(0, os.path.join(
    os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))),
    "tools"))

import checklib as cl  # noqa: E402

STEP = 0.1
BEFORE = 30         # 3.0s at the first rate
AFTER = 30          # 3.0s with the button held

# 2.0s watching a pin that should be still, once the timer is stopped from
# outside. The slower of this exercise's rates changes about every half
# second, so a program blinking from a counting loop shows several changes
# here and one driven by TIM2 shows none.
STOPPED = 20

# As exercise 2: a timer stopped between its last update and our write can
# leave one interrupt already pending, and the handler may run it.
ALLOWED_AFTER_STOP = 1

TIMER_TICK = 84000000.0


def period_of(psc, arr):
    """Seconds between timer updates, from the two registers that set it."""
    if psc is None or arr is None:
        return None
    if arr in (0, 0xFFFFFFFF):
        return None
    return (psc + 1.0) * (arr + 1.0) / TIMER_TICK


def body(elf, report):
    steps = []
    for _ in range(BEFORE):
        steps.append(cl.run_for(STEP))
        steps.append(cl.read("before", cl.led()))
    steps.append(cl.read("psc1", cl.word(cl.TIM2_PSC)))
    steps.append(cl.read("arr1", cl.word(cl.TIM2_ARR)))

    steps.append(cl.press())
    for _ in range(AFTER):
        steps.append(cl.run_for(STEP))
        steps.append(cl.read("after", cl.led()))
    steps.append(cl.read("psc2", cl.word(cl.TIM2_PSC)))
    steps.append(cl.read("arr2", cl.word(cl.TIM2_ARR)))
    steps.append(cl.read("cr1", cl.word(cl.TIM2_CR1)))
    steps.append(cl.release())

    # Then take the timer away, as exercise 2 does.
    #
    # Deliberately NOT a third window checking that the rate returns when
    # the button comes up. That would read as the obvious test and it
    # would be wrong: this exercise offers "two rates that alternate" as
    # one of its designs, and a learner who toggles on each press is
    # correct and would never restore the first rate on release. Both
    # reference solutions happen to be "fast while held", so they would
    # not have caught it -- which is the limit ADR-0027 states about
    # itself.
    #
    # Stopping the timer asks the thing the exercise actually requires,
    # and asks it the same way whatever design the learner chose.
    steps.append(cl.write(cl.TIM2_CR1, 0))
    for _ in range(STOPPED):
        steps.append(cl.run_for(STEP))
        steps.append(cl.read("stopped", cl.led()))

    values, seconds = cl.simulate(elf, steps)
    before = cl.series(values, "before")
    after = cl.series(values, "after")
    stopped = cl.series(values, "stopped")

    report.note("PA5 を %.1f 秒観測し、B1 を押してさらに %.1f 秒観測しました"
                "（実時間 %.1f 秒）"
                % (STEP * BEFORE, STEP * AFTER, seconds))
    report.note("押していないとき  %s" % cl.trace(before))
    report.note("押しているとき    %s" % cl.trace(after))

    total = cl.transitions(before) + cl.transitions(after)
    report.check(total >= 3, "LED が点滅する",
                 "LED の状態変化は全体で %d 回でした。課題 3 は課題 2 の\n"
                 "続きなので、ボタンで変える前に、タイマーによる点滅が\n"
                 "動いている必要があります。" % total)

    cr1 = cl.as_int(cl.first(values, "cr1"))
    report.check(bool(cr1 is not None and cr1 & 0x1),
                 "TIM2 が動作を続けている",
                 "TIM2 CR1=%s\n"
                 "点滅は引き続きタイマーで作ります。ボタンが変えるのは\n"
                 "速さであって、点滅させる仕組みそのものではありません。"
                 % ("unreadable" if cr1 is None else "0x%08X" % cr1))

    # The gap between a timer that counts and a pin that moves. Exercise 2's
    # check says this for the same signature and the same reason: told only
    # that the LED did not blink, a learner whose timer is plainly running
    # goes back over the timer setup, which is the one part that is right.
    if total == 0 and cr1 is not None and cr1 & 0x1:
        report.note(
            "注意: TIM2 は数えていますが、LED は一度も変化しませんでした。"
            "タイマーの設定ではなく、その先を見てください。割り込みを"
            "受け付けるようプロセッサに伝えているか（NVIC）、ハンドラの"
            "名前がベクタテーブルの期待どおりか、PA5 が出力に設定されて"
            "いるかです。課題 2 と同じ原因です。")

    # --- did anything change? -----------------------------------------
    was = cl.transitions(before)
    now = cl.transitions(after)
    rate_changed = abs(now - was) >= 2

    p1 = period_of(cl.as_int(cl.first(values, "psc1")),
                   cl.as_int(cl.first(values, "arr1")))
    p2 = period_of(cl.as_int(cl.first(values, "psc2")),
                   cl.as_int(cl.first(values, "arr2")))
    timer_changed = bool(p1 and p2 and abs(p1 - p2) > 1e-6)

    detail = [
        "点滅の変化回数: 押す前 %d 回、押している間 %d 回" % (was, now),
        "タイマーの周期: 押す前 %s、押している間 %s"
        % (_secs(p1), _secs(p2)),
        "",
        "B1 を押したら、LED の点滅の速さが変わるはずです。ボタンは押した",
        "ときに LOW になることに注意してください。プルアップが PC13 を",
        "High に保っているため、押した状態が 0 です。ここを逆に読んで",
        "しまうのが、他がすべて通っているのにこの項目だけ失敗する",
        "いちばんよくある原因です。",
    ]
    report.check(rate_changed or timer_changed,
                 "ボタンを押すと点滅の速さが変わる",
                 "\n".join(detail))

    # CR1 above says the timer is running. It does not say the timer is
    # what moves the pin -- a program that sets CEN once and then blinks
    # from a counting loop, changing the loop's constant when the button
    # is down, satisfies every check above. Exercise 3 continues exercise
    # 2, so the blinking still has to come from the timer. ADR-0049.
    # As in exercise 2, and for the same reason: a pin that never moved
    # passes this without answering it. Stopping the timer and seeing
    # nothing change is what a correct program looks like AND what a dead
    # LED looks like, and reporting 成功 for the second sends a learner
    # hunting a causation fault they do not have. The requirement is that
    # THE BLINKING comes from the timer, so with no blinking it is not met.
    halted = cl.transitions(stopped)
    if total == 0:
        report.check(
            False, "点滅はタイマーによって作られている",
            "LED が一度も変化していないため、その点滅をタイマーが作って\n"
            "いるとは言えません。課題 3 は課題 2 の続きなので、まず\n"
            "タイマーによる点滅を動かしてから、ボタンで速さを変えます。")
    else:
        report.check(
            halted <= ALLOWED_AFTER_STOP,
            "点滅はタイマーによって作られている",
            "TIM2 を停止させたあとも、LED は %.1f 秒間で %d 回変化しました。\n"
            "波形  %s\n"
            "タイマーを止めれば点滅も止まるはずです。止まらないということは、\n"
            "速さは変わっていても、点滅そのものはタイマーではなく別の仕組み\n"
            "で作られているということです。課題 3 は課題 2 の続きなので、\n"
            "点滅はタイマーの割り込みから作る必要があります。"
            % (STEP * STOPPED, halted, cl.trace(stopped)))


def _secs(value):
    return "unreadable" if value is None else "%.3fs" % value


if __name__ == "__main__":
    sys.exit(cl.main(
        "課題 3 - ボタンで点滅の間隔を変える", body))
