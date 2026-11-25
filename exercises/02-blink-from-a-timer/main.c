/* Exercise 2 - blink LD2 from a timer interrupt.
 *
 * Exercise 1 counted in a loop. That works, but the processor can do nothing
 * else while it counts, and the interval changes if you change the code. A
 * timer counts on its own, in hardware, and interrupts you when it is done.
 *
 * Use TIM2. Blink at one second on, one second off. The timer's input is
 * 84,000,000 ticks per second.
 *
 * What the exercise asks for, and which registers it asks you to find, are on
 * this exercise's page: README.md, or README.ja.md. Read that first. The
 * register names are given there; the numbers are yours to find, because
 * finding them is the exercise.
 *
 * The handler is already named for you below. You do not register it
 * anywhere: the name is what matters, because it matches an entry in the
 * vector table in lib/startup.c.
 *
 * ---------------------------------------------------------------------------
 * THE SIMULATOR WILL NOT CHECK YOUR PIN SETUP.
 *
 * As in exercise 1: Renode drives the LED from the output data register
 * alone, without looking at the clock-enable bit or the mode register. The
 * GPIO half of this exercise can be wrong, or missing, and the LED will
 * still blink here.
 *
 * The timer half is checked, because the blinking depends on it. The pin
 * setup is not -- exercise 1's check reads those two registers back and this
 * one does not, so here the simulator is the only thing looking and it is not
 * looking. See 'pin-configuration-not-enforced' in DIVERGENCES.md.
 * ---------------------------------------------------------------------------
 */

#include "stm32f401xe.h"

/* Shared between the interrupt handler and main. volatile, because the
 * compiler cannot see that an interrupt changes it and would otherwise be
 * entitled to assume it never does. */
static volatile uint32_t ticks = 0;

void TIM2_IRQHandler(void)
{
    /* 1. Clear the flag that caused this interrupt. Do this first. */

    /* 2. Toggle the LED. */

    ticks++;
}

int main(void)
{
    /* 3. Turn on the clock for GPIO port A and make PA5 an output,
     *    as you did in exercise 1. */

    /* 4. Turn on the clock for TIM2. */

    /* 5. Set the prescaler and the reload value for one second. */

    /* 6. Let the timer raise an interrupt, and let the processor accept it. */

    /* 7. Start the timer counting. */

    while (1) {
        /* Nothing to do here. That is the point: the timer does the waiting,
         * and on a real product this is where the processor would sleep. */
    }
}
