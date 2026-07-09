# Toolchain Model / 工具链模型

![Bench DUT Instrument](assets/bench-dut-instrument.png)

AI MCU Auto Debug borrows a few lab-style words because they help agents reason about hardware setups, but the project remains an automation toolchain rather than a full lab platform.

AI MCU Auto Debug 借用少量实验台概念，帮助 agent 理解硬件配置，但项目定位仍是自动化工具链，不是完整实验室平台。

## Concepts / 概念

- `Orchestrator`: the host PC, CI runner, or AI agent environment that runs the tool.
- `Bench`: a named setup combining DUT, instruments, workflow, wiring notes, and safety policy.
- `DUT`: the MCU board under test.
- `Instrument`: debug probe, UART adapter, runtime-log command, or future optional camera/signal tool.
- `Workflow`: repeatable commands for setup, build, debug, observation, and reporting.
- `Evidence`: JSON/Markdown reports and logs used to ground the agent.

- `Orchestrator`：运行工具的主机、CI runner 或 AI agent 环境。
- `Bench`：由 DUT、instrument、workflow、接线说明和安全策略组成的命名配置。
- `DUT`：被测 MCU 开发板。
- `Instrument`：调试探针、UART 适配器、runtime-log 命令，或未来可选摄像头/信号工具。
- `Workflow`：用于部署、构建、调试、观测和报告的可复现命令。
- `Evidence`：用于约束 agent 的 JSON/Markdown 报告和日志。

## Example Files / 示例文件

```text
configs/benches/stm32f103_minimal.yaml
configs/boards/stm32f103rct6_daplink.yaml
configs/instruments/daplink_cmsis_dap.yaml
configs/instruments/uart_serial.yaml
configs/workflows/stm32f103_readonly_debug.yaml
```

Camera/vision remains a future optional instrument. Current public readiness is based on the non-vision flow: build, debug, UART observation, knowledge guard, and reports.

摄像头/视觉仍是未来可选 instrument。当前公开就绪度基于非视觉流程：构建、调试、UART observation、知识库保护和报告。
