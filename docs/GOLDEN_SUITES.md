# Golden Suites / 黄金测试套件

![Golden suite reports](assets/golden-suite-reports.png)

Golden suites are reproducible workflows that prove a board/toolchain path with evidence instead of claims.

Golden suite 是可复现的工作流，用证据证明板卡/工具链路径，而不是只写宣传描述。

## Current Suites / 当前套件

| Suite | Status | DUT | Instruments | Evidence |
|---|---|---|---|---|
| `stm32f103_readonly_debug` | candidate | STM32F103RCT6 | DAPLink/CMSIS-DAP, optional UART | Context check, build, smoke test, read-only debug report |

`candidate` means the suite exists and can be run, but public verification depends on the current maintainer bench and report artifacts.

`candidate` 表示套件已存在且可运行，但公开 verified 状态取决于当前维护者 bench 和报告产物。

## Expected Evidence / 期望证据

- Environment report from `doctor`.
- Probe evidence from `probe-scan` or target config.
- Context validation from `check-context`.
- Build and smoke test output.
- Debug evidence: reset/halt, core registers, memory read, breakpoint, single-step when configured.
- UART observation through `runtime-log`, `serial-log`, or MCP `collect_serial_log` when a UART instrument exists.
- Handoff package or JSON report that another agent can replay without touching hardware by default.

- `doctor` 环境报告。
- `probe-scan` 或 target config 提供的探针证据。
- `check-context` 的 context 校验结果。
- 构建和 smoke test 输出。
- 调试证据：按配置包含 reset/halt、核心寄存器、内存读取、断点、单步。
- 存在 UART instrument 时，通过 `runtime-log`、`serial-log` 或 MCP `collect_serial_log` 做 UART observation。
- 默认不触碰硬件也可被另一个 agent 回放的 handoff 包或 JSON 报告。

## Run Example / 运行示例

```powershell
ai-mcu-debug check-context --context examples/mcu_context.stm32f103rct6.json
ai-mcu-debug build --config examples/build.stm32f103rct6.json
ai-mcu-debug smoke-test --config examples/build.stm32f103rct6.json
ai-mcu-debug ai-debug --mode read-only --project . --context examples/mcu_context.stm32f103rct6.json --build-config examples/build.stm32f103rct6.json --target examples/debug.target.cmsis-dap.stm32f103rct6.json --task examples/debug_task.stm32f103rct6.json
```

No suite should require camera/vision in the current public release.

当前公开版本的 suite 不应要求摄像头/视觉能力。
