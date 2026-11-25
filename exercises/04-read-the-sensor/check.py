"""Does the bar follow the temperature?

Exercise 4 lets you choose your own thresholds, so there is no particular
pattern of lit LEDs that is correct. What is correct whatever you chose is
the SHAPE: as the sensor gets warmer, the number of lit LEDs must never go
down, and somewhere across the range it must go up. That is what a bar is,
and it is checkable without anybody being told where to put their
thresholds.

It also establishes that the sensor is really being read, without having to
watch the I2C bus: a display that changes when the temperature changes is
reading the temperature from somewhere, and there is nowhere else.

WHAT THIS DOES NOT CHECK, AND CANNOT
------------------------------------
Your pin setup. Renode's I2C model never looks at the GPIO registers, so
firmware with every GPIOB write deleted still reads the sensor correctly.
The clock enables, the alternate-function mode and the open-drain output
type are invisible here and decisive on hardware. See
'pin-configuration-not-enforced' and 'open-drain-ignored' in DIVERGENCES.md.

Nor your exact thresholds, nor the order you light the LEDs in. Four LEDs
lighting up from D5 downwards is as good a bar as four lighting up from D2
upwards.

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

HERE = os.path.dirname(os.path.abspath(__file__))
PARTS = os.path.relpath(os.path.join(HERE, "parts.repl"), cl.ROOT)

# Where the four LEDs sit, from the exercise: D2 is PA10, and D3, D4 and D5
# are on port B. The board view names a part it adds after its kind and its
# label, so these are the names on your own board too.
LEDS = (("d2", "sysbus.gpioPortA.led_d2 State"),
        ("d3", "sysbus.gpioPortB.led_d3 State"),
        ("d4", "sysbus.gpioPortB.led_d4 State"),
        ("d5", "sysbus.gpioPortB.led_d5 State"))

# A wide spread rather than two ends, so a learner whose thresholds sit in
# one corner of the range still shows a rising bar somewhere in it. Reported
# in the output, so that anybody who chose differently can see the figures
# the check used rather than guess at them.
#
# The ORDER they are presented in is deliberately not the order they are
# judged in, and the first one comes round again at the end.
#
# A rising sweep, each point read once, is satisfied completely by a program
# that never reads the sensor and simply lights more LEDs the longer it runs.
# Such a program cannot follow a sequence that goes down as well as up, and
# it cannot come back to the reading it gave at the start. Going out of order
# is what defeats the ramp; the revisit is what shows the bar is a function
# of the sensor rather than of the clock. ADR-0049.
ORDER = (15, 45, 0, 30, 15)
TEMPERATURES = tuple(sorted(set(ORDER)))

# How far the bar may differ when the first temperature is presented again.
#
# Exact equality would be the stronger test and is wrong here: a learner who
# adds hysteresis so the bar does not flicker at a threshold has done
# something defensible, and arriving at 15 from above rather than from below
# would legitimately differ -- by one LED. The program this exists to catch
# is out by its whole range, not by one step: a ramp over this sweep lights
# three or four more LEDs by the end.
#
# The sensor's own quantisation does not come into it. The model converts
# through fixed point deterministically, so the same commanded temperature
# gives the same reading; this tolerance is for the learner's logic.
REVISIT_TOLERANCE = 1

# Long enough for a main loop to read the sensor and write the pins at least
# once after each change, and no longer.
#
# This is a budget, not a comfort. A program that touches peripherals in a
# tight loop simulates at roughly a hundred times slower than real time, so
# board time is the expensive thing here: five samples of 0.2s came to one
# second, which is the simulator's hundred-second limit exactly. A learner
# whose bar was correct but whose loop was tight could never get past "could
# not observe". Observed on a real submission, 2026-10-13.
#
# Four samples of 0.1s is 0.4 seconds, so the same tight loop finishes well
# inside the limit and gets a real verdict instead of silence.
SETTLE = 0.1


def body(elf, report):
    steps = []
    # Labelled by position rather than by temperature: the first
    # temperature appears twice and the two readings must not collide.
    for index, celsius in enumerate(ORDER):
        steps.append(("sysbus.i2c1.si7021 Temperature %d" % celsius,))
        steps.append(cl.run_for(SETTLE))
        for label, expression in LEDS:
            steps.append(cl.read("%s@%d" % (label, index), expression))
    # What the program left configured, read once at the end.
    #
    # This used to say that pin configuration is never judged here,
    # because "requiring it here would fail a program that works on this
    # simulator while passing one that would not work on the board". That
    # argument is sound, and it is an argument about the OUTPUT TYPE: a
    # write to OTYPER is refused and logged, so open drain genuinely
    # cannot be read back and must not be required.
    #
    # It does not reach the rest. The port clock, the pin mode and the
    # alternate function number are all kept by the bus -- measured
    # 2026-11-19, GPIOB_AFRH reads back 0x00000044 after firmware selects
    # AF4 on PB8 and PB9 -- and the I2C model ignoring them is exactly why
    # a learner can get them wrong here and be told nothing. So those
    # three are judged and the output type is not. ADR-0052.
    #
    # The pins are safe to name because the exercise fixes them: "there is
    # no pin to choose".
    steps.append(cl.read("moder_a", cl.word(cl.GPIOA_MODER)))
    steps.append(cl.read("moder_b", cl.word(cl.GPIOB_MODER)))
    steps.append(cl.read("ahb1enr", cl.word(cl.RCC_AHB1ENR)))
    steps.append(cl.read("afrh_b", cl.word(cl.GPIOB_AFRH)))

    values, seconds = cl.simulate(elf, steps, extra=(PARTS,))

    lit = []
    for index in range(len(ORDER)):
        states = [cl.first(values, "%s@%d" % (label, index))
                  for label, _ in LEDS]
        if any(state is None for state in states):
            # A missing reading means a part was not on the board, which is
            # ours to get right rather than the learner's: this check brings
            # its own parts. Saying "your program is wrong" here would blame
            # somebody for our own fixture.
            raise cl.CouldNotRun(
                "4 つの LED のうち少なくとも 1 つの状態が読み取れません"
                "でした。確認用のボード定義 (parts.repl) が読み込めて"
                "いない可能性があります。課題の不合格ではありません。")
        lit.append(sum(1 for state in states if state == "True"))

    report.note("センサーの温度を %s ℃ の順に設定して、そのたびに D2〜D5 を"
                "読みました（実時間 %.1f 秒）"
                % ("、".join(str(t) for t in ORDER), seconds))
    report.note("点灯数  %s"
                % " → ".join("%d℃:%d" % (t, n)
                             for t, n in zip(ORDER, lit)))

    # The sweep is presented out of order; it is judged in temperature
    # order. Everything below reads from this, never from the sequence.
    by_temperature = dict(zip(ORDER[:-1], lit[:-1]))
    rising = [by_temperature[t] for t in TEMPERATURES]

    # Nothing lit has two causes and the advice differs. The four pins
    # being outputs says the learner has done the pin setup, so the
    # remaining suspects are the sensor read and the write to ODR -- and
    # telling them to look at pins they configured correctly wastes the
    # one piece of information this check has.
    moder_a = cl.as_int(cl.first(values, "moder_a"))
    moder_b = cl.as_int(cl.first(values, "moder_b"))
    ahb1enr = cl.as_int(cl.first(values, "ahb1enr"))
    afrh_b = cl.as_int(cl.first(values, "afrh_b"))
    if None in (moder_a, moder_b, ahb1enr, afrh_b):
        raise cl.CouldNotRun(
            "ピンの設定レジスタを読み取れなかったため、設定を確認でき"
            "ませんでした。課題の不合格ではありません。")
    pins_ready = all([cl.pin_is_output(moder_a, 10),
                      cl.pin_is_output(moder_b, 3),
                      cl.pin_is_output(moder_b, 4),
                      cl.pin_is_output(moder_b, 5)])
    if pins_ready:
        dark = ("どの温度でも D2〜D5 がすべて消灯したままでした。\n"
                "D2〜D5 はいずれも出力に設定されています。ピンの設定では\n"
                "なく、その先を見てください。センサーから温度を読めて\n"
                "いるか、読んだ値で ODR に書き込んでいるかです。\n"
                "まず温度を読まずに 1 つだけ点灯させて、配線側と判定側の\n"
                "どちらの問題か切り分けるのが早いです。")
    else:
        dark = ("どの温度でも D2〜D5 がすべて消灯したままでした。\n"
                "センサーを読めていないか、読んだ値で LED を点けて\n"
                "いません。まず 1 つだけでも点灯させてみてください。")
    anything_lit = max(lit) > 0
    report.check(anything_lit, "LED が点灯する", dark)

    # A BAR THAT NEVER LIGHTS SATISFIES TWO OF THE SHAPE TESTS WITHOUT
    # SHOWING ANYTHING.
    #
    # Nothing ever falls in a row of zeroes, and zero equals zero when the
    # temperature comes round again -- so this verdict and the revisit one
    # below both used to report 成功 on a program that lit no LED at all.
    # Found 2026-11-20 while reading what the assistant is now sent: these
    # lines go into the prompt as well as to the learner, so a vacuous 成功
    # tells the model the shape is right and points it away from the part
    # that is wrong.
    #
    # Not a way to pass -- 「LED が点灯する」 and 「温度に反応する」 both
    # fail in the same run -- but a shape test with no shape to judge must
    # not claim it judged one.
    falls = [(TEMPERATURES[i], rising[i], TEMPERATURES[i + 1], rising[i + 1])
             for i in range(len(rising) - 1) if rising[i + 1] < rising[i]]
    if not anything_lit:
        report.check(
            False, "暖かくなるほど点灯数が減らない",
            "LED が一度も点灯していないため、点灯数の増え方を見ることが\n"
            "できません。まず 1 つだけでも点灯させてください。")
    else:
        report.check(
            not falls, "暖かくなるほど点灯数が減らない",
            "" if not falls else
            "%d℃ で %d 個だった点灯数が、%d℃ では %d 個に減りました。\n"
            "棒グラフは、暖かくなるほど点灯数が増えるものです。\n"
            "しきい値の比較の向きを確認してください。" % falls[0])

    report.check(
        max(rising) > min(rising), "温度に反応する",
        "%d℃ から %d℃ まで変えても点灯数が %d 個のまま変わりません"
        "でした。\n"
        "読んだ温度が LED に反映されていないか、しきい値がすべて"
        "この範囲の外にあります。\n"
        "しきい値はご自身で決めるものですが、この確認は %s ℃ で見ます。"
        % (TEMPERATURES[0], TEMPERATURES[-1], rising[0],
           "〜".join(str(t) for t in (TEMPERATURES[0], TEMPERATURES[-1]))))

    # Back to where we started. A bar that follows the sensor returns to
    # the reading it gave the first time; one that follows elapsed time
    # cannot, because time has only gone forwards.
    came_back = abs(lit[-1] - lit[0])
    if not anything_lit:
        # Zero equals zero. See the note above the falls test.
        report.check(
            False, "同じ温度に戻ると表示も戻る",
            "LED が一度も点灯していないため、同じ温度で同じ表示に戻るか\n"
            "を見ることができません。まず温度を表示させてください。")
    else:
        report.check(
            came_back <= REVISIT_TOLERANCE,
            "同じ温度に戻ると表示も戻る",
            "最初に %d℃ で %d 個だった点灯数が、最後にもう一度 %d℃ に"
            "戻したときには %d 個でした。\n"
            "同じ温度なら、表示も同じに戻るはずです。%d 個の差があるという\n"
            "ことは、表示がセンサーの値ではなく、経過時間や呼び出し回数など\n"
            "別のものに従っている可能性があります。\n"
            "温度を読まずに表示を変えていないか確認してください。"
            % (ORDER[0], lit[0], ORDER[-1], lit[-1], came_back))

    # The bus pins. Renode's I2C model never looks at these, which is
    # precisely why nothing else here can catch them: a transfer succeeds
    # with the pins untouched, so the sensor is read and the bar is right
    # and the program would do nothing at all on a bench. Verified
    # 2026-09-25 by deleting every GPIOB write -- the Si7021 still read
    # correctly.
    clocked_b = bool(ahb1enr & cl.RCC_AHB1ENR_GPIOBEN)
    handed_over = all([cl.pin_is_alternate(moder_b, 8),
                       cl.pin_is_alternate(moder_b, 9)])
    right_function = all([cl.pin_alternate_is(afrh_b, 8, cl.AF_I2C1),
                          cl.pin_alternate_is(afrh_b, 9, cl.AF_I2C1)])

    if not clocked_b:
        bus_why = ("GPIOB のクロックが有効になっていません。ポートの\n"
                   "クロックを入れないと、実機ではそのポートのレジスタ\n"
                   "への書き込みが効きません。")
    elif not handed_over:
        bus_why = ("PB8 と PB9 が MODER で代替機能モードになっていま\n"
                   "せん。10 が代替機能です。出力やデフォルトのままでは、\n"
                   "実機でピンは I2C1 に繋がりません。")
    else:
        bus_why = ("PB8 と PB9 は代替機能モードですが、選んでいる代替\n"
                   "機能が I2C1 ではありません。AFRH で AF%d を選びます。\n"
                   "どの番号がどの機能かは DS10086 の代替機能表にあり、\n"
                   "リファレンスマニュアルではありません。" % cl.AF_I2C1)

    report.check(
        clocked_b and handed_over and right_function,
        "I2C1 のピンが設定されている",
        "RCC_AHB1ENR=0x%08X GPIOB_MODER=0x%08X GPIOB_AFRH=0x%08X\n"
        "%s\n"
        "このシミュレータの I2C はピンの設定を一切見ないため、設定が\n"
        "なくても通信は成功します。実機では、周辺機能がピンに届くのは\n"
        "そのピンを経由する場合だけです。\n"
        "DIVERGENCES.md の 'pin-configuration-not-enforced' を参照して\n"
        "ください。\n"
        "なお、オープンドレインの設定だけはここでは確認できません。\n"
        "実機では必須です。'open-drain-ignored' を参照してください。"
        % (ahb1enr, moder_b, afrh_b, bus_why))


if __name__ == "__main__":
    sys.exit(cl.main("課題 4 - センサーの値を 4 つの LED に表示する", body))
