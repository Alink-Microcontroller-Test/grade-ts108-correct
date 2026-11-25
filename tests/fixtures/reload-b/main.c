/* Test fixture B for the firmware-reload test. Not an exercise.
 *
 * The other half of the pair. See tests/fixtures/reload-a/main.c for why the
 * address is absolute and where it sits in SRAM.
 *
 * Writes a different word to the same address as fixture A. Because a reset
 * does not clear SRAM, a test that loads A, swaps to B and then reads this
 * address can distinguish three outcomes rather than two:
 *
 *   B's word  -- the swap worked and B is running
 *   A's word  -- the swap did not take effect, however it reported itself
 *   anything else -- the board is not running either of them
 *
 * A swap that silently failed would otherwise look exactly like a successful
 * load of a program that does nothing, which is the confusion this pair is
 * shaped to remove.
 */

#include <stdint.h>

#define MARK (*(volatile uint32_t *) 0x20008000UL)

#define FIXTURE_B 0xBBBB0002UL

int main(void)
{
    MARK = FIXTURE_B;

    for (;;) {
        /* Nothing. The test reads MARK; it does not need this to do more. */
    }
}
