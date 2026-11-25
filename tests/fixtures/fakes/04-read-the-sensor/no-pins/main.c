/* A program that cheats. See ../../README.md.
 *
 * Exercise 4's pin bypass: the 2026-09-25 experiment itself.
 *
 * Reference solution thresholds.c with every I2C PIN setup line
 * removed: no alternate-function mode on PB8/PB9, no AFRH, no
 * open drain. The sensor logic is untouched and correct.
 *
 * Renode's I2C model consults no GPIO register, so this reads the
 * Si7021 perfectly and shows the right bar. On a bench nothing
 * would reach the bus at all.
 *
 * Not a solution. Its pin setup is wrong on purpose.
 */
/* Reference solution A for exercise 4: four thresholds, one per LED.
 *
 * NOT FOR LEARNERS. See solutions/README.md and ADR-0027.
 *
 * Reads the Si7021 over I2C1 and lights more of the four added LEDs the
 * warmer it is: one above 10 C, two above 20, three above 30, four above 40.
 * The thresholds are ours -- the exercise fixes none, and its check is
 * written to accept any set, requiring only that the count never falls as
 * the temperature rises.
 *
 * The I2C sequence is the one verify/main.c uses, in CMSIS form. The pin
 * setup is done properly even though Renode's I2C model never reads a GPIO
 * register: on a board it is the difference between working and not.
 */

#include "stm32f401xe.h"

#define SI7021_ADDRESS      0x40
#define SI7021_MEASURE_TEMP 0xE3

#define TIMEOUT 200000U

/* A pause between readings. Without one, polling the bus flat out makes the
 * simulation roughly a hundred times slower than real time and the check
 * runs out of its budget -- see 'peripheral-reads-are-slow-to-simulate' in
 * DIVERGENCES.md. Short enough that a new temperature is picked up well
 * inside the tenth of a second the check allows.
 */
#define BETWEEN_READINGS 90000U

static void wait(volatile uint32_t count)
{
    while (count--) { }
}

static void pins_and_bus(void)
{
    RCC->AHB1ENR |= RCC_AHB1ENR_GPIOAEN | RCC_AHB1ENR_GPIOBEN;
    RCC->APB1ENR |= RCC_APB1ENR_I2C1EN;

    /* The LEDs: PA10, and PB3, PB4, PB5. */
    GPIOA->MODER &= ~(3U << (10 * 2));
    GPIOA->MODER |= (1U << (10 * 2));
    GPIOB->MODER &= ~((3U << (3 * 2)) | (3U << (4 * 2)) | (3U << (5 * 2)));
    GPIOB->MODER |= (1U << (3 * 2)) | (1U << (4 * 2)) | (1U << (5 * 2));

    /* PB8 and PB9 to alternate function 4, open drain: I2C1 SCL and SDA.
     * I2C is a bus two devices pull low and a resistor pulls high, so a
     * push-pull output fights the sensor. */

    /* APB1 runs at 42 MHz in the standard 84 MHz configuration. CCR 210 and
     * TRISE 43 give the 100 kHz standard mode the datasheet asks for. */
    I2C1->CR1 = 0;
    I2C1->CR2 = 42;
    I2C1->CCR = 210;
    I2C1->TRISE = 43;
    I2C1->CR1 |= I2C_CR1_PE;
}

/* 0 on success, or a negative number saying which wait gave up. */
static int read_raw(uint16_t *out)
{
    volatile uint32_t t;

    I2C1->CR1 |= I2C_CR1_START;
    for (t = 0; !(I2C1->SR1 & I2C_SR1_SB); t++)
        if (t > TIMEOUT) return -1;

    I2C1->DR = (SI7021_ADDRESS << 1);
    for (t = 0; !(I2C1->SR1 & I2C_SR1_ADDR); t++)
        if (t > TIMEOUT) return -2;
    (void) I2C1->SR2;                   /* reading SR2 clears ADDR */

    for (t = 0; !(I2C1->SR1 & I2C_SR1_TXE); t++)
        if (t > TIMEOUT) return -3;
    I2C1->DR = SI7021_MEASURE_TEMP;

    for (t = 0; !(I2C1->SR1 & I2C_SR1_BTF); t++)
        if (t > TIMEOUT) return -4;

    I2C1->CR1 |= I2C_CR1_START;         /* repeated start */
    for (t = 0; !(I2C1->SR1 & I2C_SR1_SB); t++)
        if (t > TIMEOUT) return -5;

    I2C1->DR = (SI7021_ADDRESS << 1) | 1U;
    for (t = 0; !(I2C1->SR1 & I2C_SR1_ADDR); t++)
        if (t > TIMEOUT) return -6;
    I2C1->CR1 |= I2C_CR1_ACK;           /* acknowledge the first byte */
    (void) I2C1->SR2;

    for (t = 0; !(I2C1->SR1 & I2C_SR1_RXNE); t++)
        if (t > TIMEOUT) return -7;
    uint8_t msb = (uint8_t) I2C1->DR;

    I2C1->CR1 &= ~I2C_CR1_ACK;          /* NACK the last one */
    I2C1->CR1 |= I2C_CR1_STOP;

    for (t = 0; !(I2C1->SR1 & I2C_SR1_RXNE); t++)
        if (t > TIMEOUT) return -8;
    uint8_t lsb = (uint8_t) I2C1->DR;

    *out = (uint16_t) ((msb << 8) | lsb);
    return 0;
}

static void show(int32_t centi)
{
    if (centi >= 1000) GPIOA->BSRR = (1U << 10);
    else GPIOA->BSRR = (1U << (10 + 16));

    if (centi >= 2000) GPIOB->BSRR = (1U << 3);
    else GPIOB->BSRR = (1U << (3 + 16));

    if (centi >= 3000) GPIOB->BSRR = (1U << 5);
    else GPIOB->BSRR = (1U << (5 + 16));

    if (centi >= 4000) GPIOB->BSRR = (1U << 4);
    else GPIOB->BSRR = (1U << (4 + 16));
}

int main(void)
{
    uint16_t raw;

    pins_and_bus();

    while (1) {
        if (read_raw(&raw) == 0) {
            /* Fixed point, in hundredths of a degree: the datasheet's
             * 175.72 * raw / 65536 - 46.85, scaled by 100 so no float is
             * needed. */
            int32_t centi = (int32_t) ((17572L * (int32_t) raw) / 65536L) - 4685;
            show(centi);
        }
        wait(BETWEEN_READINGS);
    }
}
