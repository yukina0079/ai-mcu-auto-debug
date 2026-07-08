#include <stdint.h>

#define RCC_APB2ENR (*(volatile uint32_t *)0x40021018u)
#define GPIOC_CRH (*(volatile uint32_t *)0x40011004u)
#define GPIOC_BSRR (*(volatile uint32_t *)0x40011010u)
#define GPIOC_BRR (*(volatile uint32_t *)0x40011014u)

#define RCC_APB2ENR_IOPCEN (1u << 4)
#define GPIOC13_MODE_MASK (0xFu << 20)
#define GPIOC13_OUTPUT_2MHZ_PUSH_PULL (0x2u << 20)
#define GPIOC13_PIN (1u << 13)

static void delay(volatile uint32_t cycles)
{
    while (cycles-- > 0u) {
        __asm volatile("nop");
    }
}

int main(void)
{
    RCC_APB2ENR |= RCC_APB2ENR_IOPCEN;
    GPIOC_CRH = (GPIOC_CRH & ~GPIOC13_MODE_MASK) | GPIOC13_OUTPUT_2MHZ_PUSH_PULL;

    while (1) {
        GPIOC_BRR = GPIOC13_PIN;
        delay(200000u);
        GPIOC_BSRR = GPIOC13_PIN;
        delay(200000u);
    }
}
