# AI MCU Auto Debug

[中文](README.md) | [English](README_EN.md)

[![License: MIT](https://img.shields.io/badge/License-MIT-green.svg)](LICENSE)
[![Python](https://img.shields.io/badge/Python-3.10%2B-blue.svg)](pyproject.toml)

![AI MCU Auto Debug 总览](docs/assets/hero-ai-mcu-debug.png)

AI MCU Auto Debug 是一个面向 AI Agent 的开源 MCU 自动调试工具链。它把代码编写、构建、烧录、在线调试、串口观测、摄像头画面和证据报告连接成自动化闭环。

项目坚持低耦合：复用 CMake、Keil、ESP-IDF、OpenOCD、J-Link、pyOCD、probe-rs、CMSIS-SVD、UART 和用户提供的芯片资料，通过小型适配器统一暴露为 CLI、Python API、MCP 工具和可安装 Skill，而不是把所有能力绑定到单一平台。

> 仓库中的说明图由 AI 生成，仅用于表达架构，不代表特定厂商板卡、探针或认证。

## 快速开始

把仓库地址发给 Codex、Claude、OpenCode、Trae、Qoder 或其他 AI 编程工具，并让它先执行安全部署检查：

```powershell
git clone https://github.com/yukina0079/ai-mcu-auto-debug.git
cd ai-mcu-auto-debug
python -m venv .venv
.\.venv\Scripts\Activate.ps1
python -m pip install -e .
ai-mcu-debug agent-bootstrap --project . --client generic-json
ai-mcu-debug doctor
ai-mcu-debug capability-audit --project .
```

推荐发给 Agent 的第一条提示词：

```text
把这个仓库作为 AI MCU 自动调试工具链使用。先运行 agent-bootstrap，再用 workflow-plan 判断下一步。除非我明确批准当前板卡和操作，否则不要烧录、修改代码、强制写入，也不要并行占用同一块板卡的调试接口。缺少 MCU 资料时向我索要，不要猜测资料地址。
```

## 自动化闭环

![AI MCU 自动调试闭环](docs/assets/closed-loop-workflow.png)

- 自然语言目标：用户描述需求，Agent 规划步骤并调用工具。
- 代码与构建：支持 CMake、命令式构建、Keil、PlatformIO 和 ESP-IDF 等现有工具链。
- 在线调试：复位、暂停、恢复、断点、单步、核心寄存器和内存读写。
- 运行观测：UART、RTT、SWO、外部日志命令以及串口直接采集。
- 视觉观测：摄像头采集后通过标准 MCP 图像内容直接交给具备视觉能力的 AI 分析。
- 知识约束：从用户提供的 SVD、linker、startup、datasheet、reference manual 和 errata 生成 `mcu_context.json`，防止猜测寄存器含义。
- 证据报告：输出 JSON、Markdown、日志和可回放 handoff 包，为下一轮修复提供依据。

## Agent 兼容

![Agent 兼容与共享工具层](docs/assets/agent-toolchain-compatibility.png)

CLI、Python API、MCP 和内置 Skill 暴露同一套能力。多数 Agent 只需要仓库地址，就能完成环境检查和接入配置。

```powershell
ai-mcu-debug agent-bootstrap --client codex --project .
ai-mcu-debug agent-bootstrap --client claude-desktop --project .
ai-mcu-debug agent-bootstrap --client claude-code --project .
ai-mcu-debug agent-bootstrap --client opencode --project .
ai-mcu-debug agent-bootstrap --client trae --project .
ai-mcu-debug agent-bootstrap --client qoder --project .
ai-mcu-debug mcp-config --client generic-json --project .
ai-mcu-debug mcp-smoke --project .
```

对于配置格式不公开或不稳定的客户端，`mcp-config` 会输出通用 MCP JSON，并保留仓库根目录下的 CLI 作为后备入口，不猜测私有配置。

## 核心模型

![Bench、DUT、Instrument 与 Workflow](docs/assets/bench-dut-instrument.png)

- `Bench`：由 DUT、仪器、接线说明、Workflow 和安全策略组成的可复现配置。
- `DUT`：被测 MCU 板卡。
- `Instrument`：调试探针、串口适配器、运行日志命令或可选摄像头。
- `Workflow`：环境检查、构建、观测、调试和报告等可重复步骤。
- `Evidence/Report`：可供其他 Agent 或工程师回放与审计的产物。

配置示例：

```text
configs/benches/stm32f103_minimal.yaml
configs/boards/stm32f103rct6_daplink.yaml
configs/instruments/daplink_cmsis_dap.yaml
configs/instruments/uart_serial.yaml
configs/instruments/camera_usb_optional.yaml
configs/workflows/stm32f103_readonly_debug.yaml
configs/benches/esp32c3_supermini.yaml
configs/instruments/esp32c3_usb_serial_jtag.yaml
configs/workflows/esp32c3_supermini_readonly_debug.yaml
```

## 已验证硬件

| 板卡 | 状态 | 已验证路径 | 验证内容 |
|---|---|---|---|
| STM32F103RCT6 通用板 | 已验证 | DAPLink/CMSIS-DAP + OpenOCD + GDB | Cortex-M3 与 256 KiB Flash 识别、构建、烧录校验、复位暂停、核心寄存器、RAM 读取、源码断点、单步和恢复运行。验证时未连接 NRST。 |
| ESP32-C3 SuperMini | 调试链路已验证 | 内置 USB Serial/JTAG + Espressif OpenOCD + RISC-V GDB | 芯片与 4 MB Flash 识别、寄存器、内存读取、硬件断点、单步、恢复运行和串口日志。 |

ESP32-C3 通过可选 ESP-IDF 后端接入。`doctor` 能发现 EIM 或 VS Code 扩展管理的 ESP-IDF、Espressif OpenOCD 和 RISC-V GDB，不要求加入全局 `PATH`。

## 硬件调试流程

```powershell
ai-mcu-debug resolve-chip --project . --chip STM32F103RCT6
ai-mcu-debug doc-intake --project . --chip STM32F103RCT6
ai-mcu-debug prepare-mcu --project . --chip STM32F103RCT6 --svd <device.svd> --linker <linker.ld> --startup <startup.c> --doc datasheet=<datasheet.pdf-or-md> --doc reference_manual=<reference.pdf-or-md> --doc errata=<errata.pdf-or-md> --output examples/mcu_context.json
ai-mcu-debug check-context --context examples/mcu_context.json
ai-mcu-debug init-workspace --project . --chip STM32F103RCT6 --context examples/mcu_context.json
ai-mcu-debug workflow-plan --project . --chip STM32F103RCT6
ai-mcu-debug ai-debug --mode dry-run --workspace-config .embeddedskills/config.json
ai-mcu-debug ai-debug --mode read-only --workspace-config .embeddedskills/config.json
```

Windows 可选环境：

```powershell
winget install xpack-dev-tools.openocd
winget install Arm.GnuArmEmbeddedToolchain
python -m pip install pyocd pyserial
ai-mcu-debug doctor --debug-backend openocd-gdb
ai-mcu-debug probe-scan
```

## 串口观测

![UART 串口观测与证据生成](docs/assets/serial-observation.png)

```powershell
ai-mcu-debug serial-log --port COM3 --baud 115200 --duration-s 5 --output debug_runs/serial/latest.json
```

串口报告保留端口、波特率、时间范围、原始日志和观测结论。也可以通过 `runtime-log` 复用已有 UART、RTT、SWO 或外部日志工具。

## 摄像头与视觉 AI

安装可选视觉依赖：

```powershell
python -m pip install -e ".[vision]"
ai-mcu-debug camera-scan --allow-camera
ai-mcu-debug camera-capture --camera-index 0 --image-output debug_runs/vision/latest.jpg --report-output debug_runs/vision/latest.json --allow-camera
```

MCP 工具 `camera_scan`、`capture_board_image` 和 `analyze_board_image` 提供相同能力。成功采集后会返回 JSON 证据和标准 MCP `image` 内容，视觉 Agent 可以直接查看 LED、显示屏、接线和板卡状态。

摄像头会拍摄周边环境，因此默认禁用；每次扫描或采集必须显式设置 `allow_camera=true` 或 `--allow-camera`。采集结果默认写入被 Git 忽略的 `debug_runs/vision/`，不会自动发布到仓库。

## Golden Suite 与公开证据

![Golden Suite 与证据报告](docs/assets/golden-suite-reports.png)

公开仓库区分“能力声明”和“验证证据”。只有具备可复现 Workflow 和报告产物的板卡才标记为 `verified`，证据不足的板卡保持 `candidate`。

- [Agent 快速接入](docs/AGENT_QUICKSTART.md)
- [工具链模型](docs/AI_LAB_MODEL.md)
- [Golden Suite](docs/GOLDEN_SUITES.md)
- [已验证板卡](docs/VERIFIED_BOARDS.md)
- [报告与证据](docs/REPORTS.md)

![已验证板卡的证据要求](docs/assets/verified-board-evidence.png)

## 安全策略

- 同一块板卡的调试接口是独占资源，不并行运行 OpenOCD、GDB、pyOCD、J-Link、probe-rs 或其他硬件调试会话。
- 烧录、代码修复、强制操作、寄存器/内存写入、option bytes 和时钟/复位控制写入都需要针对当前板卡的明确授权。
- 工具默认向用户索要 MCU 资料，不自行搜索或猜测 datasheet URL。
- 外设寄存器含义和写入约束必须来自 `mcu_context.json`；未知地址默认阻止。
- `workflow-run --no-hardware` 是 handoff 回放的安全形式；缺少该参数时会记录硬件访问风险。
- 摄像头访问默认关闭，采集画面默认不进入 Git。

## 许可证

本项目基于 [MIT License](LICENSE) 开源。
