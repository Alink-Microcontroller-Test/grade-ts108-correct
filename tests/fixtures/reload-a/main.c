/* Test fixture A for the firmware-reload test. Not an exercise.
 *
 * Writes one recognisable word to a fixed address in SRAM and then spins.
 * Fixture B writes a different word to the same address, so a test can tell
 * which of the two is actually running.
 *
 * The address is absolute rather than a variable on purpose. A variable would
 * land in .bss, which the startup code zeroes, and the point of this pair is
 * to observe what survives a reset and what a newly loaded image writes.
 *
 * 0x20008000 is 32K into a 96K SRAM: clear of .data and .bss at the bottom,
 * and clear of the stack, which grows down from the top.
 */

#include <stdint.h>

#define MARK (*(volatile uint32_t *) 0x20008000UL)

#define FIXTURE_A 0xAAAA0001UL

int main(void)
{
    MARK = FIXTURE_A;

    for (;;) {
        /* Nothing. The test reads MARK; it does not need this to do more. */
    }
}
