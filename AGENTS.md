# Agent Instructions

- Use UTF-8 for all source code and text files. Prefer UTF-8 without BOM when the toolchain supports it.
- When running PowerShell commands, assume UTF-8 console input/output.
- Treat one MCU board/debug probe as an exclusive resource. Do not run parallel OpenOCD/GDB/pyOCD/J-Link/probe-rs/debug sessions against the same target.
- Start with `ai-mcu-debug agent-bootstrap --project . --client generic-json` when another AI agent only has the repository URL.
