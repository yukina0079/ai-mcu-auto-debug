# Verified Boards / 已验证板卡

![Verified board evidence](assets/verified-board-evidence.png)

This page separates verified evidence from candidate support. A board is marked `verified` only when the repository has a reproducible workflow and report evidence.

本页区分真实验证证据和候选支持。只有仓库中具备可复现 workflow 与报告证据的板卡，才标记为 `verified`。

## Board Matrix / 板卡矩阵

| Board / DUT | Status | Debug Instrument | UART Observation | Notes |
|---|---|---|---|---|
| STM32F103RCT6 generic board | candidate | DAPLink/CMSIS-DAP through OpenOCD | optional | Primary development target and example configs are included. |
| ESP32-C3 SuperMini | verified debug link | Built-in USB Serial/JTAG through Espressif OpenOCD | COM13 / 115200 on verified bench | Chip identity, 4 MB Flash, RISC-V registers, memory read, hardware breakpoint, single-step, resume, and serial log verified. |

## Verification Requirements / 验证要求

To move a board from `candidate` to `verified`, add a report that shows:

从 `candidate` 提升到 `verified`，需要报告证明：

- exact chip identity and context source;
- debug probe and target config;
- build/smoke result;
- read-only debug evidence, including nonzero PC/SP/xPSR where applicable;
- memory read evidence from an approved memory range;
- UART observation when the bench includes a serial instrument;
- failure notes and uncertainty instead of silent assumptions.

- 精确芯片身份和 context 来源；
- 调试探针与 target config；
- build/smoke 结果；
- 只读调试证据，适用时包含非零 PC/SP/xPSR；
- 来自已批准内存区域的读取证据；
- bench 包含串口 instrument 时的 UART observation；
- 失败说明和不确定性，而不是静默假设。

## Current Public Position / 当前公开状态

The project is usable as a toolchain today, but broad board verification is intentionally conservative. New boards should be added one by one with evidence-backed reports.

项目当前可以作为工具链使用，但公开板卡验证保持保守。新板卡应按证据报告逐个加入。
