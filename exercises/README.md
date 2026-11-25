# The exercises

Four exercises, in order. Each one builds on the last, so do them in order even
if a later one looks more interesting.

**Each exercise has its own page**, in its own folder, saying which manuals it
needs, what the simulator gets wrong there, and how it is judged. Start with
that, then the task itself, which is at the top of that exercise's `main.c`.

This page is how to build and run them. **How the course itself works** —
being graded, the daily allowance, Releases, what to do when no reply arrives
— is in [`../COURSE.md`](../COURSE.md).

> This document has a Japanese version: [`README.ja.md`](README.ja.md).

## Before you start

Your machine needs to be set up: see [`../SETUP.md`](../SETUP.md). Check it
with

**Windows**

```
powershell -ExecutionPolicy Bypass -File tools\check-environment.ps1
```

**macOS and Linux**

```
./tools/check-environment.sh
```

and do not go further until it says `Ready`.

## Build and run

Choose the exercise in **Build and run an exercise** at the top of the board
view, and press the button.

It compiles your code with the same build the course uses to mark it — the
same script, not a copy of it — and loads the result onto the board. There is
nothing to type and no file to move.

The scaffolding compiles as it stands, before you have written anything — it
simply does nothing. That is deliberate: it means a compile error is something
you just introduced, not something you inherited.

If it does not compile, the page shows the compiler's own words. Read the line
above them first: it says whether the problem is in your code or in the setup,
and those two need opposite responses.

Only one build runs at a time. Press while one is still going and the page
says so rather than queueing it — a build takes under a second, so press
again.

The board view is at **http://localhost:8000**. It is in Japanese; add
`?lang=en` for English.

You can press the button there and read whatever your program prints to the
serial port. You can also add parts the board does not have — more LEDs, a
switch, a sensor — from the palette on the right. Anything you add is drawn at
the pin you wired it to and written into your own `board.repl`, so the board
your code runs on is the board you built. The fourth exercise needs both a
sensor and four extra LEDs, and neither is there until you add them.

**Running what GitHub built.** Beside that button is **Run the build GitHub
made**. It fetches the firmware your most recent push compiled on GitHub and
loads that instead. Reach for it when a result does not add up and you want to
run the exact binary the machine built, rather than one you built beside it.

It says which commit that build came from, and says plainly when it is not the
code you currently have — GitHub builds what you pushed, and your working copy
is almost always ahead of that.

Those builds are kept for seven days. If there is none, push again and there
will be.

If your clone has no stored GitHub credential the control is unavailable and
says why. Download the build yourself and drop it on the page instead; it
loads the same way.

A sensor reading you set is kept when you rebuild, and when you load a build
from anywhere else. Loading firmware resets every part on the board, so without
that the fourth exercise would lose its reading every time.

**If you would rather type the commands**, they still work inside the
container, and [`NATIVE-SETUP.md`](../NATIVE-SETUP.md) is where they are
written down — it is the route for a machine that cannot run a container at
all, and it uses them throughout.

## The four

| | |
| --- | --- |
| [`01-blink-with-a-delay`](01-blink-with-a-delay/) | Turn LD2 on and off, counting in a loop |
| [`02-blink-from-a-timer`](02-blink-from-a-timer/) | Do the same with a timer interrupt, so the processor is not tied up counting |
| [`03-change-the-interval`](03-change-the-interval/) | Change the blink rate with the user button |
| [`04-read-the-sensor`](04-read-the-sensor/) | Read a temperature sensor over I2C and show it across LEDs. The sensor and the LEDs are both parts you add |

## Your work goes in main.c

Only `main.c` is taken for grading. A header or a second `.c` file you add
beside it is **not** sent, and the build on the grading side will not find
it.

This one bites quietly, because it works on your own machine: the compiler
looks in the same directory, finds your header, and builds. The grading
build has only `main.c`, so it stops at your `#include` and the error reads
as though you had mistyped the name. If it happens, the reply says which
file was left out.

Helper functions are fine — write them in `main.c`, above the function that
uses them.

## What you are given, and what you are not

The scaffolding gives you the structure, the build, the startup code, and the
register **names** through the CMSIS header. Type `GPIOA->` and your editor
lists what exists.

It does not give you the **values**. Which bit enables a clock, which mode
means output, what prescaler makes one second — those come from the reference
manual, and working them out is the exercise. Being handed them would leave
you able to run the code and unable to write the next one.

The documents you need. Each exercise's own page names which of these it
needs and says what to click to reach it, so you do not have to work that out
from here.

<!-- generated: manuals -->
<!-- This block is generated from references.json. Do not edit it by hand; run python tools/gen_exercise_pages.py -->

- **RM0368** — STM32F401xB/C and STM32F401xD/E reference manual
  The registers, bit by bit. [STM32F401 documentation](https://www.st.com/en/microcontrollers-microprocessors/stm32f401/documentation.html)
- **DS10086** — STM32F401xD/xE datasheet
  Pins, and which peripheral each one can be switched to. [STM32F401 documentation](https://www.st.com/en/microcontrollers-microprocessors/stm32f401/documentation.html)
- **UM1724** — STM32 Nucleo-64 boards (MB1136) user manual
  Which pin is which on the board's headers. [STM32 Nucleo boards documentation](https://www.st.com/en/evaluation-tools/stm32-nucleo-boards/documentation.html)

<!-- /generated -->

## The simulator is not the board

Some things work here that would fail on real hardware, and the simulator will
not warn you. They are listed in [`../DIVERGENCES.md`](../DIVERGENCES.md), and
the ones that affect exercise 4 are repeated at the top of its `main.c`.

One more is worth knowing before you go exploring beyond these four exercises.
The simulator is built on a generic STM32F4 description, and it offers
**peripherals an F401RE does not have** — an Ethernet controller, two CAN
controllers, GPIO ports F through K, UART4 and UART5, and timers TIM6, TIM7,
TIM8 and TIM12 through TIM14. Code using any of them runs here perfectly and
could never run on the real chip. Check the datasheet (DS10086) before using a
peripheral these exercises did not introduce you to. That is the
`superset-peripherals` row of the divergence list.

Read that page before you trust anything you have written to work on a real
NUCLEO-F401RE.
