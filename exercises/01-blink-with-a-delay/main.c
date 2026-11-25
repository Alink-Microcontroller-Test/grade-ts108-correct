/* Exercise 1 - blink LD2 using a delay in software.
 *
 * LD2, the green LED on the board, is connected to PA5.
 *
 * What the exercise asks for, and which registers it asks you to find, are on
 * this exercise's page: README.md, or README.ja.md. Read that first. The
 * register names are given there; the numbers are yours to find, because
 * finding them is the exercise.
 *
 * ---------------------------------------------------------------------------
 * THE SIMULATOR WILL NOT CHECK YOUR PIN SETUP. THE CHECK DOES.
 *
 * Renode lights this LED from the output data register alone. It does not
 * look at the clock-enable bit, and it does not look at the mode register.
 * So a program that writes only to GPIOA->ODR blinks perfectly here, and
 * does nothing whatever on a real board -- the port has no clock, and the
 * pin is still an input.
 *
 * Measured, not assumed: firmware with both of those steps deleted blinks
 * here exactly like a correct program. Nothing about the pin gives it away.
 *
 * Those two steps are the exercise, so the check reads both registers back
 * after your program has run and fails if they were never set. Setting the
 * pin up inside your loop is fine -- it is read at the end, not the start.
 * The blinking is not evidence that your pins are right; the check is.
 * See 'pin-configuration-not-enforced' in DIVERGENCES.md.
 * ---------------------------------------------------------------------------
 */

#include "stm32f401xe.h"

/* Roughly this many loop iterations per second, measured in the simulator.
 * It is approximate, and this exercise's page says why. */
#define ABOUT_ONE_SECOND 18000000

static void wait(volatile uint32_t count)
{
    /* volatile, so the compiler does not notice this loop does nothing and
     * delete it. Removing that keyword is a good way to see your LED stop
     * blinking for reasons that look impossible. */
    while (count--) { }
}

int main(void)
{
    /* 1. Turn on the clock for GPIO port A. */
    /* RCC->AHB1ENR |= ...; */

    /* 2. Make PA5 an output. */
    /* GPIOA->MODER ...; */

    while (1) {
        /* 3. Turn the LED on. */

        wait(ABOUT_ONE_SECOND);

        /* 4. Turn the LED off. */

        wait(ABOUT_ONE_SECOND);
    }
}
