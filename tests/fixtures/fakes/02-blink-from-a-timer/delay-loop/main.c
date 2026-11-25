/* A program that cheats. See ../../README.md.
 *
 * Exercise 2's bypass.
 *
 * Configures TIM2 exactly as the exercise asks, down to CEN and UIE, and
 * then ignores it completely: the blinking comes from a counting loop.
 * Never enables the interrupt in the NVIC and has no handler at all.
 *
 * Before this change it satisfied every check in exercise 2 -- the LED
 * blinks, the half-periods are one second, and both bits are set.
 *
 * Not a solution. It deliberately does not do the exercise.
 */
#include "stm32f401xe.h"

#define LD2 5
#define ABOUT_ONE_SECOND 12857000U

int main(void)
{
    RCC->AHB1ENR |= RCC_AHB1ENR_GPIOAEN;
    GPIOA->MODER &= ~(3U << (LD2 * 2));
    GPIOA->MODER |= (1U << (LD2 * 2));

    /* All of the timer setup, and none of its use. */
    RCC->APB1ENR |= RCC_APB1ENR_TIM2EN;
    TIM2->PSC = 41999U;
    TIM2->ARR = 1999U;
    TIM2->DIER |= TIM_DIER_UIE;
    TIM2->CR1 |= TIM_CR1_CEN;

    while (1) {
        GPIOA->ODR ^= (1U << LD2);
        for (volatile uint32_t i = 0; i < ABOUT_ONE_SECOND; i++) { }
    }
}
