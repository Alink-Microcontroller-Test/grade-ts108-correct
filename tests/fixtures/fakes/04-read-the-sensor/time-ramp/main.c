/* A program that cheats. See ../../README.md.
 *
 * Exercise 4's bypass.
 *
 * Never touches the sensor. Lights one more LED every tenth of a second,
 * so on a sweep that only ever goes up, read once per point, the bar
 * rises exactly as the exercise asks.
 *
 * Before this change it satisfied all three checks: a LED lights, the
 * count never falls as the temperature rises, and the count responds.
 *
 * Not a solution. There is no I2C in it at all.
 */
#include "stm32f401xe.h"

#define ABOUT_A_TENTH 1800000U

int main(void)
{
    RCC->AHB1ENR |= RCC_AHB1ENR_GPIOAEN | RCC_AHB1ENR_GPIOBEN;
    GPIOA->MODER &= ~(3U << (10 * 2));
    GPIOA->MODER |= (1U << (10 * 2));
    GPIOB->MODER &= ~((3U << (3 * 2)) | (3U << (4 * 2)) | (3U << (5 * 2)));
    GPIOB->MODER |= (1U << (3 * 2)) | (1U << (4 * 2)) | (1U << (5 * 2));

    for (;;) {
        for (volatile uint32_t i = 0; i < ABOUT_A_TENTH; i++) { }
        GPIOA->ODR |= (1U << 10);
        for (volatile uint32_t i = 0; i < ABOUT_A_TENTH; i++) { }
        GPIOB->ODR |= (1U << 3);
        for (volatile uint32_t i = 0; i < ABOUT_A_TENTH; i++) { }
        GPIOB->ODR |= (1U << 4);
        for (volatile uint32_t i = 0; i < ABOUT_A_TENTH; i++) { }
        GPIOB->ODR |= (1U << 5);
        while (1) { }
    }
}
