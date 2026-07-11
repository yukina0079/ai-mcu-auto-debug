---
name: mcu-auto-debug
description: Automates MCU project setup, code/build/test/debug loops, register and memory inspection, user-provided MCU document intake, UART observation, evidence reports, and safe MCP/CLI handoff for AI coding agents. Use when the user mentions MCU, embedded debug, datasheet, SVD, registers, memory reads/writes, flashing, OpenOCD, pyOCD, J-Link, probe-rs, DAPLink, ST-Link, UART logs, or AI-driven firmware debugging.
---

# MCU Auto Debug

## Core Rule

Use deterministic tools for hardware, build, document, serial log, register, and memory work. Do not invent MCU register meanings, memory maps, errata, probe state, or datasheet facts. If evidence is missing, return `uncertain` or ask the user for the exact missing document or hardware detail.

## First Commands

Run the portable non-hardware bootstrap before touching a board:

```text
python -m ai_mcu_debug.cli agent-bootstrap --project . --client generic-json
python -m ai_mcu_debug.cli doctor
python -m ai_mcu_debug.cli capability-audit --project .
python -m ai_mcu_debug.cli mcp-smoke --project .
python -m ai_mcu_debug.cli workflow-plan --project . --chip <chip>
```

Use `skill-bootstrap` only when installing/updating the local skill or generating client MCP snippets:

```text
python -m ai_mcu_debug.cli skill-bootstrap --project . --dry-run
python -m ai_mcu_debug.cli mcp-config --client codex --project .
python -m ai_mcu_debug.cli mcp-config --client claude-desktop --project .
python -m ai_mcu_debug.cli mcp-config --client generic-json --project .
python -m ai_mcu_debug.cli install-skill --dry-run
python -m ai_mcu_debug.cli install-skill --force
```

## Workflow

1. Identify the MCU from explicit user input, project files, startup files, linker scripts, SVD metadata, debug target configs, or read-only hardware identity evidence.
2. Run `workflow-plan` before hardware actions; follow `recommended_tool_calls[]` or `user_requests[]` instead of guessing.
3. If required documents are missing, ask only for the item named by `doc-intake` or `setup-project.document_intake.required_requests[]`.
4. Do not run web search or infer datasheet URLs by default. Use user-provided local files, official URLs, or a user-provided document repository.
5. Convert evidence into `mcu_context.json` with `prepare-mcu`, `fetch-docs` + `ingest-docs`, or MCP `prepare_mcu_context`.
6. Run `check-context` before relying on register names, memory maps, or errata.
7. Build and smoke test through the configured build adapter.
8. Use `serial-log`, `runtime-log`, or MCP `collect_serial_log` for UART observation when a serial instrument exists.
9. Run `ai-debug --mode dry-run` before `ai-debug --mode read-only`.
10. Export evidence with `export-handoff` when another AI or engineer needs to replay the work.

## ESP32-C3 / ESP-IDF

When the target is ESP32-C3 or an ESP32-C3 SuperMini:

1. Use `doctor --debug-backend esp-idf-openocd-gdb --build-backend esp-idf`; the tool discovers EIM/VS Code installations from `eim_idf.json` and does not require global PATH changes.
2. Use the ESP-IDF activation script, Espressif OpenOCD, `board/esp32c3-builtin.cfg`, and `riscv32-esp-elf-gdb`. Do not use generic xPack OpenOCD for the built-in USB Serial/JTAG interface.
3. Treat `VID_303A&PID_1001` as one exclusive instrument. Do not run serial logging, esptool, OpenOCD, or GDB against it in parallel.
4. On Windows, the JTAG `MI_02` interface must use the Espressif/libwdi WinUSB driver. `LIBUSB_ERROR_NOT_FOUND` means the driver package or binding is not ready.
5. Use RISC-V registers such as `pc`, `sp`, `ra`, and `a0`; do not request Cortex-M-only `lr`, `xpsr`, or vector-table launch behavior.
6. Keep ESP32-C3 knowledge separate from STM32 examples. If intake finds another chip family, stop and ask for ESP32-C3 SVD/TRM/linker evidence instead of generating context.

## Safety Gates

- Hardware debug sessions are single-owner per board. Do not run OpenOCD, GDB, pyOCD, J-Link, probe-rs, `debug-op`, `debug-sequence`, `hardware-id`, `connection-diagnose`, or `ai-debug` in parallel against the same target.
- Batch multiple register or memory reads into one `debug-sequence` or one `ai-debug --mode read-only` task.
- Core registers may be read through the debugger; peripheral register meaning must come from `mcu_context`.
- Register writes and memory writes require context validation and explicit user approval for the current board.
- Flash, option bytes, clock/reset-control writes, code repair, `--force`, and hardware replay require explicit approval.
- Missing errata must be recorded as `errata_missing`, not treated as proof of no risk.

## Useful Commands

```text
python -m ai_mcu_debug.cli resolve-chip --project . --chip <chip>
python -m ai_mcu_debug.cli doc-intake --project . --chip <chip>
python -m ai_mcu_debug.cli prepare-mcu --project . --chip <chip> --svd <device.svd> --linker <linker.ld> --startup <startup.c> --doc datasheet=<datasheet.pdf-or-md> --doc reference_manual=<reference.pdf-or-md> --doc errata=<errata.pdf-or-md> --output examples/mcu_context.json
python -m ai_mcu_debug.cli init-workspace --project . --chip <chip> --context examples/mcu_context.json
python -m ai_mcu_debug.cli build --config .embeddedskills/build.json
python -m ai_mcu_debug.cli smoke-test --config .embeddedskills/build.json
python -m ai_mcu_debug.cli serial-log --port <port> --baud 115200 --duration-s 5
python -m ai_mcu_debug.cli ai-debug --mode dry-run --workspace-config .embeddedskills/config.json
python -m ai_mcu_debug.cli ai-debug --mode read-only --workspace-config .embeddedskills/config.json
python -m ai_mcu_debug.cli export-handoff --output debug_runs/handoff.zip --zip
python -m ai_mcu_debug.cli doctor --debug-backend esp-idf-openocd-gdb --build-backend esp-idf
python -m ai_mcu_debug.cli init-workspace --output-dir .embeddedskills-esp32c3 --project examples/firmware/esp32c3_supermini_smoke --chip ESP32C3 --build-backend esp-idf --debug-backend esp-idf-openocd-gdb
```

## MCP Surface

The MCP server exposes high-level tools such as `agent_bootstrap`, `workflow_plan`, `workflow_run`, `prepare_mcu_context`, `check_mcu_context`, `build_firmware`, `smoke_test_firmware`, `collect_runtime_log`, `collect_serial_log`, `run_ai_debug`, `debug_op_guarded`, `read_hardware_id`, `export_handoff`, and `replay_handoff`. Standalone flash is intentionally not exposed as an MCP tool; use `run_ai_debug` with explicit `allow_flash=true` only after user approval.

See [REFERENCE.md](REFERENCE.md) for the extended command matrix and acceptance gates.
