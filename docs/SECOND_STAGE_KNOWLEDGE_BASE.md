# 第二阶段 MCU 知识库与防幻觉用法

第二阶段目标是让 AI 在解释或写入寄存器前，有可检索、可引用、可校验的 MCU 上下文。

## 1. 生成 mcu_context.json

```text
python -m ai_mcu_debug.cli build-mcu-context --chip STM32F103C8 --svd examples/svd/STM32F103_min.svd --output examples/mcu_context.stm32f103.json --linker examples/firmware/stm32f103_blinky/linker.ld --startup examples/firmware/stm32f103_blinky/src/startup_stm32f103.c --board stm32f103_blinky --doc datasheet=examples/docs/stm32f103_datasheet_notes.md --doc errata=examples/docs/stm32f103_errata_notes.md
```

STM32F103RCT6 要使用独立 context，不能复用 C8 的 64K Flash / 20K RAM 上下文：

```text
python -m ai_mcu_debug.cli prepare-mcu --project examples/firmware/stm32f103_blinky --chip STM32F103RCT6 --package LQFP64 --board stm32f103rct6_daplink --svd examples/svd/STM32F103_min.svd --linker examples/firmware/stm32f103_blinky/linker.stm32f103rct6.ld --startup examples/firmware/stm32f103_blinky/src/startup_stm32f103.c --doc datasheet=examples/docs/stm32f103_datasheet_notes.md --doc errata=examples/docs/stm32f103_errata_notes.md --output examples/mcu_context.stm32f103rct6.json
python -m ai_mcu_debug.cli check-context --context examples/mcu_context.stm32f103rct6.json
python -m ai_mcu_debug.cli write-mcu-debug-doc --context examples/mcu_context.stm32f103rct6.json --output docs/STM32F103RCT6_DEBUG_RECORD.md
```

输入来源：

- CMSIS-SVD：外设、寄存器、字段、访问权限、reset value。
- Linker script：Flash/RAM 范围。
- Startup 文件：中断向量。
- Datasheet/reference manual/errata/board notes：本地 Markdown 或文本摘录。

## 2. 查询和解释寄存器

```text
python -m ai_mcu_debug.cli knowledge-query --context examples/mcu_context.stm32f103.json --query "GPIOC pin 13"
python -m ai_mcu_debug.cli knowledge-query --context examples/mcu_context.stm32f103.json --query "LED PC13" --mode vector --limit 3
python -m ai_mcu_debug.cli explain-register --context examples/mcu_context.stm32f103.json --register GPIOC.CRH
python -m ai_mcu_debug.cli explain-register --context examples/mcu_context.stm32f103.json --register 0x40011004
```

返回结果会包含 `reference.source`、寄存器名和地址。AI 输出结论时应引用这些字段，而不是凭记忆编造。

## 3. 写入前校验

```text
python -m ai_mcu_debug.cli validate-register-write --context examples/mcu_context.stm32f103.json --register GPIOC.CRH --value 0x00200000
python -m ai_mcu_debug.cli validate-address-write --context examples/mcu_context.stm32f103.json --address 0x08000000 --length 4
```

校验规则：

- 未知寄存器：拒绝。
- 只读寄存器或只读字段：拒绝。
- 设置保留位：拒绝。
- 写入 Flash/Option Bytes 等危险区域：要求审批或拒绝。
- 可能存在 write-one-to-clear 语义的字段：返回警告。

## 4. 接入实时调试命令

`debug-op write-memory` 可以带 `--context`，会在连接硬件前先执行知识库校验：

```text
python -m ai_mcu_debug.cli debug-op --target examples/debug.target.openocd.local.json --context examples/mcu_context.stm32f103.json write-memory --address 0x08000000 --data-hex 01020304
```

这类 Flash 写入会被拦截。确实需要执行时才加 `--force`。

外设寄存器读取也应带 `--context`，这样 AI 在读取前能先确认寄存器来自 SVD/上下文，而不是凭名字猜：

```text
python -m ai_mcu_debug.cli debug-op --target examples/debug.target.openocd.local.json --context examples/mcu_context.stm32f103.json read-register --register GPIOC.CRH
```

`pc`、`sp`、`lr`、`xpsr`、`r0` 到 `r15` 这类核心寄存器属于调试器内建语义，允许不依赖 SVD 直接读取；外设寄存器缺少 `--context` 时会被拦截。

外设寄存器名不会再被当成 GDB 核心寄存器读取；带 `--context` 的 `GPIOC.CRH` 会先由 SVD 解析到 `0x40011004`，再执行内存映射寄存器读取。

## 5. 生成 MCU 调试记录文档

```text
python -m ai_mcu_debug.cli write-mcu-debug-doc --context examples/mcu_context.stm32f103.json --output docs/STM32F103_DEBUG_RECORD.md
```

生成文档用于给 AI 对照，避免调试过程中幻觉寄存器地址、字段含义或内存范围。

## 6. 调试报告与知识库对照

```text
python -m ai_mcu_debug.cli analyze-debug-report --context examples/mcu_context.stm32f103.json --report debug_runs/first_phase_smoke_debug.json --output debug_runs/first_phase_smoke_debug.knowledge.json
```

对照内容：

- PC/SP/xPSR 是否符合 Cortex-M 和 memory map。
- memory read 是否落在 Flash/RAM 等已知区域，且整段不跨越边界。
- 外设寄存器值是否可以按 SVD 字段解码。
- 失败原因是否能找到相关 datasheet/reference/errata 证据；找不到时标记 `uncertain`，不强行归因。

## 7. Errata 风险清单

`build-mcu-context` 会从 `kind=errata` 的文档中抽取结构化风险，写入 `errata_risks`：

- `revision_scope`
- `documentation_mismatch`
- `write_hazard`
- `flag_semantics`
- `debug_connection`
- `clock_timing`
- `interrupt_dma`

每条风险包含稳定 `id`、严重级别、影响外设/寄存器/字段、source line、evidence 和 mitigation。`explain-register` 会返回相关 errata 风险，写操作校验只把 errata 当 warning/approval，不覆盖 SVD 的只读/保留位硬性拒绝。
