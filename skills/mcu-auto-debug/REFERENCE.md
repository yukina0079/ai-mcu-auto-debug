# MCU Auto Debug Reference

## Current Stable Commands

```text
python -m ai_mcu_debug.cli doctor
python -m ai_mcu_debug.cli doctor --debug-backend openocd-gdb --build-backend cmake
python -m ai_mcu_debug.cli doctor --debug-backend probe-rs-gdb --build-backend command
python -m ai_mcu_debug.cli skill-bootstrap --project . --dry-run
python -m ai_mcu_debug.cli install-skill --dry-run
python -m ai_mcu_debug.cli install-skill
python -m ai_mcu_debug.cli mcp-config --client codex --project .
python -m ai_mcu_debug.cli mcp-smoke --project .
python -m ai_mcu_debug.cli workflow-plan --project . --chip <chip>
python -m ai_mcu_debug.cli workflow-run --project . --chip <chip>
python -m ai_mcu_debug.cli capability-audit --project .
python -m ai_mcu_debug.cli probe-scan
python -m ai_mcu_debug.cli init-workspace --project . --chip <chip> --context examples/mcu_context.json
python -m ai_mcu_debug.cli setup-project --project . --chip <chip> --context examples/mcu_context.json
python -m ai_mcu_debug.cli accept-nonvision --project . --chip <chip> --context examples/mcu_context.json
python -m ai_mcu_debug.cli init-workspace --project . --chip <chip> --context examples/mcu_context.json --debug-backend pyocd-gdb
python -m ai_mcu_debug.cli init-workspace --project . --chip <chip> --context examples/mcu_context.json --debug-backend jlink-gdb
python -m ai_mcu_debug.cli init-workspace --project . --chip <chip> --context examples/mcu_context.json --debug-backend probe-rs-gdb
python -m ai_mcu_debug.cli init-workspace --project . --context examples/mcu_context.json --build-backend platformio --pio-env <env>
python -m ai_mcu_debug.cli init-workspace --project . --context examples/mcu_context.json --build-backend keil --keil-project <app.uvprojx> --keil-target <target>
python -m ai_mcu_debug.cli workspace-status
python -m ai_mcu_debug.cli validate-target --target <target.json> --scan-probes
python -m ai_mcu_debug.cli hardware-id --target <target.json> --chip <chip>
python -m ai_mcu_debug.cli connection-diagnose --target <target.json> --report-dir debug_runs/connection_diagnostics
python scripts/first_stage_acceptance.py --skip-ai-debug
python scripts/first_stage_acceptance.py --report-dir debug_runs/first_stage_acceptance
python -m ai_mcu_debug.cli build --config examples/build.cmake.json
python -m ai_mcu_debug.cli smoke-test --config examples/build.cmake.json
python -m ai_mcu_debug.cli runtime-log --config examples/build.cmake.json
python -m ai_mcu_debug.cli repair-build --config examples/build.cmake.codex-repair.json
python -m ai_mcu_debug.cli resolve-chip --project . --chip <chip>
python -m ai_mcu_debug.cli doc-intake --project . --chip <chip>
python -m ai_mcu_debug.cli mcu-profile --chip <chip>
python -m ai_mcu_debug.cli manifest-lint --manifest <manifest.json> --chip <chip>
python -m ai_mcu_debug.cli locate-docs --chip <chip> --project .
python -m ai_mcu_debug.cli doc-repo-sync --url <user-provided-repo-url> --local-path knowledge_repos/<name>
python -m ai_mcu_debug.cli fetch-docs --chip <chip> --manifest knowledge_cache/<vendor>/<chip>/manifest.json --url datasheet=<user-provided-url-or-file>
python -m ai_mcu_debug.cli ingest-docs --manifest knowledge_cache/<vendor>/<chip>/manifest.json --svd <device.svd> --linker <linker.ld> --startup <startup.c> --output examples/mcu_context.json
python -m ai_mcu_debug.cli prepare-mcu --project . --chip <chip> --svd <device.svd> --linker <linker.ld> --startup <startup.c> --doc datasheet=<datasheet.pdf-or-md> --doc reference_manual=<reference.pdf-or-md> --doc errata=<errata.pdf-or-md> --output examples/mcu_context.json
python -m ai_mcu_debug.cli check-context --context examples/mcu_context.json
python -m ai_mcu_debug.cli build-mcu-context --chip <chip> --svd <device.svd> --output examples/mcu_context.json
python -m ai_mcu_debug.cli knowledge-query --context examples/mcu_context.json --query "<query>" --mode vector
python -m ai_mcu_debug.cli explain-register --context examples/mcu_context.json --register <register-or-address>
python -m ai_mcu_debug.cli validate-register-write --context examples/mcu_context.json --register <register> --value <value>
python -m ai_mcu_debug.cli validate-address-write --context examples/mcu_context.json --address <address> --length <bytes>
python -m ai_mcu_debug.cli debug-op --target <target.json> --context examples/mcu_context.json <operation>
python -m ai_mcu_debug.cli debug-sequence --target <target.json> --sequence <sequence.json>
python -m ai_mcu_debug.cli analyze-debug-report --context examples/mcu_context.json --report <report.json> --output <knowledge-report.json>
python -m ai_mcu_debug.cli ai-debug --mode dry-run --project . --context examples/mcu_context.json --build-config <build.json>
python -m ai_mcu_debug.cli ai-debug --mode dry-run --workspace-config .embeddedskills/config.json
python -m ai_mcu_debug.cli ai-debug --mode read-only --project . --context examples/mcu_context.json --build-config <build.json> --target <target.json> --task <task.json>
python -m ai_mcu_debug.cli export-handoff --output debug_runs/handoff.zip --zip
python -m ai_mcu_debug.cli replay-handoff --manifest debug_runs/handoff/handoff_manifest.json
python -m ai_mcu_debug.cli mcp-server
```

After `init-workspace`, the shorter form is valid because `ai-debug` reads `.embeddedskills/config.json`:

```text
python -m ai_mcu_debug.cli ai-debug --mode dry-run
python -m ai_mcu_debug.cli ai-debug --mode read-only
```

`init-workspace` generates missing `.embeddedskills/build.json`, `.embeddedskills/debug.target.json`, and `.embeddedskills/debug_task.json` when it has enough local evidence. Provide explicit `--build-config`, `--target`, or `--task` only when the generated template is not appropriate.

## Hardware Debug Concurrency

Hardware debug access is exclusive per target board. Do not start parallel OpenOCD, pyOCD, J-Link, probe-rs, GDB, `debug-op`, `debug-sequence`, `hardware-id`, `connection-diagnose`, or `ai-debug` hardware sessions against the same board. These tools usually compete for the same USB probe, GDB server port, or target halt state; parallel reads can create false timeouts even when the board is healthy.

When several registers or memory addresses must be sampled, prefer one of these patterns:

- Put the reads in one `debug-sequence` so a single GDB connection performs them in order.
- Use one `ai-debug --mode read-only` session with a task file that lists all required observations.
- If using individual `debug-op` calls, run them sequentially and wait for each process to exit before starting the next one.

For first-time onboarding, prefer `setup-project`. It runs `doctor`, optional `probe-scan`, document intake planning, context preparation when required documents are present, and `init-workspace` template generation in one deterministic report. If documents are missing, it stops at `status=awaiting_user_documents` with `document_intake.required_requests[]`.

Use `mcu-profile` before onboarding a new chip family. It returns deterministic required document groups, recommended debug backends, a `vendors/<vendor>/<family>/<chip>/manifest.json` layout, and a manifest skeleton with placeholders for user-provided source URLs and hashes. Use `manifest-lint` to validate a user document repo manifest before running `prepare-mcu`.

For CI-style or handoff-ready non-vision acceptance, run `accept-nonvision`. It executes `setup-project`, `ai-debug --mode dry-run`, `export-handoff`, and handoff replay validation in sequence. Its policy always records `flash_allowed=false`, `repair_allowed=false`, `vision_allowed=false`, and `handoff_replay_execute=false`.

Use `--debug-backend pyocd-gdb` to generate a pyOCD GDB server target instead of the default OpenOCD target. The `ai-debug` workflow stays the same; only `.embeddedskills/debug.target.json` changes.

Use `--debug-backend jlink-gdb` to generate a J-Link GDB Server target when SEGGER tooling is installed. The generated target still uses the same `GdbRemoteAdapter` path as OpenOCD and pyOCD.

Use `--debug-backend probe-rs-gdb` only when the installed probe-rs workflow provides a GDB server compatible with `target remote localhost:3333`. Otherwise keep probe-rs as `flash_command` or `runtime_log_command` through a bounded wrapper script.

Use `--build-backend platformio`, `--build-backend keil`, or `--build-backend command` to generate thin command-based build templates. These backends all keep the same `BuildAdapter` interface; tool-specific details stay in `build.json` commands and `extra`, not in core logic.

When a Cortex-M target resets into ROM/system memory or the reset line cannot be observed, add `launch_from_vector_table` to the debug task. The runner reads the initial MSP and Reset_Handler from the Flash vector table, sets `$sp` and `$pc`, then resumes to the configured breakpoint:

```json
{
  "reset_before_run": true,
  "launch_from_vector_table": "0x08000000"
}
```

## Explicitly Authorized Run Command

```text
python -m ai_mcu_debug.cli ai-debug --mode run --allow-flash --project . --context examples/mcu_context.json --build-config <build.json> --target <target.json> --task <task.json>
python -m ai_mcu_debug.cli ai-debug --mode run --allow-flash --allow-repair --project . --context examples/mcu_context.json --build-config <build.json> --target <target.json> --task <task.json>
```

Never add `--allow-flash`, `--allow-repair`, or `--force` unless the user has explicitly approved that operation for the current board.

## User-Provided Document Policy

1. Run `doc-intake` first to generate a structured checklist of exactly which user files, URLs, or repos are required.
2. Run `locate-docs` to reuse explicit user inputs, local project files, and `knowledge_cache`.
3. If a user provides a document repo URL, run `doc-repo-sync`; otherwise do not choose a repo or search for one.
4. If required sources are missing, ask the user for the exact item named in `required_requests[]`.
5. Convert user-provided URLs or local files with `fetch-docs`, `ingest-docs`, or `prepare-mcu`; record hashes and paths as evidence.
6. Prefer exact part number datasheets, family reference manuals, errata, and CMSIS-SVD/CMSIS-Pack files supplied by the user or already present in the project.
7. Do not run web search, infer vendor URLs, or fetch guessed datasheets as the default AI workflow.
8. Do not paraphrase register semantics from memory. Use `mcu_context`, SVD, extracted document text, or mark the item `uncertain`.
9. Do not treat agent/skill/project process files such as `SKILL.md`, `REFERENCE.md`, `AGENTS.md`, generated debug records, or generated reports as MCU datasheets/reference manuals.
10. For broad workspace scans, ignore generated artifacts such as `debug_runs`, `.embeddedskills`, installed skill docs, generated `mcu_context` reports, and cloned `knowledge_repos` when resolving the chip identity.

## MCU Document Git Repository

Use a separate repository for reusable MCU materials only when the user provides the repo URL or local path:

```text
python -m ai_mcu_debug.cli doc-repo-sync --url https://github.com/<owner>/mcu-knowledge-base.git --local-path knowledge_repos/mcu-knowledge-base
python -m ai_mcu_debug.cli locate-docs --project . --chip STM32F103RCT6 --doc-repo knowledge_repos/mcu-knowledge-base
python -m ai_mcu_debug.cli prepare-mcu --project . --chip STM32F103RCT6 --doc-repo knowledge_repos/mcu-knowledge-base --output examples/mcu_context.json
```

Recommended repo layout:

```text
vendors/<vendor>/<family>/<chip>/manifest.json
vendors/<vendor>/<family>/<chip>/documents/*.md
vendors/<vendor>/<family>/<chip>/svd/*.svd
vendors/<vendor>/<family>/<chip>/linker/*.ld
```

Manifests should include `chip`, `aliases`, `vendor`, `family`, `documents[]`, `source_url`, `sha256`, `trust_level`, and `license_note`. Prefer URL/hash entries for large vendor PDFs; use Git LFS only when offline binary copies are intentionally required.

`locate-docs` returns structured `diagnostics[]` for document-repo problems. Important codes include `doc_repo_path_missing`, `manifest_missing`, `unsupported_manifest`, `chip_manifest_not_found`, `chip_alias_conflict`, `hash_mismatch`, and `ambiguous_document_selection`. Blocking diagnostics such as alias conflicts and strict doc-repo local hash mismatches stop `prepare-mcu` before a context can be generated.

For a fresh workspace fed by a project copy, chip name, and user-provided MCU document repo URL:

```text
python scripts/cross_workspace_acceptance.py --chip STM32F103RCT6 --doc-repo-url https://github.com/yukina0079/mcu-knowledge-base.git --doc-repo-only --skip-ai-debug
```

The current STM32F103RCT6 acceptance path verifies that the generated context uses the RCT6-specific linker and memory map: Flash 256 KiB and RAM 48 KiB.

## Handoff And Audit

Use `export-handoff` to package the non-vision evidence for another AI agent or engineer:

```text
python -m ai_mcu_debug.cli export-handoff --output debug_runs/handoff.zip --project . --report-dir debug_runs --zip
```

The package contains workspace config, `mcu_context`, JSON/JSONL/log reports, knowledge manifests, lightweight Markdown evidence, `audit_events.jsonl`, and replay commands. It intentionally excludes firmware binaries, large PDFs, pack files, generated build products, and older nested handoff packages. Unsafe output paths such as the project root are rejected.

Use `replay-handoff` to validate or safely execute the manifest replay commands:

```text
python -m ai_mcu_debug.cli replay-handoff --manifest debug_runs/handoff/handoff_manifest.json
python -m ai_mcu_debug.cli replay-handoff --manifest debug_runs/handoff/handoff_manifest.json --execute
```

The default is validation only. Execution is constrained to safe high-level CLI commands such as `workspace-status`, `doc-repo-sync`, `prepare-mcu`, `ai-debug --mode dry-run`, `doc-intake`, `mcu-profile`, `manifest-lint`, and `locate-docs`. Hardware-affecting commands and flags such as `flash`, `debug-op`, `accept-first-stage`, `--allow-flash`, `--allow-repair`, and `--force` are blocked.

Handoff replay also allows `workflow-run` only when `--no-hardware` is present. Exported handoff manifests include this non-hardware workflow command so another AI or CI job can safely re-drive setup, context checks, dry-run, and non-vision acceptance without touching target hardware.

`audit_events.jsonl` records deterministic events for document repo sync, document fetch, configure/build/flash/smoke/runtime-log commands, repair commands, debugger commands, and guard-blocked unsafe debug operations. Runs started through `ai-debug` add `run_id` and `step_id` metadata so one loop can be separated from unrelated manual commands.

## Runtime Logs

Runtime logs are configured as a thin command wrapper on the build adapter:

```json
{
  "runtime_log_command": ["python", "scripts/read_uart_once.py", "--port", "COM3", "--baud", "115200"]
}
```

The command may wrap UART, RTT, SWO, semihosting, or any existing log capture tool. `ai-debug --mode run` treats a failing runtime-log command as required evidence and can pass that failure to the repair adapter only when `--allow-repair` is explicitly set. Physical attach failures still stop in connection diagnostics instead of triggering code repair.

## MCP Server

The minimal stdio MCP server exposes only high-level safe tools:

```text
python -m ai_mcu_debug.cli mcp-server
```

Tools currently exposed: `workflow_plan`, `workflow_run`, `capability_audit`, `mcp_config`, `mcp_smoke`, `doctor`, `probe_scan`, `init_workspace`, `validate_target`, `connection_diagnose`, `resolve_chip`, `locate_documents`, `fetch_user_documents`, `ingest_documents`, `sync_document_repo`, `check_mcu_context`, `write_debug_record`, `build_firmware`, `smoke_test_firmware`, `collect_runtime_log`, `repair_build`, `install_skill`, `setup_project`, `accept_nonvision`, `mcu_profile`, `lint_mcu_manifest`, `prepare_mcu_context`, `plan_document_intake`, `run_ai_debug`, `debug_op_guarded`, `read_hardware_id`, `export_handoff`, `replay_handoff`, and `workspace_status`. The server delegates to the same API/CLI logic, so `allow_flash`, `allow_repair`, and `force` remain opt-in. `repair_build` is blocked unless `allow_repair=true`; standalone flash remains intentionally outside MCP and should go through `run_ai_debug` with explicit `allow_flash`.

`tools/list` publishes explicit JSON input schemas for every tool, including required fields, safe defaults, run-mode enums, debug operation enums, and policy-sensitive flags. `tools/call` validates incoming arguments against those schemas before dispatching, returning `status=invalid_arguments` for missing required fields, unexpected properties, type mismatches, or bad enum values. This keeps agent calls stable without moving safety policy out of the CLI/API layer.

Use the small environment tools directly when an agent needs to inspect or repair setup without running the full onboarding flow: `doctor` for tool availability, `probe_scan` for USB/PnP probe evidence, `init_workspace` for workspace-local defaults/templates, `validate_target` for probe/interface mismatches, and `connection_diagnose` for bounded non-flashing OpenOCD attach variants.

Use `workflow_plan` as the first read-only router when the next step is unclear. It inspects chip resolution, document intake, context readiness, and workspace status, then returns `recommended_tool_calls[]` or `user_requests[]` without modifying files, flashing, repairing, or using vision. Each recommended call includes structured arguments, `cli`/`cli_args` equivalents, and `safety` metadata for file writes, hardware touch, flash, repair, force, vision, and web-search policy.

Use `workflow_run` when those safe recommendations should be executed automatically. It loops through `workflow_plan`, dispatches supported safe calls, writes `workflow_run_report.json`, and stops for user document requests, policy-blocked actions, failures, or `max_steps`. It does not enable flash, repair, force, vision, or web search; use `--no-hardware` when even read-only target control should be skipped.

## Capability Audit

Use `capability-audit` to produce a deterministic static readiness report for the non-vision automation surface:

```text
python -m ai_mcu_debug.cli capability-audit --project .
python -m ai_mcu_debug.cli capability-audit --project . --output debug_runs/capability_audit/latest.json
```

The audit checks evidence for realtime debug, build/test/repair loops, knowledge guards, user document intake, safe workflow orchestration, handoff replay, skill deployment, and safety gates across CLI commands, public API functions, MCP tools, tests, docs, and special policy checks. Vision/camera support is marked postponed and non-blocking by default; pass `--include-vision` only when camera evidence should become a blocking requirement.

## Skill Installation

Use `skill-bootstrap` as the preferred deployment gate for the skill package and MCP wiring:

```text
python -m ai_mcu_debug.cli skill-bootstrap --project . --dry-run
python -m ai_mcu_debug.cli skill-bootstrap --project . --force --config-output debug_runs/skill_bootstrap/mcp.toml --report-output debug_runs/skill_bootstrap/bootstrap_report.json
```

It runs `install-skill`, `mcp-config`, `mcp-smoke`, and `capability-audit` in one JSON report. It never edits global client config, never touches target hardware, never flashes, and never runs repair. Use `--dry-run` to preview install/config output without writing files.

Use `install-skill` to sync the repository skill package into a local Codex skill directory:

```text
python -m ai_mcu_debug.cli install-skill --dry-run
python -m ai_mcu_debug.cli install-skill --force
python -m ai_mcu_debug.cli install-skill --destination <codex-home>/skills/mcu-auto-debug --force
```

The command copies the package from `skills/mcu-auto-debug` by default, records SHA-256 hashes for each file, and refuses to overwrite changed destination files unless `--force` is explicit. MCP exposes the same operation as `install_skill` for agent-driven deployment.

Use `mcp-config` to generate the client-side MCP server snippet without editing a global config file automatically:

```text
python -m ai_mcu_debug.cli mcp-config --client codex --project .
python -m ai_mcu_debug.cli mcp-config --client generic-json --project . --output debug_runs/mcp_config/ai_mcu_debug.json
python -m ai_mcu_debug.cli mcp-config --client claude-desktop --project .
python -m ai_mcu_debug.cli mcp-smoke --project .
```

The generated server runs `python -m ai_mcu_debug.cli mcp-server` with `cwd` set to the repository root. This keeps client setup separate from the skill package and lets Codex, Claude Desktop, CI, or another MCP host call the same safe tool surface.
`mcp-smoke` starts that server through stdio, sends `initialize` and `tools/list`, verifies core tool names, and exits. It does not touch hardware, flash, repair code, or edit any client config.

## User Document Import

When the user provides URLs or local files, cache and hash them before context generation:

```text
python -m ai_mcu_debug.cli fetch-docs --chip STM32F103RCT6 --manifest knowledge_cache/st/STM32F103RCT6/manifest.json --url datasheet=<user-provided-datasheet-url-or-file> --url reference_manual=<user-provided-reference-url-or-file> --url errata=<user-provided-errata-url-or-file> --url cmsis_pack=<user-provided-pack-url-or-file>
python -m ai_mcu_debug.cli ingest-docs --manifest knowledge_cache/st/STM32F103RCT6/manifest.json --chip STM32F103RCT6 --svd <device.svd> --linker <linker.ld> --startup <startup.c> --output examples/mcu_context.json
```

`fetch-docs` expands user-provided CMSIS-Pack files and records a matching `.svd` entry in the manifest when a suitable SVD is found. If required sources are absent, ask for official URLs or local files instead of guessing.

## Backend Selection

| Need | Preferred Backend | Notes |
|---|---|---|
| DAPLink/CMSIS-DAP + STM32 | OpenOCD GDB server | Use `interface/cmsis-dap.cfg`, `transport select swd`, and the chip family target cfg. |
| J-Link probe | J-Link GDB Server | Prefer when the installed SEGGER stack is available and the user wants SEGGER tooling. |
| Rust/probe-rs supported chips | probe-rs | Good for modern Cortex-M chips and RTT-centric workflows. |
| pyOCD-supported CMSIS-DAP chips | pyOCD GDB server | Good fallback for CMSIS-DAP diagnosis and DAPLink comparison. |
| CMake/GCC project | CMake adapter | Default for portable embedded GCC projects. |
| Generic scripts | Command adapter | Use when the project already has build/flash/test/log wrapper scripts. |
| Keil MDK project | Command adapter with Keil template | Use when `.uvprojx` is the source of truth; generated command calls `UV4.exe`. |
| PlatformIO project | Command adapter with PlatformIO template | Use when `platformio.ini` owns build/upload settings. |

## Hardware Identity

Use `hardware-id` for read-only silicon identity evidence once the probe can attach:

```text
python -m ai_mcu_debug.cli hardware-id --target .embeddedskills/debug.target.json --chip STM32F103RCT6 --report-dir debug_runs/hardware_identity
```

The command reads Cortex-M `CPUID` at `0xE000ED00` and STM32 `DBGMCU_IDCODE` at `0xE0042000` when available. It decodes the CPU core, STM32 device line/revision, writes `hardware_identity.json`, and reports whether the observed line/density is compatible with `--chip`. This is read-only evidence; it does not prove package marking, board variant, or errata status.

## Safe Connection Diagnosis

When a report shows `swd_target_dp_not_responding`, do not flash. Run:

```text
python -m ai_mcu_debug.cli connection-diagnose --target .embeddedskills/debug.target.json --report-dir debug_runs/connection_diagnostics
```

The command runs only bounded OpenOCD attach attempts: configured speed, lower SWD speeds, and connect-under-reset variants. It records `connection_diagnostics.json` with output tails, sampled reset state such as `nRESET`, probable causes, and next actions. It does not erase, flash, or write target memory/registers. If the board does not wire NRST to the probe, set `extra.nrst_connected=false` in the target file and do not interpret `nRESET=0` as proof that the target is physically held in reset.

For a repeatable first-stage hardware gate, run:

```text
python scripts/first_stage_acceptance.py --report-dir debug_runs/first_stage_acceptance
python scripts/first_stage_acceptance.py --report-dir debug_runs/first_stage_acceptance_after_flash_strict --connection-diagnostic-timeout-s 8
```

Use `--skip-ai-debug` when you only want workspace/probe/target static checks without opening a SWD debug session.

## STM32F103RCT6 Verified Hardware Gate

Current verified STM32F103RCT6 setup:

- Probe: DAPLink/CMSIS-DAP, `VID_C251&PID_F001`, SWD.
- OpenOCD target: `interface/cmsis-dap.cfg`, `target/stm32f1x.cfg`, `adapter speed 100`, startup command `init; reset halt`.
- NRST: not connected; target config records `extra.nrst_connected=false`.
- Debug launch: task records `launch_from_vector_table: 0x08000000`.
- Firmware: `build/stm32f103rct6_blinky/firmware.elf`, flashed and verified by OpenOCD before strict acceptance.
- Strict acceptance report: `debug_runs/first_stage_acceptance_after_flash_strict/ai_debug_report.json`.
- Final official-context acceptance report: `debug_runs/goal_audit_final_official_context/ai_debug_report.json`.
- Flash audit: `debug_runs/goal_audit_flash/flash_report.json` and `debug_runs/goal_audit_flash/openocd_flash.log`.
- AI repair-loop audit: `debug_runs/goal_audit_repair_loop/repair_build_report.json`.
- Evidence: PC `0x0800006a` in Flash, SP `0x2000bfe8` in RAM, xPSR `0x61000000`, breakpoint hit at `main.c:22`, single-step stopped, RAM read at `0x20000000` succeeded.

## STM32F103RCT6 Verified Source Example

```text
python -m ai_mcu_debug.cli fetch-docs --chip STM32F103RCT6 --manifest knowledge_cache/st/STM32F103RCT6/manifest.json --url datasheet=<user-provided-stm32f103rc-datasheet> --url reference_manual=<user-provided-rm0008> --url errata=<user-provided-es0340>
python -m ai_mcu_debug.cli ingest-docs --manifest knowledge_cache/st/STM32F103RCT6/manifest.json --chip STM32F103RCT6 --svd examples/svd/STM32F103_min.svd --linker examples/firmware/stm32f103_blinky/linker.stm32f103rct6.ld --startup examples/firmware/stm32f103_blinky/src/startup_stm32f103.c --output examples/mcu_context.stm32f103rct6.official.json
```

## Missing Document Policy

Required for safe register-level work:

- MCU identity with enough precision to select the correct device family.
- SVD or equivalent register map.
- Memory map from linker script, SVD, reference manual, or trusted project config.
- Datasheet or reference manual source.

Optional but must be recorded if absent:

- Errata.
- Board schematic or pinout notes.
- Application notes.

If required data is missing, return `missing_required_document` and ask the user for that item. If errata is missing, continue only with `errata_missing` in the context and avoid claiming no errata risk.

## Acceptance Gates

- Context gate: `mcu_context.json` has chip, memory regions, register index, document sources, risk rules, and debug notes.
- Toolchain gate: `doctor` finds target GDB and at least one debug backend.
- Probe gate: `probe-scan` detects a known probe for real hardware runs.
- Guard gate: unsafe register or memory writes are blocked before connecting to hardware.
- Memory-write gate: writes require `mcu_context`; only known RAM ranges or known memory-mapped registers may proceed without force, while Flash, unknown peripherals, and unknown addresses are blocked.
- Report gate: final report includes commands, evidence, uncertain items, and next actions.
- First-stage hardware gate: strict acceptance must reject zero/synthetic PC/SP/xPSR, require an actual `breakpoint-hit`, wait for the target to stop after single-step, and verify register/memory observations against `mcu_context`.
