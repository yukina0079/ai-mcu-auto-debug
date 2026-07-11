# Toolchain Model / 工具链模型

![Bench DUT Instrument](assets/bench-dut-instrument.png)

AI MCU Auto Debug borrows a few lab-style words because they help agents reason about hardware setups, but the project remains an automation toolchain rather than a full lab platform.

AI MCU Auto Debug 借用少量实验台概念，帮助 agent 理解硬件配置，但项目定位仍是自动化工具链，不是完整实验室平台。

## Concepts / 概念

- `Orchestrator`: the host PC, CI runner, or AI agent environment that runs the tool.
- `Bench`: a named setup combining DUT, instruments, workflow, wiring notes, and safety policy.
- `DUT`: the MCU board under test.
- `Instrument`: debug probe, UART adapter, runtime-log command, or optional camera/signal tool.
- `Workflow`: repeatable commands for setup, build, debug, observation, and reporting.
- `Evidence`: JSON/Markdown reports and logs used to ground the agent.

- `Orchestrator`：运行工具的主机、CI runner 或 AI agent 环境。
- `Bench`：由 DUT、instrument、workflow、接线说明和安全策略组成的命名配置。
- `DUT`：被测 MCU 开发板。
- `Instrument`：调试探针、UART 适配器、runtime-log 命令，或可选摄像头/信号工具。
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

Camera/vision is an optional passive instrument. It provides still-image capture, quality metrics, baseline change detection, and an MCP image block for agent visual inspection. Camera access is explicit per call and does not replace electrical/debug evidence.

摄像头/视觉是可选的被动 instrument，提供单帧采集、画质指标、基线变化检测以及供 agent 视觉分析的 MCP 图像内容。摄像头访问必须逐次明确允许，且不能替代电气和调试证据。
