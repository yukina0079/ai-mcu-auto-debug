---
name: mcu-auto-debug
description: Automates MCU/单片机 project bring-up, documentation preparation, build, flash, debug, evidence-backed analysis, and repair loops through the ai_mcu_debug CLI. Use when the user mentions MCU、单片机、嵌入式自动调试、datasheet、SVD、寄存器、内存读写、烧录、调试探针、DAPLink、ST-Link、J-Link、OpenOCD、pyOCD、probe-rs, or wants AI to configure and debug a board end to end.
---

# MCU Auto Debug

## Core Rule

Use deterministic tools for hardware, build, document, and register work. Do not invent MCU register meanings, memory maps, errata, probe state, or datasheet facts. If evidence is missing, return `uncertain` or ask the user for the exact missing document or hardware detail.

## Quick Start

From the project workspace:

```text
python -m ai_mcu_debug.cli doctor
python -m ai_mcu_debug.cli skill-bootstrap --project . --dry-run
python -m ai_mcu_debug.cli install-skill --dry-run
python -m ai_mcu_debug.cli install-skill
python -m ai_mcu_debug.cli mcp-config --client codex --project .
python -m ai_mcu_debug.cli mcp-smoke --project .
python -m ai_mcu_debug.cli workflow-plan --project . --chip <chip>
python -m ai_mcu_debug.cli workflow-run --project . --chip <chip>
python -m ai_mcu_debug.cli capability-audit --project .
python -m ai_mcu_debug.cli doctor --debug-backend <backend> --build-backend <backend>
python -m ai_mcu_debug.cli probe-scan
python -m ai_mcu_debug.cli resolve-chip --project .
python -m ai_mcu_debug.cli doc-intake --project . --chip <chip>
python -m ai_mcu_debug.cli mcu-profile --chip <chip>
python -m ai_mcu_debug.cli manifest-lint --manifest <manifest.json> --chip <chip>
python -m ai_mcu_debug.cli setup-project --project . --chip <chip> --context examples/mcu_context.json
python -m ai_mcu_debug.cli accept-nonvision --project . --chip <chip> --context examples/mcu_context.json
python -m ai_mcu_debug.cli locate-docs --project . --chip <chip>
python -m ai_mcu_debug.cli doc-repo-sync --url <user-provided-repo-url> --local-path knowledge_repos/<name>
python -m ai_mcu_debug.cli fetch-docs --chip <chip> --manifest knowledge_cache/user/<chip>/manifest.json --url datasheet=<user-file-or-url>
python -m ai_mcu_debug.cli ingest-docs --manifest knowledge_cache/user/<chip>/manifest.json --chip <chip> --svd <device.svd> --linker <linker.ld> --startup <startup.c> --output examples/mcu_context.json
python -m ai_mcu_debug.cli prepare-mcu --project . --chip <chip> --svd <device.svd> --linker <linker.ld> --startup <startup.c> --doc datasheet=<datasheet.pdf-or-md> --doc reference_manual=<reference.pdf-or-md> --doc errata=<errata.pdf-or-md> --output examples/mcu_context.json
python -m ai_mcu_debug.cli check-context --context examples/mcu_context.json
python -m ai_mcu_debug.cli init-workspace --project . --chip <chip> --context examples/mcu_context.json
python -m ai_mcu_debug.cli init-workspace --project . --chip <chip> --context examples/mcu_context.json --debug-backend <openocd-gdb|pyocd-gdb|jlink-gdb|probe-rs-gdb>
python -m ai_mcu_debug.cli init-workspace --project . --context examples/mcu_context.json --build-backend <cmake|command|platformio|keil>
python -m ai_mcu_debug.cli workspace-status
python -m ai_mcu_debug.cli build --config .embeddedskills/build.json
python -m ai_mcu_debug.cli smoke-test --config .embeddedskills/build.json
python -m ai_mcu_debug.cli runtime-log --config .embeddedskills/build.json
python -m ai_mcu_debug.cli hardware-id --target .embeddedskills/debug.target.json --chip <chip>
python -m ai_mcu_debug.cli ai-debug --mode dry-run
python -m ai_mcu_debug.cli ai-debug --mode dry-run --workspace-config .embeddedskills/config.json
python -m ai_mcu_debug.cli export-handoff --output debug_runs/handoff.zip --zip
python -m ai_mcu_debug.cli replay-handoff --manifest debug_runs/handoff/handoff_manifest.json
python -m ai_mcu_debug.cli mcp-server
python scripts/first_stage_acceptance.py --report-dir debug_runs/first_stage_acceptance
python scripts/first_stage_acceptance.py --report-dir debug_runs/first_stage_acceptance_after_flash_strict --connection-diagnostic-timeout-s 8
```

If `prepare-mcu` is not available yet, use the current fallback:

```text
python -m ai_mcu_debug.cli doctor
python -m ai_mcu_debug.cli probe-scan
python -m ai_mcu_debug.cli build-mcu-context --chip <chip> --svd <device.svd> --output examples/mcu_context.json --linker <linker.ld> --startup <startup.c> --doc datasheet=<datasheet.md-or-txt> --doc errata=<errata.md-or-txt>
python -m ai_mcu_debug.cli write-mcu-debug-doc --context examples/mcu_context.json --output docs/MCU_DEBUG_RECORD.md
python -m ai_mcu_debug.cli build --config <build.json>
python -m ai_mcu_debug.cli accept-first-stage --target <target.json> --task <task.json>
python -m ai_mcu_debug.cli analyze-debug-report --context examples/mcu_context.json --report <report.json> --output <knowledge-report.json>
```

## Workflow

1. Run `workflow-plan` first when the next step is unclear; follow its `recommended_tool_calls[]` or `user_requests[]` before guessing, and use each recommendation's `safety` metadata plus `cli`/`cli_args` equivalent before executing it. Use `workflow-run` when the safe recommendations should be executed automatically; it still blocks flash, repair, force, vision, and web search by default.
2. Identify the MCU from explicit user input, project files, startup files, linker scripts, SVD metadata, debug target configs, or probe-read IDs.
3. Run `mcu-profile` when preparing a new chip family, then run `setup-project` for first-time onboarding. It combines tool checks, probe scan, `doc-intake`, context preparation, and workspace template generation when enough user-provided evidence is present.
4. If required documents are missing, ask only for the missing item named by `setup-project.document_intake.required_requests[]` or `doc-intake`. Do not run web search, do not infer a datasheet URL, and do not continue with guessed register semantics.
5. Convert user-provided files, URLs, or document repositories into `mcu_context.json` with `setup-project`, `prepare-mcu`, `doc-repo-sync`, `fetch-docs`, or `ingest-docs`. MCP exposes the same path through `sync_document_repo`, `fetch_user_documents`, `ingest_documents`, and `check_mcu_context`.
6. Persist workspace-local defaults with `setup-project` or `init-workspace`, generating build/target/task templates when missing, then verify them with `workspace-status`.
7. Run `doctor` and `probe-scan`; generate local target config when possible. For connected read-only hardware checks, run `hardware-id` to read CPUID/vendor ID registers before trusting a guessed MCU identity.
8. Build, smoke test, and collect runtime logs through the configured build adapter. Code repair requires explicit user intent through `--allow-repair` or MCP `repair_build` with `allow_repair=true`.
9. Before any peripheral register read/write or memory write, use `mcu_context` guard commands.
10. Run debug actions through `debug-op`, `debug-sequence`, `debug`, or `ai-debug`. When `.embeddedskills/config.json` exists, `ai-debug` may use its project/context/build/target/task defaults.
11. If DAPLink/CMSIS-DAP is visible but the target SWD-DP does not respond, run `connection-diagnose` or rely on `ai-debug` to attach a safe OpenOCD connection matrix report. Do not flash to solve a physical attach failure. If NRST is not connected, record `nrst_connected=false` and treat OpenOCD `nRESET=0` as an unobserved reset line rather than proof that the target is held low.
12. Collect runtime logs through the configured build adapter when available, for example UART/RTT/SWO wrapper commands exposed as `runtime_log_command`.
13. Analyze reports with `analyze-debug-report` and cite sources from `mcu_context`, reports, runtime logs, and user-provided document manifests.
14. Run `accept-nonvision` for the replayable non-vision gate. It performs setup, `ai-debug --mode dry-run`, handoff export, and replay policy validation without flash, repair, or vision.
15. Run `skill-bootstrap` when installing/updating the skill or moving to a new AI client; it combines skill install, MCP config generation, MCP smoke testing, and capability audit without editing global client config.
16. Run `mcp-config` when a client needs a deterministic Codex/JSON/Claude Desktop MCP snippet for invoking the same local server.
17. Run `mcp-smoke` after config generation or installation changes to launch the stdio MCP server once and verify `tools/list`.
18. Run `capability-audit` when you need a deterministic readiness report for the non-vision automation surface across CLI, API, MCP, tests, docs, and safety policy evidence.
19. Export handoff packages with `export-handoff` when another AI or engineer needs to replay the work. The package must include workspace config, reports, manifests, logs, audit events, and replay commands; it must not include large vendor PDFs or firmware binaries by default.
20. Validate handoff replay with `replay-handoff` before executing it. Only use `--execute` for safe non-hardware replay commands; hardware debug, flash, repair, and force flags are blocked.
21. Every loop report must include build result, flash/connect result, debug snapshot, runtime-log evidence, knowledge evidence, uncertainty, artifacts, and next repair action.
22. Iterate code changes only from evidence: compiler errors, debug snapshots, logs, tests, knowledge-base findings, or vision evidence.

## MCU Document Repository

If the user provides an MCU document Git repository, sync it with `doc-repo-sync` and pass it to `locate-docs`/`prepare-mcu` using `--doc-repo`. The repo should contain manifest files with exact chip aliases, source URLs, hashes, and local lightweight files. Do not choose or search for a repository on behalf of the user. Do not assume a document is trustworthy from a filename alone; every source still needs `mcu_context` evidence and hash tracking.

Use `manifest-lint` on user-provided document repository manifests before relying on them for a new chip family. Use `mcu-profile` to generate the expected required document groups and a user-fillable manifest skeleton. These commands do not search the web.

If `locate-docs` reports `manifest_missing`, `chip_manifest_not_found`, `chip_alias_conflict`, `hash_mismatch`, or `unsupported_manifest`, use those structured diagnostics. Do not guess around document repo conflicts.

## Run Modes

- `ai-debug --mode dry-run`: context/tool/probe/build/smoke/runtime-log checks only; no flash, no hardware debug writes.
- `ai-debug --mode read-only`: dry-run plus reset/halt/breakpoint/step/register/memory read acceptance; no flash. For Cortex-M boards that start outside the user image, use the task option `launch_from_vector_table` to read MSP/Reset_Handler from the Flash vector table and set `$sp`/`$pc` before resuming to breakpoints.
- `ai-debug --mode run`: full hardware loop, but flash requires `--allow-flash` and code repair requires `--allow-repair`.

## Safety Gates

- Core registers such as `pc`, `sp`, `lr`, `xpsr`, and `r0` to `r15` may be read through the debugger.
- Peripheral registers must be explained from `mcu_context` before relying on their meaning.
- Register writes require field/access/reserved-bit validation.
- Memory writes require `mcu_context` and must be limited to known RAM ranges or known memory-mapped registers. Unknown addresses are blocked as `unknown_or_unapproved_address`.
- Flash, option bytes, clock, reset, and debug-control writes require explicit approval or a documented force policy.
- `ai-debug --mode run` must not flash unless `--allow-flash` is present for that specific run.
- Never use `--force` by default. Use it only when the user explicitly approves a specific write operation and the report records why the guard was overridden.
- Missing errata must be recorded as `errata_missing`, not treated as proof of no risk.

## References

See [REFERENCE.md](REFERENCE.md) for command matrix, planned commands, and acceptance gates.
