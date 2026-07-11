# Agent Quickstart / Agent 快速接入

![MCP skill deployment](assets/mcp-skill-deployment.png)

Use this guide when an AI coding agent receives only the repository URL and needs to deploy itself safely.

当 AI 编程工具只拿到仓库地址，需要自行安全部署时，使用这份指南。

## First Prompt / 第一条提示词

```text
Use this repository as an AI MCU automation toolchain. Run agent-bootstrap first, then use workflow-plan before hardware actions. Do not flash, repair, force writes, or run parallel hardware debug sessions unless I explicitly approve the current board and operation.
```

```text
把这个仓库当作 AI MCU 自动化工具链使用。先运行 agent-bootstrap，再用 workflow-plan 判断下一步。除非我明确批准当前板卡和操作，否则不要烧录、修复代码、强制写入，也不要并行运行硬件调试会话。
```

## Safe Bootstrap / 安全部署检查

```powershell
python -m pip install -e .
ai-mcu-debug agent-bootstrap --project . --client generic-json
ai-mcu-debug doctor
ai-mcu-debug capability-audit --project .
ai-mcu-debug mcp-smoke --project .
```

Client-specific hints / 客户端提示：

```powershell
ai-mcu-debug mcp-config --client codex --project .
ai-mcu-debug mcp-config --client claude-desktop --project .
ai-mcu-debug mcp-config --client claude-code --project .
ai-mcu-debug mcp-config --client opencode --project .
ai-mcu-debug mcp-config --client trae --project .
ai-mcu-debug mcp-config --client qoder --project .
```

For clients without stable MCP configuration, use the CLI commands directly from the repository root.

如果某个客户端没有稳定的 MCP 配置入口，就从仓库根目录直接调用 CLI。

## Default Workflow / 默认流程

1. Run `agent-bootstrap` and read its JSON report.
2. Run `workflow-plan` before touching hardware.
3. Ask the user for exact MCU documents when `doc-intake` reports missing inputs.
4. Build context with user-provided SVD/linker/startup/datasheet/reference manual/errata.
5. Run `ai-debug --mode dry-run` first, then `ai-debug --mode read-only` when hardware is connected.
6. Use `serial-log` or MCP `collect_serial_log` for UART observation when a serial adapter is present.
7. Use `camera-capture --allow-camera` or MCP `capture_board_image` only after the user explicitly allows camera access; inspect the returned image together with debug and log evidence.
8. Export reports or handoff packages when another agent or engineer needs to audit the run.

1. 先运行 `agent-bootstrap` 并阅读 JSON 报告。
2. 碰硬件前先运行 `workflow-plan`。
3. `doc-intake` 报缺资料时，向用户索要精确 MCU 资料。
4. 使用用户提供的 SVD/linker/startup/datasheet/reference manual/errata 构建 context。
5. 先运行 `ai-debug --mode dry-run`，硬件已连接后再运行 `ai-debug --mode read-only`。
6. 有串口适配器时，用 `serial-log` 或 MCP `collect_serial_log` 做 UART observation。
7. 仅在用户明确允许摄像头访问后使用 `camera-capture --allow-camera` 或 MCP `capture_board_image`，并将返回图像与调试和日志证据一起分析。
8. 需要交接给其他 agent 或工程师时，导出报告或 handoff 包。

## Safety Rules / 安全规则

- Do not run parallel hardware debug sessions against one board.
- Do not flash, repair, force, or write memory/registers without explicit user approval for the current board.
- Do not guess datasheet URLs. Ask for local files, official URLs, or a user-provided document repository.
- Treat missing errata as `errata_missing`, not proof of no risk.

- 不要对同一块板并行运行硬件调试会话。
- 没有用户针对当前板卡的明确批准，不要烧录、修复、强制操作或写内存/寄存器。
- 不要猜 datasheet URL。向用户索要本地文件、官方 URL 或用户提供的资料仓库。
- 缺少 errata 时记录为 `errata_missing`，不能当作“没有风险”。
