/* STM32F401RE memory layout.
 *
 * Shared by every exercise. The sizes are the real device's, so a program too
 * large to program onto a NUCLEO-F401RE fails to link here rather than
 * appearing to work and failing on the bench.
 */

MEMORY
{
    FLASH (rx)  : ORIGIN = 0x08000000, LENGTH = 512K
    RAM   (rwx) : ORIGIN = 0x20000000, LENGTH = 96K
}

/* The stack grows downwards from the top of RAM. The processor loads this as
 * its stack pointer from the first word of the vector table. */
_estack = ORIGIN(RAM) + LENGTH(RAM);

SECTIONS
{
    /* The vector table must be first: the processor reads the reset vector
     * from the very start of flash. */
    .isr_vector : { KEEP(*(.isr_vector)) } > FLASH

    .text :
    {
        *(.text*)
        *(.rodata*)
        . = ALIGN(4);
        _etext = .;
    } > FLASH

    /* Initialised variables are stored in flash and copied into RAM by the
     * reset handler. AT places the copy in flash; the addresses are in RAM. */
    .data : AT (_etext)
    {
        . = ALIGN(4);
        _sdata = .;
        *(.data*)
        . = ALIGN(4);
        _edata = .;
    } > RAM

    .bss :
    {
        . = ALIGN(4);
        _sbss = .;
        *(.bss*)
        *(COMMON)
        . = ALIGN(4);
        _ebss = .;
    } > RAM

    /* Fails the link if the program plus a minimum stack would not fit. */
    ._stack_check :
    {
        . = ALIGN(8);
        . = . + 1K;
    } > RAM
}
