/* A program that cheats. See ../../README.md.
 *
 * Exercise 1's bypass, measured 2026-09-30.
 *
 * Writes only to GPIOA->ODR. No clock enable, no mode register: both
 * steps of exercise 1 are simply absent. On a real NUCLEO-F401RE this
 * does nothing whatsoever -- the port is not even clocked.
 *
 * Not a solution. It deliberately fails the exercise.
 */
#include "stm32f401xe.h"

#define LD2 5
#define ABOUT_ONE_SECOND 18000000U

int main(void)
{
    while (1) {
        GPIOA->ODR ^= (1U << LD2);
        for (volatile uint32_t i = 0; i < ABOUT_ONE_SECOND; i++) { }
    }
}
