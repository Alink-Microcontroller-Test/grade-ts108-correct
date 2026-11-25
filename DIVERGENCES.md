# What the simulator gets wrong

Every known way the simulated board differs from a real ST
NUCLEO-F401RE.

**This file is generated.** The source is
[`divergences.json`](divergences.json); edit that and run
`python tools/gen_divergence_table.py`. The verification sweep fails
if the two disagree.

> This document has a Japanese version: [`DIVERGENCES.ja.md`](DIVERGENCES.ja.md).

13 divergences: 7 permanent, 0 outstanding, 6 corrected.

## Differences that let wrong code look right

These are the dangerous ones. In each case the simulator is more
permissive than the hardware, so a mistake produces working
simulation and a failure on a real board — and the learner is told
nothing at the point they make it. The exercise material must warn
about each of these where it bites.

### open-drain-ignored

**What Renode does** The GPIO model ignores the output type register entirely. Writing OTYPER to select open drain produces 'Unhandled write to offset 0x4 ... Tags: OT8 (0x1), OT9 (0x1)' and changes nothing. An I2C transfer succeeds whether or not the bus pins were configured as open drain

**What the board does** I2C is a wired-AND bus. Both SCL and SDA must be open drain with pull-ups, because devices signal by pulling the line low and release it to let it float high. Push-pull outputs contend and the bus does not work

**Status** permanent

**Warned about in** exercises/04-read-the-sensor/main.c

**Source** Observed in the feasibility spike, 2026-09-25, on Renode 1.16.1. Hardware behaviour: RM0368 section 8.3 'I/O port control registers'; the I2C specification's wired-AND requirement

### pin-configuration-not-enforced

**What Renode does** A bus controller never consults the GPIO registers. The I2C model reads no port mode, no alternate function and no clock-enable bit, so a transfer succeeds even when the pins it supposedly uses were never configured at all. Verified 2026-09-25: firmware with every GPIOB write removed still read the Si7021 correctly

**What the board does** A peripheral reaches a pin only through that pin. The port's clock must be enabled, the pin put into alternate-function mode, and the correct alternate function selected. Miss any of them and nothing reaches the bus

**Status** permanent

**Warned about in** exercises/01-blink-with-a-delay/main.c, exercises/02-blink-from-a-timer/main.c, exercises/03-change-the-interval/main.c, exercises/04-read-the-sensor/main.c

**Source** Observed in the feasibility work, 2026-09-25, on Renode 1.16.1. Renode's STM32F4_I2C model contains no reference to GPIO, pins or alternate functions. Hardware behaviour: RM0368 section 8 'General-purpose I/Os' and the alternate function table in DS10086

### sensor-value-quantisation

**What Renode does** The SI70xx model stores temperature and humidity through a fixed-point conversion, so a value read back differs slightly from the value set. Setting 25.00 C and reading it from firmware produced 24.99 C

**What the board does** A real Si7021 also quantises, but to its own resolution and with its own error, which is not the same rounding the model performs

**Status** permanent

**Warned about in** exercises/04-read-the-sensor/main.c

**Source** Observed in the feasibility spike, 2026-09-25: sensor set to 25, firmware printed 'RAW=26796 TEMP_C_X100=2499'. Model source: renode-infrastructure SI70xx.cs, which stores (value + 46.85) * 65536 / 175.72

### superset-peripherals

**What Renode does** The generic STM32F4 platform declares peripherals the F401RE does not carry: an Ethernet MAC, CAN1 and CAN2, GPIO ports F through K, UART4 and UART5, an external memory controller, and TIM6, TIM7, TIM8, TIM12, TIM13 and TIM14. Overriding cannot remove them, so they remain usable

**What the board does** An STM32F401RE has GPIO ports A to E and H, three USARTs, no CAN, no Ethernet, no external memory controller, and timers TIM1 to TIM5 and TIM9 to TIM11

**Status** permanent

**Warned about in** exercises/README.md, exercises/README.ja.md

**Source** platforms/cpus/stm32f4.repl peripheral declarations, read 2026-09-25. Hardware: STM32F401xD/xE datasheet DS10086, block diagram and pinout

## The rest

### cpu-speed-not-from-the-clock-tree

**What Renode does** The processor executes a flat 100 million instructions per second, declared as PerformanceInMips and unrelated to the 84 MHz this board describes. There is no pipeline, no flash wait state and no cache, so every instruction costs the same. A delay written as a counting loop therefore takes a length of time that does not follow from the clock configuration at all. Measured 2026-09-28: the loop advances about 18 million iterations per second of simulated time. The first exercise's ABOUT_ONE_SECOND is 18,000,000 and so does take about a second -- a constant chosen to match this simulator's fixed rate, not one derived from the clock configuration

**What the board does** Instruction timing follows the core clock, and the core clock follows the oscillator, the PLL and the bus prescalers the program sets up. It is also affected by flash wait states and by where the code sits in memory, so a counting loop is approximate on hardware too -- but it is approximate around a figure the clock determines

**Status** permanent

**Source** Measured 2026-09-28 on Renode 1.16.1: sysbus.cpu PerformanceInMips reports 0x64 (100). Sampling the LED pin while running the first exercise's reference solution gave a half-cycle of 0.111 s over 1 s of simulated time. Hardware behaviour: RM0368 section 6 and the flash latency table in section 3.4

### peripheral-reads-are-slow-to-simulate

**What Renode does** Reading a peripheral register costs far more simulated-machine effort than reading a variable, because it leaves the translated code and goes through the system bus. A loop that does nothing but read one pin therefore runs about a hundred times slower than the same loop without it. Measured 2026-09-28: polling the button in a tight main loop simulated one second of board time in 156 seconds of real time, against 1.4 seconds for the same program using an interrupt, and 5 seconds for the same polling loop with a short delay between reads

**What the board does** Reading a port register is a single load instruction, a few clock cycles, and no slower than reading a variable in RAM. A tight polling loop is wasteful of power on hardware but costs no time

**Status** permanent

**Source** Measured 2026-09-28 on Renode 1.16.1, sampling the LED pin while running three reference implementations of the third exercise: tight polling 156x slower than real time, polling with a delay 2.5x, EXTI 1.4x

### static-timer-clocks

**What Renode does** Peripheral clocks are not derived from the RCC and PLL registers. Each timer carries a frequency declared in the platform description, and programming the clock tree does not change how fast it counts

**What the board does** Timer clocks follow the clock tree. The rate depends on the oscillator, the PLL configuration and the bus prescalers the program sets up, and a mistake there changes every timing in the system

**Status** permanent

**Source** platforms/cpus/stm32f4.repl declares a literal frequency on each Timers.STM32_Timer. Hardware behaviour: RM0368 section 6 'Reset and clock control'

### button-polarity

**What Renode does** Miscellaneous.Button drives its pin high while pressed

**What the board does** B1 is active low. A pull-up holds PC13 high at rest, and the normally-open switch shorts it to ground when pressed

**Status** corrected

**Fixed by** boards/nucleo_f401re.repl sets invert: true on the board's button

**Source** UM1724 'STM32 Nucleo-64 boards', user button B1 on PC13. Verified 2026-09-25: firmware read 1 at rest, 0 while pressed

### declared-clock-rate

**What Renode does** The generic STM32F4 platform declares every timer at 10 MHz and SysTick at 72 MHz. The board description overrides the timers the F401RE has, and SysTick, to 84 MHz

**What the board does** In the standard configuration an STM32F401RE runs at 84 MHz, and its general-purpose timers receive 84 MHz

**Status** corrected

**Fixed by** boards/nucleo_f401re.repl declares 84000000 on TIM1-5 and TIM9-11 and on the NVIC's systickFrequency

**Source** Override verified 2026-09-25: sysbus.timer2 Frequency reports 0x501BD00. Hardware behaviour: RM0368 section 6.2, APB1 timer clock doubling

### missing-fpu

**What Renode does** The generic STM32F4 platform declares the core as cortex-m4, which has no floating-point unit

**What the board does** An STM32F401RE has a Cortex-M4 with a single-precision floating-point unit

**Status** corrected

**Fixed by** boards/nucleo_f401re.repl sets cpuType to cortex-m4f

**Source** STM32F401xD/xE datasheet DS10086. Verified 2026-09-25: sysbus.cpu Model reports cortex-m4f

### oversized-flash

**What Renode does** The generic STM32F4 platform declares 2 MB of flash

**What the board does** An STM32F401RE has 512 KB of flash

**Status** corrected

**Fixed by** boards/nucleo_f401re.repl sets flash size to 0x80000

**Source** STM32F401xD/xE datasheet DS10086. Verified 2026-09-25: sysbus.flash Size reports 0x80000

### oversized-sram

**What Renode does** The generic STM32F4 platform declares 256 KB of SRAM

**What the board does** An STM32F401RE has 96 KB of SRAM

**Status** corrected

**Fixed by** boards/nucleo_f401re.repl sets sram size to 0x18000

**Source** STM32F401xD/xE datasheet DS10086. Verified 2026-09-25: sysbus.sram Size reports 0x18000

### si7021-not-fitted

**What Renode does** Nothing sits on I2C1. A sensor is a part the learner adds from the board view's palette, which writes it into their own board.repl; until they do, a read of the bus finds nothing, exactly as on the board

**What the board does** A real NUCLEO-F401RE carries no sensor. To read one you wire it to the Arduino connector yourself, at D15 for SCL and D14 for SDA

**Status** corrected

**Fixed by** boards/nucleo_f401re.repl declares nothing on i2c1. The board view's palette offers SI7021 at 0x40, and adding it writes the declaration into the learner's own board.repl. The setup self-test brings its own sensor in verify/sensor.repl, because it runs before the learner has opened the board view.

**Source** UM1724, 'STM32 Nucleo-64 boards', lists the fitted components: two user LEDs, one user button, one reset button and the ST-LINK. No sensor. boards/nucleo_f401re.repl declared si7021: Sensors.SI70xx @ i2c1 0x40 until 2026-09-29 and no longer declares anything on the bus.
