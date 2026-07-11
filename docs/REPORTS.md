# Reports / 报告

![Reports and verified boards](assets/golden-suite-reports.png)

Reports are the evidence layer for AI MCU automation. They let another agent or engineer understand what happened without trusting a chat transcript.

报告是 AI MCU 自动化的证据层。另一个 agent 或工程师可以通过报告理解发生了什么，而不是只相信聊天记录。

## Report Types / 报告类型

- `capability-audit`: static readiness across CLI, API, MCP, tests, docs, and safety policy.
- `ai-debug`: build/debug/runtime evidence from one guarded automation loop.
- `connection-diagnose`: bounded attach attempts without flash or memory writes.
- `hardware-id`: read-only silicon identity evidence.
- `serial-log`: UART observation captured directly through pyserial.
- `camera-capture` / `vision-analyze`: image hash, quality metrics, optional baseline change metrics, and agent visual inspection evidence.
- `export-handoff`: replayable package for another agent or CI job.

- `capability-audit`：CLI、API、MCP、测试、文档和安全策略的静态就绪检查。
- `ai-debug`：一次受保护自动化闭环中的构建、调试和运行证据。
- `connection-diagnose`：不烧录、不写内存的有限连接诊断。
- `hardware-id`：只读硅片身份识别证据。
- `serial-log`：通过 pyserial 直接采集的 UART observation。
- `camera-capture` / `vision-analyze`：图像哈希、画质指标、可选基线变化指标和 agent 视觉分析证据。
- `export-handoff`：交给另一个 agent 或 CI 的可回放包。

## Minimum Fields / 最小字段

Every public report should include:

每份公开报告应包含：

- board/DUT identity;
- instrument and target config;
- command or MCP tool called;
- safety gates and whether flash/repair/force were allowed;
- build result, smoke result, debug result, and serial/runtime log evidence when available;
- knowledge context source and uncertainty;
- artifacts needed for replay.

- 板卡/DUT 身份；
- instrument 和 target config；
- 执行的命令或 MCP 工具；
- 安全闸门，以及是否允许 flash/repair/force；
- 可用时包含 build、smoke、debug、serial/runtime log 证据；
- 知识库 context 来源和不确定性；
- 回放所需的产物。

## Example Commands / 示例命令

```powershell
ai-mcu-debug capability-audit --project . --output debug_runs/capability_audit/latest.json
ai-mcu-debug serial-log --port COM3 --baud 115200 --duration-s 5 --output debug_runs/serial/latest.json
ai-mcu-debug camera-capture --camera-index 0 --image-output debug_runs/vision/latest.jpg --report-output debug_runs/vision/latest.json --allow-camera
ai-mcu-debug export-handoff --output debug_runs/handoff.zip --project . --report-dir debug_runs --zip
ai-mcu-debug replay-handoff --manifest debug_runs/handoff/handoff_manifest.json
```

Generated reports and handoff packages are ignored by Git by default. Publish only lightweight evidence that is intended for public review.

生成报告和 handoff 包默认被 Git 忽略。只发布适合公开审查的轻量证据。

Replay policy note: `workflow-run --no-hardware` is the safe replay form because `replay_workflow_run_may_touch_hardware` when that flag is absent.

回放策略说明：`workflow-run --no-hardware` 是安全回放形式，因为缺少该参数时 `replay_workflow_run_may_touch_hardware`。
