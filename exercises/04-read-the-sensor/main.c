/* Exercise 4 - read a temperature sensor over I2C and show it on LEDs.
 *
 * Read the temperature and show it across four LEDs, like a bar: colder
 * lights fewer, warmer lights more. You choose the thresholds, but put them
 * inside 0 to 45 degrees.
 *
 * This exercise needs two parts that are not on the board, and it cannot run
 * until you have added them in the board view. What the exercise asks for,
 * what to add, and which registers it asks you to find are on this exercise's
 * page: README.md, or README.ja.md. Read that first. The register names are
 * given there; the numbers are yours to find, because finding them is the
 * exercise.
 *
 * ---------------------------------------------------------------------------
 * THREE THINGS THE SIMULATOR WILL NOT TELL YOU
 *
 * 1. OPEN DRAIN IS NOT CHECKED HERE. IT IS WHAT MAKES THE BUS WORK.
 *
 *    To reach the bus on a real board, PB8 and PB9 need four things: the
 *    GPIOB clock enabled, the pins put into alternate-function mode, the
 *    right alternate function selected, and open-drain output type. Miss any
 *    one of them and the bus does not work.
 *
 *    The check judges the first three. It reads the clock bit, the mode bits
 *    and the alternate function number back off the bus after your program
 *    has run, so getting one of those wrong fails here.
 *
 *    It cannot judge the fourth. A write to OTYPER is refused by the
 *    simulator and logged as unhandled, so there is nothing to read back.
 *    Open drain is also the one people get wrong even when they remember the
 *    rest: I2C works by devices pulling a shared line low and releasing it to
 *    float high, which push-pull outputs cannot do.
 *
 *    And the bus itself still does not care about any of it. Renode's I2C
 *    model never looks at the GPIO registers: firmware with *every* GPIOB
 *    write deleted still read the sensor correctly. A transfer that succeeds
 *    is not evidence that your pins are right -- the check is.
 *
 *    See 'pin-configuration-not-enforced' and 'open-drain-ignored' in
 *    DIVERGENCES.md.
 *
 * 2. THE VALUE YOU READ WILL NOT EXACTLY MATCH THE VALUE THAT WAS SET.
 *
 *    Set the sensor to 25.00 C in the board view and your program reads
 *    24.99 C. The model stores the value through a fixed-point conversion and
 *    a little is lost each way. Never compare a sensor reading with == ;
 *    compare against a range. Real sensors behave the same way, for their own
 *    reasons. See 'sensor-value-quantisation' in DIVERGENCES.md.
 *
 * 3. THE BUS IS EMPTY UNTIL YOU PUT SOMETHING ON IT.
 *
 *    This one the simulator does tell you, and it is here so you know that
 *    is deliberate. If you skip the board view and run this, every read
 *    fails, because there is nothing at the sensor's address -- the same as
 *    running it on a bare board. The sensor used to be declared for you,
 *    which meant this exercise passed on a board nobody had built. It no
 *    longer is. See 'si7021-not-fitted' in DIVERGENCES.md.
 * ---------------------------------------------------------------------------
 */

#include "stm32f401xe.h"

#define SI7021_ADDRESS        0x40
#define SI7021_MEASURE_TEMP   0xE3

/* Where the four LEDs you added sit. D2 is PA10; the rest are on port B. */
/* D2 = PA10, D3 = PB3, D4 = PB5, D5 = PB4 */

static void i2c_setup(void)
{
    /* 1. Clocks for GPIO port B and for I2C1. */

    /* 2. PB8 and PB9 to alternate function, open drain.
     *    Open drain matters on hardware even though it does not here. */

    /* 3. Tell I2C1 its input clock, its speed and its rise time, then
     *    enable it. */
}

/* Returns the raw 16-bit reading, or 0 if the transfer did not complete. */
static uint16_t si7021_read_raw(void)
{
    /* 4. start, address+write, command, repeated start, address+read,
     *    two bytes, stop. */
    return 0;
}

/* Raw reading to hundredths of a degree: T = 175.72 * raw / 65536 - 46.85 */
static int32_t to_centidegrees(uint16_t raw)
{
    /* 5. Fixed point. 17572 is 175.72 scaled by 100; 4685 is 46.85 scaled
     *    the same way. */
    (void) raw;
    return 0;
}

static void show_temperature(int32_t centidegrees)
{
    /* 6. Light more of your four LEDs the warmer it is. */
    (void) centidegrees;
}

int main(void)
{
    /* 7. Set up the LED pins as outputs -- the board's own on PA5 and the
     *    four you added. */

    i2c_setup();

    while (1) {
        uint16_t raw = si7021_read_raw();
        show_temperature(to_centidegrees(raw));

        /* 8. Wait a little before reading again. A sensor does not need
         *    polling thousands of times a second. */
    }
}
