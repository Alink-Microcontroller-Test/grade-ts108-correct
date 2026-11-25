# Exercise 3 — change the interval with the button

Start from your exercise 2 code, and make the user button change how fast the
LED blinks. You will be working in [`main.c`](main.c).

<!-- section: functional-specification -->
## Functional specification

What the program has to do.

- As in exercise 2, the board's green LED (LD2) blinks from a timer.
- Pressing the user button changes how fast it blinks.
- How you define that is up to you: two rates that alternate, a cycle through
  three, or fast while held.
- The blinking still comes from the timer. The button changes how fast, not
  what makes it happen.

<!-- section: implementation-specification -->
## Implementation specification

What it has to use to do that. The registers are named here; their values are
not. Finding the values is the exercise.

- B1, the blue button on the board, is connected to PC13.
- PC13 is on a different port from the LED, so its clock is a different bit of
  the same register.
- PC13 has to be made an input. Which value in `GPIOx_MODER`.
- The register you read to see what an input pin is doing. It is not the one
  you wrote to in exercise 1.
- **The button reads high when it is not pressed.** A pull-up resistor holds
  PC13 high, and pressing the button connects the pin to ground. So a press is
  a zero, not a one. This catches almost everybody once.
- Changing the blink rate means changing the timer, not a delay loop. Which
  register holds the reload value, and what happens if you write it while the
  timer is running.
- The clock for GPIO port C has to be turned on.

Two ways to notice the button.

**Polling** — read the pin in your main loop. Simple, and fine here.

**Interrupt** — have the pin itself interrupt you, through EXTI. More work,
and closer to how a real product does it. The handler would be called
`EXTI15_10_IRQHandler`, because PC13 shares an interrupt with pins ten to
fifteen.

Either is a correct answer to this exercise.

**If you poll, put a short delay between reads.**

```
while (1) {
    wait_a_little();         // any small delay will do
    // read the button here
}
```

On real hardware a loop that reads the pin as fast as it can is merely
wasteful. In the simulator it is much worse than that: reading a peripheral
register is expensive to simulate, so a loop that does nothing else runs far
slower than real time. Your one-second blink then arrives once every few
minutes, and your perfectly correct program looks broken.

Measured: tight polling, 156x slower than real time. The same code with a
short delay between reads, 2.5x. See the
`peripheral-reads-are-slow-to-simulate` row below.

<!-- section: what-to-read -->
### What you will need to read

<!-- generated: references -->
<!-- This block is generated from references.json. Do not edit it by hand; run python tools/gen_exercise_pages.py -->

- **RM0368** — STM32F401xB/C and STM32F401xD/E reference manual. The registers, bit by bit.
  Open [STM32F401 documentation](https://www.st.com/en/microcontrollers-microprocessors/stm32f401/documentation.html) and type `RM0368` into **Search documents by title**.
- **UM1724** — STM32 Nucleo-64 boards (MB1136) user manual. Which pin is which on the board's headers.
  Open [STM32 Nucleo boards documentation](https://www.st.com/en/evaluation-tools/stm32-nucleo-boards/documentation.html) and type `UM1724` into **Search documents by title**. The list holds forty user manuals, so looking down it is not practical.

<!-- /generated -->

<!-- section: divergences -->
## The simulator is not the board

<!-- generated: divergences -->
<!-- This block is generated from divergences.json. Do not edit it by hand; run python tools/gen_exercise_pages.py -->

**These can let wrong code look right.** The simulator is more permissive than the board here, so it will not tell you:

- **pin-configuration-not-enforced** — A bus controller never consults the GPIO registers. The I2C model reads no port mode, no alternate function and no clock-enable bit, so a transfer succeeds even when the pins it supposedly uses were never configured at all. Verified 2026-09-25: firmware with every GPIOB write removed still read the Si7021 correctly
  On real hardware: A peripheral reaches a pin only through that pin. The port's clock must be enabled, the pin put into alternate-function mode, and the correct alternate function selected. Miss any of them and nothing reaches the bus
- **superset-peripherals** — The generic STM32F4 platform declares peripherals the F401RE does not carry: an Ethernet MAC, CAN1 and CAN2, GPIO ports F through K, UART4 and UART5, an external memory controller, and TIM6, TIM7, TIM8, TIM12, TIM13 and TIM14. Overriding cannot remove them, so they remain usable
  On real hardware: An STM32F401RE has GPIO ports A to E and H, three USARTs, no CAN, no Ethernet, no external memory controller, and timers TIM1 to TIM5 and TIM9 to TIM11

Also true here, and worth knowing:

- **cpu-speed-not-from-the-clock-tree** — The processor executes a flat 100 million instructions per second, declared as PerformanceInMips and unrelated to the 84 MHz this board describes.
- **peripheral-reads-are-slow-to-simulate** — Reading a peripheral register costs far more simulated-machine effort than reading a variable, because it leaves the translated code and goes through the system bus.
- **static-timer-clocks** — Peripheral clocks are not derived from the RCC and PLL registers.

The full text of each is in [`DIVERGENCES.md`](../../DIVERGENCES.md).

<!-- /generated -->

<!-- section: how-it-is-judged -->
## How it is judged

How the behaviour is observed. What the program has to do is stated once,
above, under **Functional specification**.

Because the design is yours, the check tests only what every permitted answer
has in common. It measures the blink rate before the button is pressed and
after, and requires them to differ. It reads TIM2's registers, to see that the
timer is still running.

Then it stops TIM2 part-way through the run, and your LED has to stop with it.
This exercise continues the previous one, so the blink is still the timer's
work.

The pin setup is not looked at, on either pin. Exercise 1 looks at it; this
exercise does not. The output on PA5 and the input on PC13 can both be wrong
or absent and this exercise will still behave correctly in the simulator. It
will not work on a real board.

Run it yourself inside the container, once you have built:

```
python3 exercises/03-change-the-interval/check.py \
  --elf exercises/03-change-the-interval/firmware.elf
```

It answers `0` if your program did what the exercise asks, `1` if it did not,
and `2` if it could not tell. Two is not a failure — it means the check never
got far enough to have an opinion, usually because there is no build yet.

<!-- section: building-and-running -->
## Building and running

Choose this exercise in the board view and press **Build and run**.
[`../README.md`](../README.md) has the detail.
