/* Exercise 3 - change the blink interval with the user button.
 *
 * B1, the blue button on the board, is connected to PC13.
 *
 * Start from your exercise 2 code. When the button is pressed, the LED should
 * blink at a different rate. How you define that is up to you: two rates that
 * alternate, or a cycle through three, or fast while held.
 *
 * What the exercise asks for, which registers it asks you to find, and the
 * two ways of noticing the button are on this exercise's page: README.md, or
 * README.ja.md. Read that first. The register names are given there; the
 * numbers are yours to find, because finding them is the exercise.
 *
 * ---------------------------------------------------------------------------
 * THE SIMULATOR WILL NOT CHECK YOUR PIN SETUP, ON EITHER PIN.
 *
 * Renode drives the LED from the output data register without consulting
 * the clock-enable bit or the mode register, and it reports the button
 * without either. So both halves of your pin configuration -- the output on
 * PA5 and the input on PC13 -- can be wrong or absent, and this exercise
 * will still behave correctly here and not at all on a real board.
 *
 * This exercise's check does not look at them either. Exercise 1's does;
 * this one judges the rate change and the timer. So on both pins, here,
 * nothing is looking.
 *
 * See 'pin-configuration-not-enforced' in DIVERGENCES.md.
 * ---------------------------------------------------------------------------
 */

#include "stm32f401xe.h"

static volatile uint32_t ticks = 0;

void TIM2_IRQHandler(void)
{
    /* Clear the flag, toggle the LED -- as in exercise 2. */

    ticks++;
}

int main(void)
{
    /* 1. Everything from exercise 2: GPIOA clock, PA5 output, TIM2 running
     *    and interrupting once a second. */

    /* 2. Turn on the clock for GPIO port C. */

    /* 3. Make PC13 an input. */

    while (1) {
        /* 4. Read the button. Remember that pressed means the pin reads low.
         *    If you poll, put a short delay between reads -- the page says
         *    why, and it is not about being tidy. */

        /* 5. When it is pressed, change the timer's reload value so the LED
         *    blinks at a different rate. */
    }
}
