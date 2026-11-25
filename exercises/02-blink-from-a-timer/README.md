# Exercise 2 — blink LD2 from a timer

The same behaviour as exercise 1, with a timer keeping the time instead of the
processor counting. You will be working in [`main.c`](main.c).

<!-- section: functional-specification -->
## Functional specification

What the program has to do.

- The board's green LED (LD2) blinks.
- It blinks one second on, one second off.
- The blinking comes from a timer, not from a counting loop.

<!-- section: implementation-specification -->
## Implementation specification

What it has to use to do that. The registers are named here; their values are
not. Finding the values is the exercise.

- Use TIM2.
- TIM2 is on a different bus from GPIOA, so its clock is enabled in a
  different register. `RCC_APB1ENR`.
- A prescaler and a reload value make the one second. `TIMx_PSC` and
  `TIMx_ARR`. The timer's input is 84,000,000 ticks per second, and both
  registers hold one less than the number you want.
- The timer has to be told to raise an interrupt, and the processor has to be
  told to accept it. `TIMx_DIER` for the first, `NVIC_EnableIRQ()` for the
  second; the interrupt is called `TIM2_IRQn`.
- The interrupt flag has to be cleared. Which bit of `TIMx_SR`, and where. An
  interrupt that does not clear its flag fires again immediately, for ever.
- The timer has to be started counting. `TIMx_CR1`.
- The clock for GPIO port A has to be on and PA5 made an output, as in
  exercise 1.

The handler is already named in `main.c`. You do not register it anywhere:
the name matching an entry in the vector table in `lib/startup.c` is what
registers it.

<!-- section: what-to-read -->
### What you will need to read

<!-- generated: references -->
<!-- This block is generated from references.json. Do not edit it by hand; run python tools/gen_exercise_pages.py -->

- **RM0368** — STM32F401xB/C and STM32F401xD/E reference manual. The registers, bit by bit.
  Open [STM32F401 documentation](https://www.st.com/en/microcontrollers-microprocessors/stm32f401/documentation.html) and type `RM0368` into **Search documents by title**.

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
- **static-timer-clocks** — Peripheral clocks are not derived from the RCC and PLL registers.

The full text of each is in [`DIVERGENCES.md`](../../DIVERGENCES.md).

<!-- /generated -->

<!-- section: how-it-is-judged -->
## How it is judged

How the behaviour is observed. What the program has to do is stated once,
above, under **Functional specification**.

The check counts the LED going on and off and measures the interval between
changes. It also reads TIM2's registers, to see whether the timer is running
and asking for an interrupt.

Then it stops TIM2 part-way through the run, and your LED has to stop with it.
Registers saying the timer was set up do not say the timer is what moves the
pin — a program that configures TIM2 and then blinks from a counting loop
would satisfy everything else here, and that is precisely the difference
between this exercise and the last one.

The pin setup is not looked at. Exercise 1 looks at it; this exercise does
not. The GPIO half of this one can be wrong, or missing, and the LED will
still blink in the simulator. It will not light on a real board.

Run it yourself inside the container, once you have built:

```
python3 exercises/02-blink-from-a-timer/check.py \
  --elf exercises/02-blink-from-a-timer/firmware.elf
```

It answers `0` if your program did what the exercise asks, `1` if it did not,
and `2` if it could not tell. Two is not a failure — it means the check never
got far enough to have an opinion, usually because there is no build yet.

<!-- section: building-and-running -->
## Building and running

Choose this exercise in the board view and press **Build and run**.
[`../README.md`](../README.md) has the detail.
