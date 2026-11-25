/* Reference solution A for exercise 2: one second from a 10 kHz tick.
 *
 * NOT FOR LEARNERS. See solutions/README.md and ADR-0027.
 *
 * 84 MHz / 8400 = 10 kHz; 10,000 of those is one second. This is the
 * division most people reach first, and it is the one the scaffolding's
 * hints lead towards.
 *
 * This exercise's check requires TIM2 to be counting (CR1 CEN) and to be
 * asking for its update interrupt (DIER UIE), so unlike exercise 1 there is
 * no loose answer to pair this with. The other solution divides the same
 * second differently and drives the pin through a different register --
 * which is what the +/-0.35 s tolerance exists to allow, and what nothing
 * else tests.
 */

#include "stm32f401xe.h"

#define LD2 5

#define PRESCALER 8399U     /* 84 MHz / 8400 = 10 kHz */
#define RELOAD    9999U     /* 10,000 ticks = 1.000 s */

void TIM2_IRQHandler(void)
{
    /* First, and always. An unacknowledged update flag re-enters this
     * handler immediately and for ever, and the symptom is a board that
     * looks dead rather than one that looks stuck. */
    TIM2->SR &= ~TIM_SR_UIF;
    GPIOA->ODR ^= (1U << LD2);
}

int main(void)
{
    RCC->AHB1ENR |= RCC_AHB1ENR_GPIOAEN;
    GPIOA->MODER &= ~(3U << (LD2 * 2));
    GPIOA->MODER |= (1U << (LD2 * 2));

    RCC->APB1ENR |= RCC_APB1ENR_TIM2EN;
    TIM2->PSC = PRESCALER;
    TIM2->ARR = RELOAD;

    TIM2->EGR = TIM_EGR_UG;
    TIM2->SR &= ~TIM_SR_UIF;

    TIM2->DIER |= TIM_DIER_UIE;
    NVIC_EnableIRQ(TIM2_IRQn);
    TIM2->CR1 |= TIM_CR1_CEN;

    while (1) { }
}
