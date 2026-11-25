/* Reference solution B for exercise 3: the button changes the prescaler.
 *
 * NOT FOR LEARNERS. See solutions/README.md and ADR-0027.
 *
 * The reload value never moves. Released, the timer ticks at 10 kHz and the
 * LED changes every half second; held, it ticks at 50 kHz and changes every
 * tenth. Same observable behaviour as solution A by the other register, and
 * a check that reads only ARR to decide whether the rate changed would pass
 * A and fail this -- which is the defect this file is here to catch.
 *
 * It also reads the button through an interrupt rather than by polling, so
 * the main loop is empty. EXTI 13 fires on both edges, which is what makes
 * "while held" work from an event.
 */

#include "stm32f401xe.h"

#define LD2    5
#define BUTTON 13

#define SLOW_PRESCALER 8399U    /* 10 kHz; 5,000 ticks = 0.5 s */
#define FAST_PRESCALER 1679U    /* 50 kHz; 5,000 ticks = 0.1 s */
#define RELOAD         4999U

void TIM2_IRQHandler(void)
{
    TIM2->SR &= ~TIM_SR_UIF;
    GPIOA->ODR ^= (1U << LD2);
}

void EXTI15_10_IRQHandler(void)
{
    if (EXTI->PR & (1U << BUTTON)) {
        EXTI->PR = (1U << BUTTON);              /* write 1 to clear */

        /* Pressed is low. Read the pin rather than counting edges: an edge
         * that arrives while this handler runs would otherwise leave the
         * rate disagreeing with the button for ever. */
        if ((GPIOC->IDR & (1U << BUTTON)) == 0) {
            TIM2->PSC = FAST_PRESCALER;
        } else {
            TIM2->PSC = SLOW_PRESCALER;
        }
        /* The prescaler is buffered: it loads at the next update event, and
         * an update now is what makes the new rate start now. */
        TIM2->EGR = TIM_EGR_UG;
    }
}

int main(void)
{
    RCC->AHB1ENR |= RCC_AHB1ENR_GPIOAEN | RCC_AHB1ENR_GPIOCEN;
    RCC->APB2ENR |= RCC_APB2ENR_SYSCFGEN;       /* EXTI needs this */

    GPIOA->MODER &= ~(3U << (LD2 * 2));
    GPIOA->MODER |= (1U << (LD2 * 2));
    GPIOC->MODER &= ~(3U << (BUTTON * 2));

    /* Route EXTI line 13 to port C, and let it fire on press and release. */
    SYSCFG->EXTICR[3] &= ~(0xFU << 4);
    SYSCFG->EXTICR[3] |= (2U << 4);             /* 0010: port C */
    EXTI->IMR |= (1U << BUTTON);
    EXTI->FTSR |= (1U << BUTTON);
    EXTI->RTSR |= (1U << BUTTON);
    NVIC_EnableIRQ(EXTI15_10_IRQn);

    RCC->APB1ENR |= RCC_APB1ENR_TIM2EN;
    TIM2->PSC = SLOW_PRESCALER;
    TIM2->ARR = RELOAD;
    TIM2->EGR = TIM_EGR_UG;
    TIM2->SR &= ~TIM_SR_UIF;
    TIM2->DIER |= TIM_DIER_UIE;
    NVIC_EnableIRQ(TIM2_IRQn);
    TIM2->CR1 |= TIM_CR1_CEN;

    while (1) { }
}
