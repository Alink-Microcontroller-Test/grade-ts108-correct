/* Setup self-test.
 *
 * This is not an exercise. Its only job is to prove that a learner's compiler
 * and simulator work together on this board, so that a real problem later is
 * known to be in their code rather than in their installation.
 *
 * It exercises one thing per line of output: the serial port, the user LED on
 * PA5, the user button on PC13, and the Si7021 on I2C1. The check script reads
 * those lines and reports whether each worked.
 *
 * Raw register access on purpose. The self-test must not depend on headers
 * that an exercise might later change; course material uses CMSIS.
 */

#include <stdint.h>

#define REG(a) (*(volatile uint32_t *)(a))

#define RCC_AHB1ENR   REG(0x40023830)
#define RCC_APB1ENR   REG(0x40023840)

#define GPIOA_MODER   REG(0x40020000)
#define GPIOA_ODR     REG(0x40020014)
#define GPIOA_AFRL    REG(0x40020020)

#define GPIOB_MODER   REG(0x40020400)
#define GPIOB_OTYPER  REG(0x40020404)
#define GPIOB_AFRH    REG(0x40020424)

#define GPIOC_MODER   REG(0x40020800)
#define GPIOC_IDR     REG(0x40020810)

#define USART2_SR     REG(0x40004400)
#define USART2_DR     REG(0x40004404)
#define USART2_BRR    REG(0x40004408)
#define USART2_CR1    REG(0x4000440C)

#define I2C1_CR1      REG(0x40005400)
#define I2C1_CR2      REG(0x40005404)
#define I2C1_DR       REG(0x40005410)
#define I2C1_SR1      REG(0x40005414)
#define I2C1_SR2      REG(0x40005418)
#define I2C1_CCR      REG(0x4000541C)
#define I2C1_TRISE    REG(0x40005420)

#define SI7021_ADDR   0x40
#define CMD_MEASURE_T 0xE3

#define TIMEOUT       100000

static void uart_putc(char c)
{
    while (!(USART2_SR & (1 << 7))) { }
    USART2_DR = c;
}

static void uart_puts(const char *s)
{
    while (*s)
        uart_putc(*s++);
}

static void uart_putdec(int v)
{
    char buf[12];
    int i = 0;

    if (v < 0) {
        uart_putc('-');
        v = -v;
    }
    do {
        buf[i++] = '0' + (v % 10);
        v /= 10;
    } while (v);
    while (i)
        uart_putc(buf[--i]);
}

static void uart_init(void)
{
    RCC_AHB1ENR |= (1 << 0);
    RCC_APB1ENR |= (1 << 17);

    GPIOA_MODER &= ~((3u << 4) | (3u << 6));
    GPIOA_MODER |=  ((2u << 4) | (2u << 6));
    GPIOA_AFRL  &= ~((0xFu << 8) | (0xFu << 12));
    GPIOA_AFRL  |=  ((7u << 8) | (7u << 12));

    USART2_BRR = 0x16D;
    USART2_CR1 = (1 << 13) | (1 << 3);
}

static void i2c_init(void)
{
    RCC_AHB1ENR |= (1 << 1);
    RCC_APB1ENR |= (1 << 21);

    GPIOB_MODER  &= ~((3u << 16) | (3u << 18));
    GPIOB_MODER  |=  ((2u << 16) | (2u << 18));
    /* Open drain. The simulator ignores this; real hardware needs it. See the
     * 'open-drain-ignored' row of divergences.json. */
    GPIOB_OTYPER |=  ((1u << 8) | (1u << 9));
    GPIOB_AFRH   &= ~((0xFu << 0) | (0xFu << 4));
    GPIOB_AFRH   |=  ((4u << 0) | (4u << 4));

    I2C1_CR1   = 0;
    I2C1_CR2   = 42;
    I2C1_CCR   = 210;
    I2C1_TRISE = 43;
    I2C1_CR1  |= (1 << 0);
}

/* Returns 0 on success, or a negative step number identifying where it hung. */
static int si7021_read_raw(uint16_t *out)
{
    volatile uint32_t t;

    I2C1_CR1 |= (1 << 8);
    for (t = 0; !(I2C1_SR1 & (1 << 0)); t++)
        if (t > TIMEOUT) return -1;

    I2C1_DR = (SI7021_ADDR << 1);
    for (t = 0; !(I2C1_SR1 & (1 << 1)); t++)
        if (t > TIMEOUT) return -2;
    (void) I2C1_SR2;

    for (t = 0; !(I2C1_SR1 & (1 << 7)); t++)
        if (t > TIMEOUT) return -3;
    I2C1_DR = CMD_MEASURE_T;

    for (t = 0; !(I2C1_SR1 & (1 << 2)); t++)
        if (t > TIMEOUT) return -4;

    I2C1_CR1 |= (1 << 8);
    for (t = 0; !(I2C1_SR1 & (1 << 0)); t++)
        if (t > TIMEOUT) return -5;

    I2C1_DR = (SI7021_ADDR << 1) | 1;
    for (t = 0; !(I2C1_SR1 & (1 << 1)); t++)
        if (t > TIMEOUT) return -6;
    I2C1_CR1 |= (1 << 10);
    (void) I2C1_SR2;

    for (t = 0; !(I2C1_SR1 & (1 << 6)); t++)
        if (t > TIMEOUT) return -7;
    uint8_t msb = (uint8_t) I2C1_DR;

    I2C1_CR1 &= ~(1 << 10);
    I2C1_CR1 |= (1 << 9);

    for (t = 0; !(I2C1_SR1 & (1 << 6)); t++)
        if (t > TIMEOUT) return -8;
    uint8_t lsb = (uint8_t) I2C1_DR;

    *out = ((uint16_t) msb << 8) | lsb;
    return 0;
}

int main(void)
{
    uart_init();
    uart_puts("CHECK serial ok\r\n");

    RCC_AHB1ENR |= (1 << 0);
    GPIOA_MODER &= ~(3u << 10);
    GPIOA_MODER |=  (1u << 10);
    GPIOA_ODR   |=  (1u << 5);
    uart_puts("CHECK led on\r\n");

    RCC_AHB1ENR |= (1 << 2);
    GPIOC_MODER &= ~(3u << 26);
    uart_puts("CHECK button ");
    uart_putdec((GPIOC_IDR >> 13) & 1);
    uart_puts("\r\n");

    i2c_init();

    uint16_t raw = 0;
    int rc = si7021_read_raw(&raw);

    if (rc == -2) {
        /* Nothing acknowledged the address, which on this board is the normal
         * case rather than a fault: a real NUCLEO-F401RE carries no sensor,
         * boards/nucleo_f401re.repl does not declare one, and a learner adds
         * one from the palette in exercise 4. Only verify/verify.resc brings
         * a sensor, so only there does this step have a part to talk to.
         *
         * Said as "not fitted" rather than "failed" because it is a true
         * statement about the board and not a failure of the toolchain, which
         * is the only thing this self-test is for. It was reported as a
         * failure until 2026-11-11, which nobody met while learners started
         * the simulator by hand with their own firmware -- and which became
         * the first line every learner read once the container started the
         * board for them.
         *
         * The environment check matches "CHECK sensor 2[45][0-9][0-9]" for
         * success and never reads this branch, so the wording is ours to get
         * right. */
        uart_puts("CHECK sensor not fitted\r\n");
    } else if (rc != 0) {
        uart_puts("CHECK sensor failed at step ");
        uart_putdec(-rc);
        uart_puts("\r\n");
    } else {
        /* T = 175.72 * raw / 65536 - 46.85, in hundredths of a degree. */
        int centi = (int) (((uint32_t) raw * 17572) / 65536) - 4685;
        uart_puts("CHECK sensor ");
        uart_putdec(centi);
        uart_puts("\r\n");
    }

    uart_puts("CHECK done\r\n");

    for (;;) { }
}
