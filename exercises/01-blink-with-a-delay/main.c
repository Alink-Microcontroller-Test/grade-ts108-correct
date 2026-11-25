/* Reference solution A for exercise 1: a software delay loop.
 *
 * NOT FOR LEARNERS. This file exists so our own CI can ask this exercise's
 * check a question it is otherwise never asked: does it accept a working
 * program, and does it give the same answer every time? See
 * solutions/README.md and ADR-0027.
 *
 * The timing-loose half of the pair. A delay counted in loop iterations is
 * never accurate, and the period drifts with the compiler, the optimisation
 * level and -- in the simulator -- with how fast the host happens to be.
 * The check for this exercise accepts any period, which is the whole reason
 * this approach is a legitimate answer to it.
 *
 * The pin setup is the real thing: the clock is enabled and the mode
 * register is written, both of which Renode ignores and a board does not.
 */

#include "stm32f401xe.h"

#define LD2 5

/* A quarter of a second, roughly, at the simulator's flat 100 MIPS. Shorter
 * than the scaffolding's suggestion on purpose: the check watches for six
 * seconds and wants to see the LED change at least three times, and a
 * one-second period leaves that uncomfortably close to the edge.
 */
#define ABOUT_A_QUARTER_SECOND 4500000

static void wait(volatile uint32_t count)
{
    while (count--) { }
}

int main(void)
{
    RCC->AHB1ENR |= RCC_AHB1ENR_GPIOAEN;

    GPIOA->MODER &= ~(3U << (LD2 * 2));
    GPIOA->MODER |= (1U << (LD2 * 2));          /* 01: output */

    while (1) {
        GPIOA->ODR |= (1U << LD2);
        wait(ABOUT_A_QUARTER_SECOND);
        GPIOA->ODR &= ~(1U << LD2);
        wait(ABOUT_A_QUARTER_SECOND);
    }
}
