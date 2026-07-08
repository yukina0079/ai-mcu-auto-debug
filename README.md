# AI MCU Auto Debug

AI MCU Auto Debug is a low-coupling automation layer for MCU bring-up and debugging. It stitches together existing embedded tools instead of replacing them: CMake/GCC or vendor build commands, OpenOCD/J-Link/pyOCD/probe-rs style debug servers, CMSIS-SVD and user-provided vendor documents, and a Codex skill or MCP client for orchestration.

The public release focuses on the non-vision loop: prepare knowledge, build firmware, run safe debug actions, collect evidence, and iterate from reports. Camera/image-based board inspection is not shipped in this release.

## What Works

- Core debug automation: reset/halt, core registers, memory reads, breakpoints, single-step, debug sequences, and read-only hardware identity checks.
- Build and test loop: build, smoke test, runtime log collection, explicit repair commands, and `ai-debug` orchestration.
- Knowledge guard: build an `mcu_context.json` from SVD, linker/startup files, and user-provided datasheets/reference manuals/errata; anti-hallucination checks keep unknown addresses blocked.
- User document intake: the tool asks for missing MCU documents or a document Git repository. It does not run web search or guess datasheet URLs by default.
- Safe workflow routing: `workflow-plan` explains the next safe calls; `workflow-run` can execute allowed non-dangerous steps and blocks flash, repair, force, vision, and web search by default.
- MCP integration: `mcp-server` exposes high-level tools with explicit input schemas for Codex, Claude Desktop, or a generic MCP host.
- Skill deployment: `skill-bootstrap` installs or previews the bundled Codex skill, generates MCP config snippets, runs an MCP smoke test, and performs capability audit in one report.
- Handoff and replay: `export-handoff` packages replayable evidence; `replay-handoff` validates or safely executes non-hardware replay commands such as `workflow-run --no-hardware`.

## Install

```powershell
git clone https://github.com/yukina0079/ai-mcu-auto-debug.git
cd ai-mcu-auto-debug
python -m venv .venv
.\.venv\Scripts\Activate.ps1
python -m pip install -e .
python -m pytest
```

External embedded tools are optional until you need a matching backend. Typical Windows setup:

```powershell
winget install xpack-dev-tools.openocd
winget install Arm.GnuArmEmbeddedToolchain
python -m pip install pyocd
```

J-Link users should install SEGGER J-Link separately and make sure the GDB server executable is available on `PATH`.

## Quick Start

Run the local readiness checks:

```powershell
ai-mcu-debug doctor
ai-mcu-debug probe-scan
ai-mcu-debug capability-audit --project .
ai-mcu-debug skill-bootstrap --project . --dry-run
```

Install the bundled Codex skill and verify the MCP server:

```powershell
ai-mcu-debug install-skill --dry-run
ai-mcu-debug install-skill
ai-mcu-debug mcp-config --client codex --project .
ai-mcu-debug mcp-smoke --project .
```

Prepare a board workspace. Replace the placeholders with files supplied by you or your MCU document repository:

```powershell
ai-mcu-debug resolve-chip --project . --chip STM32F103RCT6
ai-mcu-debug doc-intake --project . --chip STM32F103RCT6
ai-mcu-debug prepare-mcu --project . --chip STM32F103RCT6 --svd <device.svd> --linker <linker.ld> --startup <startup.c> --doc datasheet=<datasheet.pdf-or-md> --doc reference_manual=<reference.pdf-or-md> --doc errata=<errata.pdf-or-md> --output examples/mcu_context.json
ai-mcu-debug check-context --context examples/mcu_context.json
ai-mcu-debug init-workspace --project . --chip STM32F103RCT6 --context examples/mcu_context.json
ai-mcu-debug workspace-status
```

Run the non-vision debug loop:

```powershell
ai-mcu-debug build --config .embeddedskills/build.json
ai-mcu-debug smoke-test --config .embeddedskills/build.json
ai-mcu-debug runtime-log --config .embeddedskills/build.json
ai-mcu-debug ai-debug --mode dry-run --workspace-config .embeddedskills/config.json
ai-mcu-debug ai-debug --mode read-only --workspace-config .embeddedskills/config.json
```

Hardware-affecting actions stay explicit:

```powershell
ai-mcu-debug ai-debug --mode run --allow-flash --workspace-config .embeddedskills/config.json
ai-mcu-debug ai-debug --mode run --allow-flash --allow-repair --workspace-config .embeddedskills/config.json
```

Do not use `--allow-flash`, `--allow-repair`, or `--force` unless the current board and operation are intentionally selected.

## MCP Server

Start the stdio server directly:

```powershell
ai-mcu-debug-mcp
```

Or generate a client snippet:

```powershell
ai-mcu-debug mcp-config --client codex --project .
ai-mcu-debug mcp-config --client claude-desktop --project .
ai-mcu-debug mcp-config --client generic-json --project .
```

The MCP surface exposes high-level tools for environment checks, probe scan, document intake, context preparation, build/smoke/runtime-log, safe workflow execution, `ai-debug`, guarded debug operations, handoff export/replay, skill deployment, and capability audit. Standalone flash remains intentionally outside MCP; use `run_ai_debug` with explicit `allow_flash` instead.

## Document Repositories

If you maintain MCU documents in Git, sync and validate them before use:

```powershell
ai-mcu-debug doc-repo-sync --url <user-provided-repo-url> --local-path knowledge_repos/<name>
ai-mcu-debug locate-docs --project . --chip STM32F103RCT6 --doc-repo knowledge_repos/<name>
ai-mcu-debug manifest-lint --manifest knowledge_repos/<name>/vendors/st/stm32f1/STM32F103RCT6/manifest.json --chip STM32F103RCT6
```

Every trusted document still needs exact chip aliases, source metadata, hashes, and context evidence. A filename alone is not treated as proof.

## Useful Reports

```powershell
ai-mcu-debug accept-nonvision --project . --chip STM32F103RCT6 --context examples/mcu_context.json
ai-mcu-debug export-handoff --output debug_runs/handoff.zip --zip
ai-mcu-debug replay-handoff --manifest debug_runs/handoff/handoff_manifest.json
```

`accept-nonvision` runs setup, `ai-debug --mode dry-run`, handoff export, and replay policy validation without flash, repair, or camera/vision.

## Repository Hygiene

Generated build outputs, debug runs, local `.embeddedskills/` state, downloaded MCU documents, heavyweight official-context extracts, and local planning notes are intentionally ignored. Reusable MCU materials should live in user-provided document repositories or explicit local files.
