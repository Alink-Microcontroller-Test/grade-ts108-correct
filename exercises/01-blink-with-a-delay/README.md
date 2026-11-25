# Exercise 1 — blink LD2 with a delay

Turn the green LED on and off by counting in a loop. You will be working in
[`main.c`](main.c).

<!-- section: functional-specification -->
## Functional specification

What the program has to do.

- The board's green LED (LD2) blinks.
- It goes on and off repeatedly, rather than being lit once.
- No particular rate is asked for.

<!-- section: implementation-specification -->
## Implementation specification

What it has to use to do that. The registers are named here; their values are
not. Finding the values is the exercise.

- LD2 is wired to PA5.
- The clock for GPIO port A has to be turned on. `RCC_AHB1ENR` in RM0368.
- PA5 has to be told it is an output. The GPIO port mode register (`MODER`).
  How many bits describe each pin, and which value means output, are both in
  the manual.
- The pin has to be driven high and low. The GPIO port output data register
  (`ODR`).
- The wait is counted in a loop. `ABOUT_ONE_SECOND` in `main.c` is given to
  you.

The register names are available to you through the header. Type `GPIOA->` and
your editor will list them. The names are given; the numbers are yours to
find.

`ABOUT_ONE_SECOND` is approximate, and that is the point: a delay written this
way is never accurate, which is what exercise 2 replaces with a timer. It is
approximate for a second reason worth knowing. The simulator runs the
processor at a flat rate unrelated to the clock frequency this board
describes — so the constant was found by measuring rather than by arithmetic
on the clock, and it would not be the right number on real hardware. See the
`cpu-speed-not-from-the-clock-tree` row below.

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

The full text of each is in [`DIVERGENCES.md`](../../DIVERGENCES.md).

<!-- /generated -->

<!-- section: how-it-is-judged -->
## How it is judged

How the behaviour is observed. What the program has to do is stated once,
above, under **Functional specification**.

The check counts the LED going on and off. It also reads the port's
clock-enable bit and `MODER` back after your program has run, to see whether
PA5 was set up to be driven. Setting the pin up inside your loop is fine —
they are read at the end, not the start.

The configuration is looked at because the simulator will light the LED from a
write to `ODR` alone, with no clock and no mode register. That is not how a
real board behaves, and it means the blinking on its own cannot tell a
finished exercise from one where both setup steps were skipped.

Not how fast.

Run it yourself inside the container, once you have built:

```
python3 exercises/01-blink-with-a-delay/check.py \
  --elf exercises/01-blink-with-a-delay/firmware.elf
```

It answers `0` if your program did what the exercise asks, `1` if it did not,
and `2` if it could not tell. Two is not a failure — it means the check never
got far enough to have an opinion, usually because there is no build yet.

<!-- section: building-and-running -->
## Building and running

Choose this exercise in the board view and press **Build and run**.
[`../README.md`](../README.md) has the detail.
