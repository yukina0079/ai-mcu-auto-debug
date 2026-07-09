# AI Agent Usage / AI Agent 使用指南

This file is kept for compatibility. The primary public guide is [AGENT_QUICKSTART.md](AGENT_QUICKSTART.md).

本文件保留用于兼容旧链接。主要公开指南请看 [AGENT_QUICKSTART.md](AGENT_QUICKSTART.md)。

## Minimal Safe Flow / 最小安全流程

```powershell
ai-mcu-debug agent-bootstrap --project . --client generic-json
ai-mcu-debug workflow-plan --project . --chip <chip>
ai-mcu-debug doc-intake --project . --chip <chip>
ai-mcu-debug ai-debug --mode dry-run --workspace-config .embeddedskills/config.json
```

Hardware-affecting actions stay opt-in: no flash, no repair, no force, no writes, and no parallel hardware debug sessions unless the user explicitly approves the current board and operation.

硬件影响操作保持显式授权：没有用户针对当前板卡和操作的明确批准，不烧录、不修复、不强制、不写入，也不并行运行硬件调试会话。
