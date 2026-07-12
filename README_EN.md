# AI MCU Auto Debug

[中文](README.md) | [English](README_EN.md)

[![License: MIT](https://img.shields.io/badge/License-MIT-green.svg)](LICENSE)
[![Python](https://img.shields.io/badge/Python-3.10%2B-blue.svg)](pyproject.toml)

![AI MCU Auto Debug overview](docs/assets/hero-ai-mcu-debug.png)

AI MCU Auto Debug is an open-source, low-coupling MCU automation toolchain for AI agents. It connects code generation, build, flash, live debugging, UART observation, camera images, knowledge grounding, and evidence reports through CLI, Python API, MCP tools, and a bundled skill.

## Quick Start

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

Recommended first prompt:

```text
Use this repository as an AI MCU automation toolchain. Run agent-bootstrap first, then use workflow-plan before hardware actions. Do not flash, repair, force writes, or run parallel hardware debug sessions unless I explicitly approve the current board and operation. Ask me for missing MCU documents instead of guessing URLs.
```

## Capabilities

![Closed-loop workflow](docs/assets/closed-loop-workflow.png)

- Natural-language code, build, debug, observe, report, and repair loop.
- Reset/halt, breakpoints, single-step, core registers, guarded peripheral access, and memory operations.
- Anti-hallucination grounding from user-provided SVD, linker/startup, datasheet, reference manual, and errata files.
- UART/RTT/SWO runtime evidence and direct pyserial capture.
- Camera capture returned as standard MCP image content for vision-capable agents.
- Portable MCP setup for Codex, Claude, OpenCode, Trae, Qoder, and generic clients.

## Agent Integration

![Agent compatibility](docs/assets/agent-toolchain-compatibility.png)

```powershell
ai-mcu-debug agent-bootstrap --client codex --project .
ai-mcu-debug agent-bootstrap --client claude-code --project .
ai-mcu-debug agent-bootstrap --client opencode --project .
ai-mcu-debug agent-bootstrap --client trae --project .
ai-mcu-debug agent-bootstrap --client qoder --project .
ai-mcu-debug mcp-config --client generic-json --project .
ai-mcu-debug mcp-smoke --project .
```

## Verified Hardware

| Board | Status | Verified path | Evidence |
|---|---|---|---|
| STM32F103RCT6 generic board | verified | DAPLink/CMSIS-DAP + OpenOCD + GDB | Identity, build, verified flash, reset/halt, core registers, RAM read, source breakpoint, single-step, and resume. NRST was not connected on the verified bench. |
| ESP32-C3 SuperMini | verified debug link | Built-in USB Serial/JTAG + Espressif OpenOCD + RISC-V GDB | Chip/Flash identity, registers, memory, hardware breakpoint, single-step, resume, and serial log. |

## Camera Observation

```powershell
python -m pip install -e ".[vision]"
ai-mcu-debug camera-scan --allow-camera
ai-mcu-debug camera-capture --camera-index 0 --image-output debug_runs/vision/latest.jpg --allow-camera
```

MCP tools `camera_scan`, `capture_board_image`, and `analyze_board_image` return JSON evidence and standard MCP image content. Camera access is opt-in for every call, and generated images under `debug_runs/` are ignored by Git.

## Safety

- One board/debug probe is an exclusive resource. Never run parallel hardware debug sessions against it.
- Flash, repair, force, register/memory writes, option bytes, and clock/reset writes require explicit approval.
- Missing MCU documents are requested from the user; datasheet URLs are not guessed.
- Unknown addresses are blocked by default, as are unsupported register writes.

See the [Chinese documentation index](README.md#golden-suite-与公开证据) for detailed workflows, reports, verified boards, and examples.

## License

Open source under the [MIT License](LICENSE).
