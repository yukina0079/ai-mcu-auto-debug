# AI Agent 使用指南

本文件为兼容旧链接而保留。主要公开指南请阅读 [Agent 快速接入](AGENT_QUICKSTART.md)。

## 最小安全流程

```powershell
ai-mcu-debug agent-bootstrap --project . --client generic-json
ai-mcu-debug workflow-plan --project . --chip <chip>
ai-mcu-debug doc-intake --project . --chip <chip>
ai-mcu-debug ai-debug --mode dry-run --workspace-config .embeddedskills/config.json
```

所有影响硬件的操作均需显式授权：没有用户针对当前板卡和操作的明确批准，不烧录、不修复、不强制写入，也不并行运行硬件调试会话。
