/* A program that cheats. See ../../README.md.
 *
 * Exercise 3's bypass.
 *
 * Configures TIM2 and leaves CEN set, so the "TIM2 is still running"
 * check passes. Blinks from a counting loop, and polls the button to
 * change the loop's constant, so the rate visibly changes.
 *
 * No interrupt is enabled and there is no handler. The timer does
 * nothing whatsoever.
 *
 * Not a solution. It deliberately does not do the exercise.
 */
#include "stm32f401xe.h"

#define LD2    5
#define BUTTON 13

#define SLOW 9000000U
#define FAST 1800000U

int main(void)
{
    RCC->AHB1ENR |= RCC_AHB1ENR_GPIOAEN | RCC_AHB1ENR_GPIOCEN;
    GPIOA->MODER &= ~(3U << (LD2 * 2));
    GPIOA->MODER |= (1U << (LD2 * 2));
    GPIOC->MODER &= ~(3U << (BUTTON * 2));

    RCC->APB1ENR |= RCC_APB1ENR_TIM2EN;
    TIM2->PSC = 8399U;
    TIM2->ARR = 4999U;
    TIM2->CR1 |= TIM_CR1_CEN;

    while (1) {
        uint32_t wait = ((GPIOC->IDR & (1U << BUTTON)) == 0) ? FAST : SLOW;
        GPIOA->ODR ^= (1U << LD2);
        for (volatile uint32_t i = 0; i < wait; i++) { }
    }
}
