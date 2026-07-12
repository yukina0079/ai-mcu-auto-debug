# Golden Suite

![Golden Suite 与报告](assets/golden-suite-reports.png)

Golden Suite 是可复现的验证流程，用报告和日志证明板卡、工具链与调试路径确实工作，而不是只声明支持。

## 当前套件

| 套件 | 状态 | DUT | Instrument | 已验证证据 |
|---|---|---|---|---|
| `stm32f103_readonly_debug` | 已验证 | STM32F103RCT6 | DAPLink/CMSIS-DAP + OpenOCD，可选 UART | 构建与烧录校验、Cortex-M3 身份、复位暂停、核心寄存器、RAM 读取、源码断点、单步、恢复运行和基于资料的 context |
| `esp32c3_supermini_readonly_debug` | 调试链路已验证 | ESP32-C3 SuperMini | 内置 USB Serial/JTAG | ESP-IDF 环境、芯片与 Flash 身份、寄存器、内存、硬件断点、单步和串口日志 |

`candidate` 表示套件已存在且可以执行，但尚未获得当前维护者 Bench 的公开验证报告。

## 期望证据

- `doctor` 生成的环境报告。
- `probe-scan` 或目标配置提供的探针证据。
- `check-context` 的知识 context 校验结果。
- 构建与 smoke test 输出。
- 按配置执行的复位暂停、核心寄存器、内存读取、断点和单步证据。
- 存在 UART Instrument 时，由 `runtime-log`、`serial-log` 或 MCP `collect_serial_log` 生成的串口观测。
- 默认不接触硬件即可供其他 Agent 回放的 handoff 包或 JSON 报告。

## 运行示例

```powershell
ai-mcu-debug check-context --context examples/mcu_context.stm32f103rct6.json
ai-mcu-debug build --config examples/build.stm32f103rct6.json
ai-mcu-debug smoke-test --config examples/build.stm32f103rct6.json
ai-mcu-debug ai-debug --mode read-only --project . --context examples/mcu_context.stm32f103rct6.json --build-config examples/build.stm32f103rct6.json --target examples/debug.target.cmsis-dap.stm32f103rct6.json --task examples/debug_task.stm32f103rct6.json
```

当前公开版本的 Golden Suite 不依赖摄像头或视觉能力。
