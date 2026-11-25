/* Startup for the STM32F401RE: the vector table and the reset handler.
 *
 * Shared by every exercise and by the setup self-test. You should not need to
 * change anything here.
 *
 * Every interrupt handler is a weak alias for Default_Handler, which is an
 * endless loop. To handle an interrupt, define a function with the matching
 * name in your own file -- for example:
 *
 *     void TIM2_IRQHandler(void) { ... }
 *
 * and the linker uses yours instead of the default. You do not need to
 * register it anywhere: the table below is what the processor reads.
 *
 * Which number each interrupt is, and which peripheral raises it, is in the
 * reference manual (RM0368), 'Interrupt and exception vectors'. That table is
 * worth reading before exercise 2.
 */

#include <stdint.h>

extern uint32_t _estack, _etext, _sdata, _edata, _sbss, _ebss;

int main(void);
void SystemInit(void) __attribute__((weak));

void Reset_Handler(void)
{
    /* Initialised variables live in flash and must be copied into RAM. */
    uint32_t *src = &_etext;
    for (uint32_t *dst = &_sdata; dst < &_edata; )
        *dst++ = *src++;

    /* Everything else starts at zero, and C promises that. */
    for (uint32_t *dst = &_sbss; dst < &_ebss; )
        *dst++ = 0;

    if (SystemInit)
        SystemInit();

    main();

    /* main returning on a microcontroller means there is nothing left to do. */
    for (;;) { }
}

void Default_Handler(void)
{
    /* An interrupt fired that nothing handles. Stopping here rather than
     * returning makes it visible in a debugger instead of silently looping. */
    for (;;) { }
}

#define ALIAS __attribute__((weak, alias("Default_Handler")))

/* Core exceptions */
void NMI_Handler(void)              ALIAS;
void HardFault_Handler(void)        ALIAS;
void MemManage_Handler(void)        ALIAS;
void BusFault_Handler(void)         ALIAS;
void UsageFault_Handler(void)       ALIAS;
void SVC_Handler(void)              ALIAS;
void DebugMon_Handler(void)         ALIAS;
void PendSV_Handler(void)           ALIAS;
void SysTick_Handler(void)          ALIAS;

/* Peripheral interrupts, in the order the processor reads them. */
void WWDG_IRQHandler(void)               ALIAS;
void PVD_IRQHandler(void)                ALIAS;
void TAMP_STAMP_IRQHandler(void)         ALIAS;
void RTC_WKUP_IRQHandler(void)           ALIAS;
void FLASH_IRQHandler(void)              ALIAS;
void RCC_IRQHandler(void)                ALIAS;
void EXTI0_IRQHandler(void)              ALIAS;
void EXTI1_IRQHandler(void)              ALIAS;
void EXTI2_IRQHandler(void)              ALIAS;
void EXTI3_IRQHandler(void)              ALIAS;
void EXTI4_IRQHandler(void)              ALIAS;
void DMA1_Stream0_IRQHandler(void)       ALIAS;
void DMA1_Stream1_IRQHandler(void)       ALIAS;
void DMA1_Stream2_IRQHandler(void)       ALIAS;
void DMA1_Stream3_IRQHandler(void)       ALIAS;
void DMA1_Stream4_IRQHandler(void)       ALIAS;
void DMA1_Stream5_IRQHandler(void)       ALIAS;
void DMA1_Stream6_IRQHandler(void)       ALIAS;
void ADC_IRQHandler(void)                ALIAS;
void EXTI9_5_IRQHandler(void)            ALIAS;
void TIM1_BRK_TIM9_IRQHandler(void)      ALIAS;
void TIM1_UP_TIM10_IRQHandler(void)      ALIAS;
void TIM1_TRG_COM_TIM11_IRQHandler(void) ALIAS;
void TIM1_CC_IRQHandler(void)            ALIAS;
void TIM2_IRQHandler(void)               ALIAS;
void TIM3_IRQHandler(void)               ALIAS;
void TIM4_IRQHandler(void)               ALIAS;
void I2C1_EV_IRQHandler(void)            ALIAS;
void I2C1_ER_IRQHandler(void)            ALIAS;
void I2C2_EV_IRQHandler(void)            ALIAS;
void I2C2_ER_IRQHandler(void)            ALIAS;
void SPI1_IRQHandler(void)               ALIAS;
void SPI2_IRQHandler(void)               ALIAS;
void USART1_IRQHandler(void)             ALIAS;
void USART2_IRQHandler(void)             ALIAS;
void EXTI15_10_IRQHandler(void)          ALIAS;
void RTC_Alarm_IRQHandler(void)          ALIAS;
void OTG_FS_WKUP_IRQHandler(void)        ALIAS;
void DMA1_Stream7_IRQHandler(void)       ALIAS;
void SDIO_IRQHandler(void)               ALIAS;
void TIM5_IRQHandler(void)               ALIAS;
void SPI3_IRQHandler(void)               ALIAS;
void DMA2_Stream0_IRQHandler(void)       ALIAS;
void DMA2_Stream1_IRQHandler(void)       ALIAS;
void DMA2_Stream2_IRQHandler(void)       ALIAS;
void DMA2_Stream3_IRQHandler(void)       ALIAS;
void DMA2_Stream4_IRQHandler(void)       ALIAS;
void OTG_FS_IRQHandler(void)             ALIAS;
void DMA2_Stream5_IRQHandler(void)       ALIAS;
void DMA2_Stream6_IRQHandler(void)       ALIAS;
void DMA2_Stream7_IRQHandler(void)       ALIAS;
void USART6_IRQHandler(void)             ALIAS;
void I2C3_EV_IRQHandler(void)            ALIAS;
void I2C3_ER_IRQHandler(void)            ALIAS;
void FPU_IRQHandler(void)                ALIAS;
void SPI4_IRQHandler(void)               ALIAS;

__attribute__((section(".isr_vector"), used))
void (* const vector_table[])(void) = {
    (void (*)(void)) &_estack,
    Reset_Handler,
    NMI_Handler,
    HardFault_Handler,
    MemManage_Handler,
    BusFault_Handler,
    UsageFault_Handler,
    0, 0, 0, 0,
    SVC_Handler,
    DebugMon_Handler,
    0,
    PendSV_Handler,
    SysTick_Handler,

    WWDG_IRQHandler,               /*  0 */
    PVD_IRQHandler,                /*  1 */
    TAMP_STAMP_IRQHandler,         /*  2 */
    RTC_WKUP_IRQHandler,           /*  3 */
    FLASH_IRQHandler,              /*  4 */
    RCC_IRQHandler,                /*  5 */
    EXTI0_IRQHandler,              /*  6 */
    EXTI1_IRQHandler,              /*  7 */
    EXTI2_IRQHandler,              /*  8 */
    EXTI3_IRQHandler,              /*  9 */
    EXTI4_IRQHandler,              /* 10 */
    DMA1_Stream0_IRQHandler,       /* 11 */
    DMA1_Stream1_IRQHandler,       /* 12 */
    DMA1_Stream2_IRQHandler,       /* 13 */
    DMA1_Stream3_IRQHandler,       /* 14 */
    DMA1_Stream4_IRQHandler,       /* 15 */
    DMA1_Stream5_IRQHandler,       /* 16 */
    DMA1_Stream6_IRQHandler,       /* 17 */
    ADC_IRQHandler,                /* 18 */
    0, 0, 0, 0,                    /* 19-22 reserved */
    EXTI9_5_IRQHandler,            /* 23 */
    TIM1_BRK_TIM9_IRQHandler,      /* 24 */
    TIM1_UP_TIM10_IRQHandler,      /* 25 */
    TIM1_TRG_COM_TIM11_IRQHandler, /* 26 */
    TIM1_CC_IRQHandler,            /* 27 */
    TIM2_IRQHandler,               /* 28 */
    TIM3_IRQHandler,               /* 29 */
    TIM4_IRQHandler,               /* 30 */
    I2C1_EV_IRQHandler,            /* 31 */
    I2C1_ER_IRQHandler,            /* 32 */
    I2C2_EV_IRQHandler,            /* 33 */
    I2C2_ER_IRQHandler,            /* 34 */
    SPI1_IRQHandler,               /* 35 */
    SPI2_IRQHandler,               /* 36 */
    USART1_IRQHandler,             /* 37 */
    USART2_IRQHandler,             /* 38 */
    0,                             /* 39 reserved */
    EXTI15_10_IRQHandler,          /* 40 */
    RTC_Alarm_IRQHandler,          /* 41 */
    OTG_FS_WKUP_IRQHandler,        /* 42 */
    0, 0, 0, 0,                    /* 43-46 reserved */
    DMA1_Stream7_IRQHandler,       /* 47 */
    0,                             /* 48 reserved */
    SDIO_IRQHandler,               /* 49 */
    TIM5_IRQHandler,               /* 50 */
    SPI3_IRQHandler,               /* 51 */
    0, 0, 0, 0,                    /* 52-55 reserved */
    DMA2_Stream0_IRQHandler,       /* 56 */
    DMA2_Stream1_IRQHandler,       /* 57 */
    DMA2_Stream2_IRQHandler,       /* 58 */
    DMA2_Stream3_IRQHandler,       /* 59 */
    DMA2_Stream4_IRQHandler,       /* 60 */
    0, 0, 0, 0, 0, 0,              /* 61-66 reserved */
    OTG_FS_IRQHandler,             /* 67 */
    DMA2_Stream5_IRQHandler,       /* 68 */
    DMA2_Stream6_IRQHandler,       /* 69 */
    DMA2_Stream7_IRQHandler,       /* 70 */
    USART6_IRQHandler,             /* 71 */
    I2C3_EV_IRQHandler,            /* 72 */
    I2C3_ER_IRQHandler,            /* 73 */
    0, 0, 0, 0, 0, 0, 0,           /* 74-80 reserved */
    FPU_IRQHandler,                /* 81 */
    0, 0,                          /* 82-83 reserved */
    SPI4_IRQHandler,               /* 84 */
};
