# STM32F103RCT6 MCU 调试记录文档

## 来源

- SVD: `examples\svd\STM32F103_min.svd`
- Linker: `examples\firmware\stm32f103_blinky\linker.stm32f103rct6.ld`
- Startup: `examples\firmware\stm32f103_blinky\src\startup_stm32f103.c`

## Memory Map

- FLASH: 0x08000000 - 0x0803FFFF (262144 bytes)
- RAM: 0x20000000 - 0x2000BFFF (49152 bytes)

## 外设寄存器

### RCC @ 0x40021000
Reset and clock control.
- RCC.APB2ENR @ 0x40021018, access=read-write, reset=0x0

### GPIOC @ 0x40011000
General-purpose IO port C.
- GPIOC.CRH @ 0x40011004, access=read-write, reset=0x44444444
- GPIOC.IDR @ 0x40011008, access=read-only, reset=0x0
- GPIOC.BSRR @ 0x40011010, access=write-only, reset=0x0
- GPIOC.BRR @ 0x40011014, access=write-only, reset=0x0
- GPIOC.ODR @ 0x4001100C, access=read-write, reset=0x0

## 调试注意事项

- Use mcu_context.json as evidence before explaining or writing registers for STM32F103RCT6.
- CPU core from SVD: CM3.
- Memory ranges are taken from linker script and should be checked before raw memory writes.
- Interrupt vector symbols are taken from startup file and can guide reset/HardFault debugging.
- Do not invent register fields. If a register or field is missing from SVD, report uncertainty.

## Errata 风险清单

- `errata:658ef0d20b` [warning] documentation_mismatch: Mark conclusion uncertain when behavior differs from documentation (examples\docs\stm32f103_errata_notes.md:6)
  - Evidence: - If behavior differs from register documentation, mark the debug conclusion as uncertain until confirmed.
  - Mitigation: Mark the conclusion as uncertain and cite errata evidence.
- `errata:6930cf1b96` [warning] documentation_mismatch: Mark conclusion uncertain when behavior differs from documentation (examples\docs\stm32f103_errata_notes.md:7)
  - Evidence: - GPIOC.CRH behavior differs from register documentation on affected revision; use workaround before writing MODE13/CNF13.
  - Mitigation: Mark the conclusion as uncertain and cite errata evidence.
- `errata:a92461b8de` [advisory] revision_scope: Verify exact part number and revision (examples\docs\stm32f103_errata_notes.md:5)
  - Evidence: - Always check the actual errata document for the exact part number and revision.
  - Mitigation: Check device marking/revision ID against the vendor errata.