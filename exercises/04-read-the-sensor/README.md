# Exercise 4 — read the sensor over I2C

Read a temperature sensor over I2C and show the reading across a row of LEDs.
You will be working in [`main.c`](main.c).

<!-- section: functional-specification -->
## Functional specification

What the program has to do.

- Read the Si7021 temperature sensor over I2C.
- Show the reading across four LEDs, like a bar: colder lights fewer, warmer
  lights more.
- You choose the thresholds, but put them inside 0 to 45 degrees. That is the
  range the check sweeps, and a threshold outside it is never crossed.
- Returning to the same temperature shows the same bar again.

<!-- section: implementation-specification -->
## Implementation specification

What it has to use to do that. The registers are named here; their values are
not. Finding the values is the exercise. The sensor's address, its command
byte and the conversion are given to you, in `main.c`.

- The sensor goes on I2C1, which is already on the Arduino connector at D15
  (PB8) for SCL and D14 (PB9) for SDA, so there is no pin to choose.
- I2C1's clock is on APB1.
- Both pins need their alternate function set to the one that means I2C.
  `GPIOx_AFRH`, and the alternate function table in the datasheet (DS10086),
  not the reference manual.
- Both pins need open-drain output type. The bus on a real board does not
  work without it.
- The I2C peripheral needs its input clock frequency, a speed setting and a
  rise time before it is enabled. `I2C_CR2`, `I2C_CCR` and `I2C_TRISE`.
- A read from this sensor is: start, address with the write bit, the command
  byte, a repeated start, address with the read bit, then two bytes most
  significant first. Watch how each step is acknowledged in `I2C_SR1`.
- Use the datasheet's conversion. You have no floating point enabled, so do it
  in fixed point — work in hundredths of a degree and keep the intermediate
  value in a `uint32_t`.
- The LED pins have to be outputs: the board's own on PA5, and the four you
  added. Which pins those are is in `main.c`.

A library is allowed for the I2C transfer if you would rather. The GPIO, the
timer and the conversion are the parts to do yourself.

<!-- section: what-to-read -->
### What you will need to read

<!-- generated: references -->
<!-- This block is generated from references.json. Do not edit it by hand; run python tools/gen_exercise_pages.py -->

- **RM0368** — STM32F401xB/C and STM32F401xD/E reference manual. The registers, bit by bit.
  Open [STM32F401 documentation](https://www.st.com/en/microcontrollers-microprocessors/stm32f401/documentation.html) and type `RM0368` into **Search documents by title**.
- **DS10086** — STM32F401xD/xE datasheet. Pins, and which peripheral each one can be switched to.
  Open [STM32F401 documentation](https://www.st.com/en/microcontrollers-microprocessors/stm32f401/documentation.html) and type `DS10086` into **Search documents by title**.
- **UM1724** — STM32 Nucleo-64 boards (MB1136) user manual. Which pin is which on the board's headers.
  Open [STM32 Nucleo boards documentation](https://www.st.com/en/evaluation-tools/stm32-nucleo-boards/documentation.html) and type `UM1724` into **Search documents by title**. The list holds forty user manuals, so looking down it is not practical.

<!-- /generated -->

<!-- section: before-you-start -->
## Before you start

Open the board view and add both parts. The board has one user LED and no
sensor. A real NUCLEO-F401RE has no sensor either, so neither is there until
you put it there:

- an **Si7021** temperature sensor, on I2C1
- **four more LEDs**, for the bar

On real hardware this is the part where you get the breadboard out: the sensor
wired to those two holes, the LEDs to those four with resistors. Anything you
add is written into your own `board.repl`, so the board your code runs on is
the board you built. The exercise cannot run until both are on it.

<!-- section: divergences -->
## The simulator is not the board

<!-- generated: divergences -->
<!-- This block is generated from divergences.json. Do not edit it by hand; run python tools/gen_exercise_pages.py -->

**These can let wrong code look right.** The simulator is more permissive than the board here, so it will not tell you:

- **open-drain-ignored** — The GPIO model ignores the output type register entirely. Writing OTYPER to select open drain produces 'Unhandled write to offset 0x4 ... Tags: OT8 (0x1), OT9 (0x1)' and changes nothing. An I2C transfer succeeds whether or not the bus pins were configured as open drain
  On real hardware: I2C is a wired-AND bus. Both SCL and SDA must be open drain with pull-ups, because devices signal by pulling the line low and release it to let it float high. Push-pull outputs contend and the bus does not work
- **pin-configuration-not-enforced** — A bus controller never consults the GPIO registers. The I2C model reads no port mode, no alternate function and no clock-enable bit, so a transfer succeeds even when the pins it supposedly uses were never configured at all. Verified 2026-09-25: firmware with every GPIOB write removed still read the Si7021 correctly
  On real hardware: A peripheral reaches a pin only through that pin. The port's clock must be enabled, the pin put into alternate-function mode, and the correct alternate function selected. Miss any of them and nothing reaches the bus
- **sensor-value-quantisation** — The SI70xx model stores temperature and humidity through a fixed-point conversion, so a value read back differs slightly from the value set. Setting 25.00 C and reading it from firmware produced 24.99 C
  On real hardware: A real Si7021 also quantises, but to its own resolution and with its own error, which is not the same rounding the model performs
- **superset-peripherals** — The generic STM32F4 platform declares peripherals the F401RE does not carry: an Ethernet MAC, CAN1 and CAN2, GPIO ports F through K, UART4 and UART5, an external memory controller, and TIM6, TIM7, TIM8, TIM12, TIM13 and TIM14. Overriding cannot remove them, so they remain usable
  On real hardware: An STM32F401RE has GPIO ports A to E and H, three USARTs, no CAN, no Ethernet, no external memory controller, and timers TIM1 to TIM5 and TIM9 to TIM11

<!-- /generated -->

<!-- section: how-it-is-judged -->
## How it is judged

How the behaviour is observed. What the program has to do is stated once,
above, under **Functional specification**.

You choose the thresholds, so no particular pattern of lit LEDs is the correct
one. The check judges the shape instead: as the sensor warms, the number of
lit LEDs must never go down, and somewhere across the range it must go up.
That is what makes it a bar, and it is checkable without anybody being told
where to put their thresholds.

The temperatures are not presented in rising order, and one of them comes
round a second time at the end — your bar has to return to what it showed the
first time. A program that lights more LEDs the longer it runs would draw a
perfect rising bar on a sweep that only ever goes up; it cannot follow one
that goes down as well, and it cannot go back.

The I2C pins are judged too: the GPIOB clock, PB8 and PB9 in
alternate-function mode, and the right alternate function selected. Open drain
is not judged, because the simulator refuses the write and there is nothing to
read back — and it is still required on real hardware.

Run it yourself inside the container, once you have built:

```
python3 exercises/04-read-the-sensor/check.py \
  --elf exercises/04-read-the-sensor/firmware.elf
```

It answers `0` if your program did what the exercise asks, `1` if it did not,
and `2` if it could not tell. Two is not a failure — it means the check never
got far enough to have an opinion, usually because there is no build yet.

<!-- section: building-and-running -->
## Building and running

Choose this exercise in the board view and press **Build and run**.
[`../README.md`](../README.md) has the detail.
