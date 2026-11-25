/* Reference solution B for exercise 4: a level, and a table of LEDs.
 *
 * NOT FOR LEARNERS. See solutions/README.md and ADR-0027.
 *
 * Same sensor, same bus, different shape. Instead of four comparisons it
 * works out how many LEDs should be lit -- one per ten degrees from five --
 * and lights that many from a table. A check that expected particular
 * thresholds, or that read the LEDs in a fixed order, would pass solution A
 * and fail this one.
 *
 * The bus is read into a buffer by a small helper that takes the number of
 * bytes, rather than by a routine written around exactly two. Both are
 * reasonable; neither should be the one a check insists on.
 */

#include "stm32f401xe.h"

#define SI7021_ADDRESS      0x40
#define SI7021_MEASURE_TEMP 0xE3

#define TIMEOUT 200000U
#define BETWEEN_READINGS 90000U

/* The four LEDs the exercise asks for, coolest first. */
static GPIO_TypeDef *const PORT[4] = { GPIOA, GPIOB, GPIOB, GPIOB };
static const uint32_t PIN[4] = { 10U, 3U, 5U, 4U };

static void wait(volatile uint32_t count)
{
    while (count--) { }
}

static void outputs(void)
{
    RCC->AHB1ENR |= RCC_AHB1ENR_GPIOAEN | RCC_AHB1ENR_GPIOBEN;
    for (uint32_t i = 0; i < 4; i++) {
        PORT[i]->MODER &= ~(3U << (PIN[i] * 2));
        PORT[i]->MODER |= (1U << (PIN[i] * 2));
    }
}

static void bus(void)
{
    RCC->AHB1ENR |= RCC_AHB1ENR_GPIOBEN;
    RCC->APB1ENR |= RCC_APB1ENR_I2C1EN;

    GPIOB->MODER &= ~((3U << (8 * 2)) | (3U << (9 * 2)));
    GPIOB->MODER |= (2U << (8 * 2)) | (2U << (9 * 2));
    GPIOB->OTYPER |= (1U << 8) | (1U << 9);     /* open drain */
    GPIOB->AFR[1] &= ~((0xFU << 0) | (0xFU << 4));
    GPIOB->AFR[1] |= (4U << 0) | (4U << 4);     /* AF4 = I2C1 */

    I2C1->CR1 = 0;
    I2C1->CR2 = 42;                             /* APB1 = 42 MHz */
    I2C1->CCR = 210;                            /* 100 kHz */
    I2C1->TRISE = 43;
    I2C1->CR1 |= I2C_CR1_PE;
}

static int wait_for(uint32_t flag)
{
    volatile uint32_t t;
    for (t = 0; !(I2C1->SR1 & flag); t++)
        if (t > TIMEOUT) return -1;
    return 0;
}

/* Write one command byte, then read `count` bytes back. */
static int transfer(uint8_t command, uint8_t *into, uint32_t count)
{
    if (I2C1->CR1 |= I2C_CR1_START, wait_for(I2C_SR1_SB) < 0) return -1;
    I2C1->DR = (SI7021_ADDRESS << 1);
    if (wait_for(I2C_SR1_ADDR) < 0) return -2;
    (void) I2C1->SR2;

    if (wait_for(I2C_SR1_TXE) < 0) return -3;
    I2C1->DR = command;
    if (wait_for(I2C_SR1_BTF) < 0) return -4;

    I2C1->CR1 |= I2C_CR1_START;
    if (wait_for(I2C_SR1_SB) < 0) return -5;
    I2C1->DR = (SI7021_ADDRESS << 1) | 1U;
    if (wait_for(I2C_SR1_ADDR) < 0) return -6;

    if (count > 1) I2C1->CR1 |= I2C_CR1_ACK;
    (void) I2C1->SR2;

    for (uint32_t i = 0; i < count; i++) {
        if (i + 1 == count) {
            I2C1->CR1 &= ~I2C_CR1_ACK;
            I2C1->CR1 |= I2C_CR1_STOP;
        }
        if (wait_for(I2C_SR1_RXNE) < 0) return -7;
        into[i] = (uint8_t) I2C1->DR;
    }
    return 0;
}

/* How many LEDs this temperature deserves: one per ten degrees from five. */
static uint32_t level_for(int32_t centi)
{
    int32_t steps = (centi - 500) / 1000;
    if (steps < 0) return 0;
    if (steps > 3) return 4;
    return (uint32_t) steps + 1;
}

static void light(uint32_t level)
{
    for (uint32_t i = 0; i < 4; i++) {
        if (i < level) {
            PORT[i]->ODR |= (1U << PIN[i]);
        } else {
            PORT[i]->ODR &= ~(1U << PIN[i]);
        }
    }
}

int main(void)
{
    uint8_t reading[2];

    outputs();
    bus();

    while (1) {
        if (transfer(SI7021_MEASURE_TEMP, reading, 2) == 0) {
            uint16_t raw = (uint16_t) ((reading[0] << 8) | reading[1]);
            int32_t centi =
                (int32_t) ((17572L * (int32_t) raw) / 65536L) - 4685;
            light(level_for(centi));
        }
        wait(BETWEEN_READINGS);
    }
}
