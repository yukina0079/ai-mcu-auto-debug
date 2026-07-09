# AI MCU Auto Debug

[![License: MIT](https://img.shields.io/badge/License-MIT-green.svg)](LICENSE)
[![Python](https://img.shields.io/badge/Python-3.10%2B-blue.svg)](pyproject.toml)

AI MCU Auto Debug is a low-coupling automation layer for MCU bring-up and debugging. It stitches together existing embedded tools instead of replacing them: CMake/GCC or vendor build commands, OpenOCD/J-Link/pyOCD/probe-rs style debug servers, CMSIS-SVD and user-provided vendor documents, and a Codex skill or MCP client for orchestration.

AI MCU Auto Debug 是一套低耦合 MCU 上板与调试自动化框架。它不替代现有嵌入式工具，而是把 CMake/GCC 或厂商构建命令、OpenOCD/J-Link/pyOCD/probe-rs 风格调试服务、CMSIS-SVD、用户提供的芯片资料，以及 Codex skill / MCP client 串起来。

This public release focuses on the non-vision loop: prepare knowledge, build firmware, run safe debug actions, collect evidence, and iterate from reports. Camera/image-based board inspection is not shipped in this release.

当前公开版本聚焦非视觉闭环：准备知识库、构建固件、执行安全调试动作、收集证据，并根据报告迭代。摄像头/图像识别开发板状态的能力暂未包含在此版本中。

## 3-Minute Setup / 3 分钟部署

```powershell
git clone https://github.com/yukina0079/ai-mcu-auto-debug.git
cd ai-mcu-auto-debug
python -m venv .venv
.\.venv\Scripts\Activate.ps1
python -m pip install -e .
ai-mcu-debug doctor
ai-mcu-debug capability-audit --project .
ai-mcu-debug skill-bootstrap --project . --dry-run
```

Expected result / 预期结果：

- `doctor` reports Python-side tools and any installed embedded backends.
- `doctor` 会报告 Python 侧工具以及已安装的嵌入式后端。
- `capability-audit` reports `status=nonvision_ready`.
- `capability-audit` 应返回 `status=nonvision_ready`。
- `skill-bootstrap --dry-run` reports MCP server discovery without touching hardware.
- `skill-bootstrap --dry-run` 会检查 MCP server 工具发现能力，不触碰硬件。

## Optional Embedded Tool Setup / 可选嵌入式工具配置

Install these only when you want real hardware debug on Windows.

只有需要连接真实硬件调试时，才需要安装这些 Windows 工具：

```powershell
winget install xpack-dev-tools.openocd
winget install Arm.GnuArmEmbeddedToolchain
python -m pip install pyocd
ai-mcu-debug doctor --debug-backend openocd-gdb
ai-mcu-debug probe-scan
```

J-Link users can install SEGGER J-Link separately; Keil and PlatformIO flows are supported through command adapters when those tools are already installed.

J-Link 用户可单独安装 SEGGER J-Link；Keil 和 PlatformIO 在本机已安装时可通过 command adapter 接入。

## What Works / 当前能力

- Core debug automation: reset/halt, core registers, memory reads, breakpoints, single-step, debug sequences, and read-only hardware identity checks.
- 核心调试自动化：reset/halt、核心寄存器读取、内存读取、断点、单步、调试序列、只读硬件 ID 检查。
- Build and test loop: build, smoke test, runtime log collection, explicit repair commands, and `ai-debug` orchestration.
- 构建与测试闭环：构建、smoke test、运行日志采集、显式修复命令，以及 `ai-debug` 编排。
- Knowledge guard: build an `mcu_context.json` from SVD, linker/startup files, and user-provided datasheets/reference manuals/errata; anti-hallucination checks keep unknown addresses blocked.
- 知识库防幻觉：根据 SVD、linker/startup 文件和用户提供的 datasheet/reference manual/errata 生成 `mcu_context.json`；未知地址默认阻断。
- User document intake: the tool asks for missing MCU documents or a document Git repository. It does not run web search or guess datasheet URLs by default.
- 用户资料导入：工具会向用户索要缺失的 MCU 资料或资料 Git 仓库；默认不联网搜索、不猜 datasheet URL。
- Safe workflow routing: `workflow-plan` explains the next safe calls; `workflow-run` can execute allowed non-dangerous steps and blocks flash, repair, force, vision, and web search by default.
- 安全工作流路由：`workflow-plan` 给出下一步安全调用；`workflow-run` 可执行允许的非危险步骤，并默认阻断 flash、repair、force、vision、web search。
- MCP integration: `mcp-server` exposes high-level tools with explicit input schemas for Codex, Claude Desktop, or a generic MCP host.
- MCP 集成：`mcp-server` 向 Codex、Claude Desktop 或通用 MCP host 暴露带明确 input schema 的高层工具。
- Skill deployment: `skill-bootstrap` installs or previews the bundled Codex skill, generates MCP config snippets, runs an MCP smoke test, and performs capability audit in one report.
- Skill 部署：`skill-bootstrap` 可安装或预演内置 Codex skill，生成 MCP 配置片段，运行 MCP smoke test，并输出能力审计报告。
- Handoff and replay: `export-handoff` packages replayable evidence; `replay-handoff` validates or safely executes non-hardware replay commands such as `workflow-run --no-hardware`.
- 交接与回放：`export-handoff` 打包可回放证据；`replay-handoff` 校验或安全执行非硬件回放命令，例如 `workflow-run --no-hardware`。

## Verify The Project / 验证项目

Run the test suite and environment checks.

运行测试套件和环境检查：

```powershell
python -m pytest
ai-mcu-debug doctor
ai-mcu-debug mcp-smoke --project .
ai-mcu-debug capability-audit --project .
```

For a quick install/deployment preview / 快速预览安装与部署：

```powershell
ai-mcu-debug skill-bootstrap --project . --dry-run
```

## Quick Start / 快速开始

Run the local readiness checks / 运行本地就绪检查：

```powershell
ai-mcu-debug doctor
ai-mcu-debug probe-scan
ai-mcu-debug capability-audit --project .
ai-mcu-debug skill-bootstrap --project . --dry-run
```

Install the bundled Codex skill and verify the MCP server.

安装内置 Codex skill 并验证 MCP server：

```powershell
ai-mcu-debug install-skill --dry-run
ai-mcu-debug install-skill
ai-mcu-debug mcp-config --client codex --project .
ai-mcu-debug mcp-smoke --project .
```

Prepare a board workspace. Replace the placeholders with files supplied by you or your MCU document repository.

准备开发板 workspace。请把占位符替换为你提供的文件，或来自你自己的 MCU 资料仓库的文件：

```powershell
ai-mcu-debug resolve-chip --project . --chip STM32F103RCT6
ai-mcu-debug doc-intake --project . --chip STM32F103RCT6
ai-mcu-debug prepare-mcu --project . --chip STM32F103RCT6 --svd <device.svd> --linker <linker.ld> --startup <startup.c> --doc datasheet=<datasheet.pdf-or-md> --doc reference_manual=<reference.pdf-or-md> --doc errata=<errata.pdf-or-md> --output examples/mcu_context.json
ai-mcu-debug check-context --context examples/mcu_context.json
ai-mcu-debug init-workspace --project . --chip STM32F103RCT6 --context examples/mcu_context.json
ai-mcu-debug workspace-status
```

Run the non-vision debug loop / 运行非视觉调试闭环：

```powershell
ai-mcu-debug build --config .embeddedskills/build.json
ai-mcu-debug smoke-test --config .embeddedskills/build.json
ai-mcu-debug runtime-log --config .embeddedskills/build.json
ai-mcu-debug ai-debug --mode dry-run --workspace-config .embeddedskills/config.json
ai-mcu-debug ai-debug --mode read-only --workspace-config .embeddedskills/config.json
```

Hardware-affecting actions stay explicit / 涉及硬件写入或烧录的动作必须显式开启：

```powershell
ai-mcu-debug ai-debug --mode run --allow-flash --workspace-config .embeddedskills/config.json
ai-mcu-debug ai-debug --mode run --allow-flash --allow-repair --workspace-config .embeddedskills/config.json
```

Do not use `--allow-flash`, `--allow-repair`, or `--force` unless the current board and operation are intentionally selected.

除非你明确确认当前板卡和操作目标，否则不要使用 `--allow-flash`、`--allow-repair` 或 `--force`。

Hardware debug sessions are single-owner per board. Do not launch parallel OpenOCD/GDB/debug commands against the same target; batch reads in one `debug-sequence` or run individual commands sequentially.

同一块板子的硬件调试会话是独占资源。不要对同一目标并行启动 OpenOCD/GDB/debug 命令；多个读取动作应放进一个 `debug-sequence`，或按顺序逐条执行。

## MCP Server / MCP 服务

Start the stdio server directly / 直接启动 stdio server：

```powershell
ai-mcu-debug-mcp
```

Or generate a client snippet / 或生成客户端配置片段：

```powershell
ai-mcu-debug mcp-config --client codex --project .
ai-mcu-debug mcp-config --client claude-desktop --project .
ai-mcu-debug mcp-config --client generic-json --project .
```

The MCP surface exposes high-level tools for environment checks, probe scan, document intake, context preparation, build/smoke/runtime-log, safe workflow execution, `ai-debug`, guarded debug operations, handoff export/replay, skill deployment, and capability audit. Standalone flash remains intentionally outside MCP; use `run_ai_debug` with explicit `allow_flash` instead.

MCP 暴露环境检查、探针扫描、资料导入、context 准备、build/smoke/runtime-log、安全工作流执行、`ai-debug`、受保护调试操作、handoff 导出/回放、skill 部署和 capability audit 等高层工具。独立 flash 工具不会直接暴露在 MCP 中；需要烧录时应通过 `run_ai_debug` 并显式设置 `allow_flash`。

## Document Repositories / MCU 资料仓库

If you maintain MCU documents in Git, sync and validate them before use.

如果你用 Git 管理 MCU 资料，请先同步并校验：

```powershell
ai-mcu-debug doc-repo-sync --url <user-provided-repo-url> --local-path knowledge_repos/<name>
ai-mcu-debug locate-docs --project . --chip STM32F103RCT6 --doc-repo knowledge_repos/<name>
ai-mcu-debug manifest-lint --manifest knowledge_repos/<name>/vendors/st/stm32f1/STM32F103RCT6/manifest.json --chip STM32F103RCT6
```

Every trusted document still needs exact chip aliases, source metadata, hashes, and context evidence. A filename alone is not treated as proof.

每份可信资料都需要精确芯片别名、来源元数据、hash 和 context 证据。文件名本身不能作为可信证据。

## Useful Reports / 常用报告

```powershell
ai-mcu-debug accept-nonvision --project . --chip STM32F103RCT6 --context examples/mcu_context.json
ai-mcu-debug export-handoff --output debug_runs/handoff.zip --zip
ai-mcu-debug replay-handoff --manifest debug_runs/handoff/handoff_manifest.json
```

`accept-nonvision` runs setup, `ai-debug --mode dry-run`, handoff export, and replay policy validation without flash, repair, or camera/vision.

`accept-nonvision` 会执行 setup、`ai-debug --mode dry-run`、handoff 导出和 replay 策略校验，不执行 flash、repair，也不使用摄像头/视觉能力。

## Repository Hygiene / 仓库卫生

Generated build outputs, debug runs, local `.embeddedskills/` state, downloaded MCU documents, heavyweight official-context extracts, and local planning notes are intentionally ignored. Reusable MCU materials should live in user-provided document repositories or explicit local files.

生成的构建产物、调试报告、本地 `.embeddedskills/` 状态、下载的 MCU 文档、大型官方 context 提取物和本地计划笔记都默认忽略。可复用 MCU 资料应放在用户提供的资料仓库或明确的本地文件中。

## License / 许可证

This project is open source under the [MIT License](LICENSE).

本项目使用 [MIT License](LICENSE) 开源。
