# 工具链模型

![Bench、DUT 与 Instrument](assets/bench-dut-instrument.png)

AI MCU Auto Debug 借用少量实验台术语，帮助 Agent 准确描述硬件配置，但项目定位仍是自动化工具链，并非完整实验室平台。

## 核心概念

- `Orchestrator`：运行工具的主机、CI runner 或 AI Agent 环境。
- `Bench`：由 DUT、Instrument、Workflow、接线说明和安全策略组成的命名配置。
- `DUT`：被测 MCU 开发板。
- `Instrument`：调试探针、UART 适配器、运行日志命令或可选摄像头。
- `Workflow`：用于部署、构建、调试、观测和报告的可复现命令。
- `Evidence`：约束 Agent 判断的 JSON、Markdown 报告与日志。

## 配置示例

```text
configs/benches/stm32f103_minimal.yaml
configs/boards/stm32f103rct6_daplink.yaml
configs/instruments/daplink_cmsis_dap.yaml
configs/instruments/uart_serial.yaml
configs/workflows/stm32f103_readonly_debug.yaml
```

摄像头是可选的被动 Instrument。工具采集单帧并通过 MCP 标准 `image` 内容交给视觉 Agent 理解；摄像头访问需要逐次明确允许，图像判断不能替代电气与在线调试证据。
