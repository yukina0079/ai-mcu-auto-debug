from __future__ import annotations

import base64
import json
import sys
import traceback
from pathlib import Path
from typing import Any, Callable

from ai_mcu_debug.api import (
    accept_nonvision,
    audit_project_capabilities,
    bootstrap_agent,
    bootstrap_skill,
    build_firmware,
    capture_board_image,
    check_prepared_context,
    check_environment,
    collect_runtime_log,
    collect_serial_log,
    diagnose_connection,
    analyze_board_image,
    export_debug_handoff,
    fetch_user_documents,
    get_mcu_profile,
    get_workspace_status,
    generate_mcp_client_config,
    ingest_user_documents,
    initialize_workspace,
    install_skill_package,
    lint_mcu_manifest,
    locate_mcu_documents,
    plan_docs,
    plan_next_workflow,
    prepare_context,
    read_hardware_id,
    replay_debug_handoff,
    repair_build,
    resolve_mcu_chip,
    run_next_workflow,
    run_ai_debug,
    run_debug_op,
    scan_cameras,
    scan_debug_probes_api,
    smoke_test_firmware,
    smoke_test_mcp_server,
    setup_project,
    sync_document_repo,
    validate_target_config,
    write_debug_record,
)


def _object_schema(
    properties: dict[str, Any],
    *,
    required: list[str] | None = None,
    additional_properties: bool = False,
) -> dict[str, Any]:
    schema: dict[str, Any] = {
        "type": "object",
        "properties": properties,
        "additionalProperties": additional_properties,
    }
    if required:
        schema["required"] = required
    return schema


def _string(description: str, *, default: str | None = None, enum: list[str] | None = None) -> dict[str, Any]:
    schema: dict[str, Any] = {"type": "string", "description": description}
    if default is not None:
        schema["default"] = default
    if enum:
        schema["enum"] = enum
    return schema


def _boolean(description: str, *, default: bool | None = None) -> dict[str, Any]:
    schema: dict[str, Any] = {"type": "boolean", "description": description}
    if default is not None:
        schema["default"] = default
    return schema


def _number(description: str, *, default: float | None = None) -> dict[str, Any]:
    schema: dict[str, Any] = {"type": "number", "description": description}
    if default is not None:
        schema["default"] = default
    return schema


def _integer(description: str, *, default: int | None = None) -> dict[str, Any]:
    schema: dict[str, Any] = {"type": "integer", "description": description}
    if default is not None:
        schema["default"] = default
    return schema


def _string_array(description: str, item_description: str) -> dict[str, Any]:
    return {
        "type": "array",
        "description": description,
        "items": {"type": "string", "description": item_description},
    }


PATH = _string("Workspace-relative or absolute file/directory path.")
PROJECT_PATH = _string("Workspace-relative or absolute firmware project path.", default=".")
CHIP = _string("Exact MCU part number or family alias supplied by the user, for example STM32F103RCT6.")
DOC_ARGS = _string_array(
    "User-provided document arguments.",
    "kind=path-or-url, for example datasheet=docs/datasheet.pdf or errata=https://example/errata.pdf.",
)
URL_ARGS = _string_array(
    "User-provided document URLs or local file paths to cache.",
    "kind=url-or-path, for example datasheet=https://vendor/datasheet.pdf.",
)
DOC_REPOS = _string_array("User-provided MCU document repository paths.", "Workspace-relative or absolute repo path.")
COMMON_EVIDENCE_PROPS = {
    "project": PROJECT_PATH,
    "chip": CHIP,
    "svd": _string("User-provided SVD path."),
    "linker": _string("User-provided linker script path."),
    "startup": _string("User-provided startup source path."),
    "docs": DOC_ARGS,
    "doc_repos": DOC_REPOS,
}
CONTEXT_PREP_PROPS = {
    **COMMON_EVIDENCE_PROPS,
    "output": _string("Output mcu_context.json path.", default="examples/mcu_context.json"),
    "board": _string("Optional board name supplied by the user."),
    "package": _string("Optional MCU package name supplied by the user."),
}
BUILD_BACKEND = _string(
    "Build backend template to generate.",
    enum=["cmake", "command", "platformio", "keil", "esp-idf"],
)
DEBUG_BACKEND = _string(
    "Debug backend template to generate.",
    enum=["openocd-gdb", "pyocd-gdb", "jlink-gdb", "probe-rs-gdb", "esp-idf-openocd-gdb"],
)
WORKSPACE_SETUP_PROPS = {
    **COMMON_EVIDENCE_PROPS,
    "output_dir": _string("Workspace-local state directory.", default=".embeddedskills"),
    "context": _string("mcu_context.json path.", default="examples/mcu_context.json"),
    "board": _string("Optional board name supplied by the user."),
    "package": _string("Optional MCU package name supplied by the user."),
    "knowledge_repo_url": _string("User-provided MCU document Git repository URL. Do not guess this value."),
    "knowledge_repo_path": _string("Local path for the user-provided MCU document repository."),
    "build_config": _string("Existing build config path to reuse instead of generating one."),
    "build_backend": BUILD_BACKEND,
    "pio_env": _string("PlatformIO environment name."),
    "keil_project": _string("Keil .uvprojx project path."),
    "keil_target": _string("Keil target name."),
    "uv4": _string("UV4.exe path for Keil command templates."),
    "target": _string("Existing debug target config path to reuse instead of generating one."),
    "task": _string("Existing debug task config path to reuse instead of generating one."),
    "debug_backend": DEBUG_BACKEND,
    "executable": _string("Firmware ELF path for debugger templates."),
    "interface": _string("OpenOCD interface cfg, for example interface/cmsis-dap.cfg."),
    "target_cfg": _string("OpenOCD target cfg, for example target/stm32f1x.cfg."),
    "transport": _string("Debug transport.", default="swd", enum=["swd", "jtag"]),
    "adapter_speed": _integer("Debug adapter speed in kHz.", default=100),
    "scan_probes": _boolean("Run probe scan during setup.", default=True),
    "force": _boolean("Override setup path-existence guards only when explicitly intended.", default=False),
}
AI_DEBUG_PROPS = {
    **COMMON_EVIDENCE_PROPS,
    "mode": _string("Workflow mode.", default="dry-run", enum=["dry-run", "read-only", "run"]),
    "context": _string("mcu_context.json path. Defaults to workspace config when present."),
    "board": _string("Optional board name supplied by the user."),
    "package": _string("Optional MCU package name supplied by the user."),
    "build_config": _string("Build config path. Defaults to workspace config when present."),
    "target": _string("Debug target config path. Defaults to workspace config when present."),
    "task": _string("Debug task config path. Defaults to workspace config when present."),
    "report_dir": _string("Directory for ai-debug reports.", default="debug_runs/ai_debug_api"),
    "allow_flash": _boolean("Permit flashing during mode=run. Defaults to false.", default=False),
    "allow_repair": _boolean("Permit code edits by the configured repair tool. Defaults to false.", default=False),
    "max_repair_iterations": _integer("Maximum repair iterations when allow_repair=true."),
    "connection_diagnostic_timeout_s": _number("Per-attempt connection diagnostic timeout in seconds.", default=12.0),
    "workspace_config": _string("Workspace defaults config path.", default=".embeddedskills/config.json"),
}
DEBUG_OPERATION = _string(
    "Guarded debugger operation.",
    enum=[
        "halt",
        "resume",
        "wait-for-stop",
        "step",
        "reset",
        "set-breakpoint",
        "delete-breakpoint",
        "read-register",
        "write-register",
        "read-memory",
        "write-memory",
    ],
)
SCHEMAS: dict[str, dict[str, Any]] = {
    "agent_bootstrap": _object_schema(
        {
            "project": PROJECT_PATH,
            "client": _string(
                "Target AI client profile.",
                default="generic-json",
                enum=["codex", "generic-json", "claude-desktop", "claude-code", "opencode", "trae", "qoder"],
            ),
            "python_executable": _string("Python executable used to launch the MCP server. Defaults to the current interpreter."),
            "server_name": _string("MCP server name in the client config.", default="ai_mcu_debug"),
            "output": _string("Optional JSON bootstrap report output path."),
            "timeout_s": _number("MCP smoke test timeout in seconds.", default=10.0),
            "dry_run": _boolean("Report readiness without modifying global client config or touching hardware.", default=True),
            "include_vision": _boolean("Treat the optional vision capability as a blocking audit requirement.", default=False),
        }
    ),
    "prepare_mcu_context": _object_schema(CONTEXT_PREP_PROPS),
    "plan_document_intake": _object_schema(
        {
            **COMMON_EVIDENCE_PROPS,
            "output": _string("Planned output mcu_context.json path.", default="examples/mcu_context.json"),
        }
    ),
    "workflow_plan": _object_schema(
        {
            **COMMON_EVIDENCE_PROPS,
            "context": _string("mcu_context.json path.", default="examples/mcu_context.json"),
            "workspace_config": _string("Workspace defaults config path.", default=".embeddedskills/config.json"),
        }
    ),
    "workflow_run": _object_schema(
        {
            **COMMON_EVIDENCE_PROPS,
            "context": _string("mcu_context.json path.", default="examples/mcu_context.json"),
            "workspace_config": _string("Workspace defaults config path.", default=".embeddedskills/config.json"),
            "report_dir": _string("Workflow-run report directory.", default="debug_runs/workflow_run"),
            "max_steps": _integer("Maximum planner/execution iterations.", default=8),
            "allow_file_writes": _boolean("Permit safe file-writing setup steps.", default=True),
            "allow_hardware": _boolean("Permit safe read-only hardware-touching steps.", default=True),
            "stop_on_failure": _boolean("Stop after the first failed or policy-blocked recommended call.", default=True),
        }
    ),
    "capability_audit": _object_schema(
        {
            "project": PROJECT_PATH,
            "include_vision": _boolean("Include the optional camera/vision capability as a blocking requirement.", default=False),
            "output": _string("Optional JSON report output path."),
        }
    ),
    "mcp_config": _object_schema(
        {
            "project": PROJECT_PATH,
            "client": _string(
                "Target AI client config format.",
                default="codex",
                enum=["codex", "generic-json", "claude-desktop", "claude-code", "opencode", "trae", "qoder"],
            ),
            "python_executable": _string("Python executable used to launch the MCP server. Defaults to the current interpreter."),
            "server_name": _string("MCP server name in the client config.", default="ai_mcu_debug"),
            "output": _string("Optional path to write the generated config snippet."),
        }
    ),
    "mcp_smoke": _object_schema(
        {
            "project": PROJECT_PATH,
            "python_executable": _string("Python executable used to launch the MCP server. Defaults to the current interpreter."),
            "required_tools": _string_array("Required MCP tool names that must appear in tools/list.", "MCP tool name."),
            "timeout_s": _number("Smoke test timeout in seconds.", default=10.0),
            "output": _string("Optional JSON smoke report output path."),
        }
    ),
    "skill_bootstrap": _object_schema(
        {
            "project": PROJECT_PATH,
            "source": _string("Source skill package directory. Defaults to repo skills/mcu-auto-debug."),
            "destination": _string("Exact destination skill directory. Overrides codex_home when set."),
            "codex_home": _string("Codex home directory. Defaults to CODEX_HOME or ~/.codex."),
            "skill_name": _string("Skill directory name.", default="mcu-auto-debug"),
            "client": _string(
                "Target AI client config format.",
                default="codex",
                enum=["codex", "generic-json", "claude-desktop", "claude-code", "opencode", "trae", "qoder"],
            ),
            "python_executable": _string("Python executable used to launch the MCP server. Defaults to the current interpreter."),
            "server_name": _string("MCP server name in the client config.", default="ai_mcu_debug"),
            "config_output": _string("Optional path to write the generated MCP config snippet."),
            "report_output": _string("Optional JSON bootstrap report output path."),
            "dry_run": _boolean("Plan install/config outputs without writing files.", default=False),
            "force": _boolean("Overwrite differing installed skill files only when explicitly intended.", default=False),
            "skip_install": _boolean("Skip copying the skill package.", default=False),
            "skip_smoke": _boolean("Skip launching the MCP server smoke test.", default=False),
            "include_vision": _boolean("Treat the optional vision capability as a blocking audit requirement.", default=False),
            "timeout_s": _number("MCP smoke test timeout in seconds.", default=10.0),
        }
    ),
    "resolve_chip": _object_schema(
        {
            "project": PROJECT_PATH,
            "chip": CHIP,
            "svd": _string("SVD path to inspect."),
            "linker": _string("Linker script path to inspect."),
            "startup": _string("Startup source path to inspect."),
            "target": _string("Debug target config path to inspect."),
        }
    ),
    "locate_documents": _object_schema(COMMON_EVIDENCE_PROPS),
    "fetch_user_documents": _object_schema(
        {
            "manifest": _string("Manifest path to write cached user documents into."),
            "chip": CHIP,
            "urls": URL_ARGS,
            "timeout_s": _number("Fetch timeout in seconds.", default=30.0),
        },
        required=["manifest"],
    ),
    "ingest_documents": _object_schema(
        {
            "manifest": _string("User document manifest path."),
            "output": _string("Output mcu_context.json path.", default="examples/mcu_context.json"),
            "chip": CHIP,
            "svd": _string("SVD path."),
            "linker": _string("Linker script path."),
            "startup": _string("Startup source path."),
            "board": _string("Optional board name supplied by the user."),
            "package": _string("Optional MCU package name supplied by the user."),
        },
        required=["manifest"],
    ),
    "sync_document_repo": _object_schema(
        {
            "url": _string("User-provided MCU document Git repository URL. Do not guess this value."),
            "local_path": _string("Local clone/update path.", default="knowledge_repos/mcu-docs"),
            "ref": _string("Optional branch, tag, or commit to checkout."),
            "update": _boolean("Update an existing local clone.", default=True),
        }
    ),
    "check_mcu_context": _object_schema(
        {"context": _string("mcu_context.json path to validate.", default="examples/mcu_context.json")}
    ),
    "write_debug_record": _object_schema(
        {
            "context": _string("mcu_context.json path.", default="examples/mcu_context.json"),
            "output": _string("Markdown debug record output path.", default="docs/MCU_DEBUG_RECORD.md"),
        }
    ),
    "doctor": _object_schema(
        {
            "debug_backend": DEBUG_BACKEND,
            "build_backend": BUILD_BACKEND,
        }
    ),
    "probe_scan": _object_schema({}),
    "init_workspace": _object_schema(
        {
            **{key: value for key, value in WORKSPACE_SETUP_PROPS.items() if key not in {"docs", "doc_repos"}},
            "generate_templates": _boolean("Generate missing build/debug/task template files.", default=True),
            "run_doctor_check": _boolean("Run doctor to resolve local tool paths for templates.", default=True),
            "scan_probes": _boolean("Scan probes to infer debug interface templates.", default=True),
        }
    ),
    "validate_target": _object_schema(
        {
            "target": _string("Debug target config path."),
            "scan_probes": _boolean("Scan local probes and compare with the target config.", default=False),
        },
        required=["target"],
    ),
    "connection_diagnose": _object_schema(
        {
            "target": _string("Debug target config path. Defaults to workspace config when present."),
            "report_dir": _string("Connection diagnostics report directory.", default="debug_runs/connection_diagnostics_api"),
            "timeout_s": _number("Per-attempt timeout in seconds.", default=12.0),
            "workspace_config": _string("Workspace defaults config path.", default=".embeddedskills/config.json"),
        }
    ),
    "setup_project": _object_schema(WORKSPACE_SETUP_PROPS),
    "build_firmware": _object_schema({"config": _string("Build config JSON path.")}, required=["config"]),
    "smoke_test_firmware": _object_schema({"config": _string("Build config JSON path.")}, required=["config"]),
    "collect_runtime_log": _object_schema({"config": _string("Build config JSON path.")}, required=["config"]),
    "collect_serial_log": _object_schema(
        {
            "port": _string("Serial port path, for example COM3 or /dev/ttyACM0."),
            "baud": _integer("Serial baud rate.", default=115200),
            "duration_s": _number("Capture duration in seconds.", default=5.0),
            "timeout_s": _number("Per-read timeout in seconds.", default=0.2),
            "output": _string("Optional JSON serial log report output path."),
        },
        required=["port"],
    ),
    "camera_scan": _object_schema(
        {
            "max_devices": _integer("Maximum camera indexes to probe.", default=5),
            "backend": {
                "type": "string",
                "enum": ["auto", "dshow", "msmf", "v4l2"],
                "default": "auto",
                "description": "OpenCV camera backend.",
            },
            "allow_camera": _boolean("Must be true to permit camera device access.", default=False),
            "output": _string("Optional JSON camera scan report output path."),
        }
    ),
    "capture_board_image": _object_schema(
        {
            "camera_index": _integer("Camera device index.", default=0),
            "image_output": _string("Captured JPEG/PNG output path.", default="debug_runs/vision/latest.jpg"),
            "report_output": _string("Optional JSON observation report output path."),
            "baseline": _string("Optional baseline image for deterministic change detection."),
            "width": _integer("Requested capture width."),
            "height": _integer("Requested capture height."),
            "warmup_frames": _integer("Frames discarded while exposure settles.", default=5),
            "backend": {
                "type": "string",
                "enum": ["auto", "dshow", "msmf", "v4l2"],
                "default": "auto",
                "description": "OpenCV camera backend.",
            },
            "allow_camera": _boolean("Must be true to permit camera capture.", default=False),
        }
    ),
    "analyze_board_image": _object_schema(
        {
            "image": _string("Existing board image path."),
            "baseline": _string("Optional baseline image for deterministic change detection."),
            "output": _string("Optional JSON observation report output path."),
        },
        required=["image"],
    ),
    "repair_build": _object_schema(
        {
            "config": _string("Build config JSON path."),
            "allow_repair": _boolean("Must be true to permit code edits by the repair adapter.", default=False),
            "max_iterations": _integer("Maximum repair iterations."),
        },
        required=["config"],
    ),
    "install_skill": _object_schema(
        {
            "source": _string("Source skill package directory. Defaults to repo skills/mcu-auto-debug."),
            "destination": _string("Exact destination skill directory. Overrides codex_home when set."),
            "codex_home": _string("Codex home directory. Defaults to CODEX_HOME or ~/.codex."),
            "skill_name": _string("Skill directory name.", default="mcu-auto-debug"),
            "dry_run": _boolean("Report planned copies without writing files.", default=False),
            "force": _boolean("Overwrite destination files that differ from the source.", default=False),
        }
    ),
    "mcu_profile": _object_schema({"chip": CHIP}),
    "lint_mcu_manifest": _object_schema(
        {
            "manifest": _string("MCU document repository manifest path."),
            "chip": CHIP,
            "strict_hashes": _boolean("Treat local hash mismatches as blocking.", default=False),
        },
        required=["manifest"],
    ),
    "accept_nonvision": _object_schema(
        {
            **WORKSPACE_SETUP_PROPS,
            "report_dir": _string("Acceptance report directory.", default="debug_runs/nonvision_acceptance"),
            "handoff_output": _string("Optional handoff output directory or zip path."),
            "handoff_project": _string("Project root to package in the handoff.", default="."),
            "zip_handoff": _boolean("Write a zip handoff package.", default=False),
        }
    ),
    "run_ai_debug": _object_schema(AI_DEBUG_PROPS),
    "debug_op_guarded": _object_schema(
        {
            "target": _string("Debug target config path."),
            "operation": DEBUG_OPERATION,
            "context": _string("mcu_context.json path for register/memory guards."),
            "force": _boolean("Override a guard only with explicit user intent.", default=False),
            "register": _string("Register name for read-register/write-register."),
            "value": {"type": ["string", "integer"], "description": "Register value for write-register."},
            "address": {"type": ["string", "integer"], "description": "Address for read-memory/write-memory."},
            "length": _integer("Byte length for read-memory."),
            "data_hex": _string("Hex bytes for write-memory."),
            "location": _string("Breakpoint location for set-breakpoint."),
            "breakpoint_id": _string("Breakpoint id for delete-breakpoint."),
            "timeout_s": _number("Timeout for wait-for-stop.", default=10.0),
            "halt": _boolean("Reset should halt the target when operation=reset.", default=True),
        },
        required=["target", "operation"],
    ),
    "read_hardware_id": _object_schema(
        {
            "target": _string("Debug target config path. Defaults to workspace config when present."),
            "chip": CHIP,
            "report_dir": _string("Hardware identity report directory.", default="debug_runs/hardware_identity_api"),
            "halt": _boolean("Halt the target before reading identity registers.", default=True),
            "workspace_config": _string("Workspace defaults config path.", default=".embeddedskills/config.json"),
        }
    ),
    "export_handoff": _object_schema(
        {
            "output": _string("Handoff output directory or zip path.", default="debug_runs/handoff"),
            "project": PROJECT_PATH,
            "workspace_config": _string("Workspace defaults config path.", default=".embeddedskills/config.json"),
            "report_dir": _string("Optional report directory to include."),
            "include_globs": _string_array("Additional lightweight files to include.", "Glob relative to project root."),
            "zip_output": _boolean("Write a zip package.", default=False),
        }
    ),
    "replay_handoff": _object_schema(
        {
            "manifest": _string("Handoff manifest path."),
            "project": PROJECT_PATH,
            "execute": _boolean("Execute safe replay commands instead of validating only.", default=False),
            "output": _string("Optional replay report output path."),
            "timeout_s": _number("Replay command timeout in seconds.", default=120.0),
            "continue_on_failure": _boolean("Continue replay after a safe command fails.", default=False),
        },
        required=["manifest"],
    ),
    "workspace_status": _object_schema(
        {"config": _string("Workspace defaults config path.", default=".embeddedskills/config.json")}
    ),
}


TOOLS: dict[str, dict[str, Any]] = {
    "agent_bootstrap": {
        "description": "Run non-hardware readiness checks and MCP/CLI handoff hints for Codex, Claude, OpenCode, Trae, Qoder, or a generic AI agent.",
        "inputSchema": SCHEMAS["agent_bootstrap"],
    },
    "prepare_mcu_context": {
        "description": "Prepare mcu_context.json from a project, chip, local files, and optional MCU document repositories.",
        "inputSchema": SCHEMAS["prepare_mcu_context"],
    },
    "plan_document_intake": {
        "description": "Plan exactly which user-provided MCU documents/files/URLs are still needed before context generation.",
        "inputSchema": SCHEMAS["plan_document_intake"],
    },
    "workflow_plan": {
        "description": "Return the next safe MCU onboarding/debug tool calls without modifying files or touching hardware.",
        "inputSchema": SCHEMAS["workflow_plan"],
    },
    "workflow_run": {
        "description": "Execute safe workflow-plan recommendations without flash, repair, force, vision, or web search.",
        "inputSchema": SCHEMAS["workflow_run"],
    },
    "capability_audit": {
        "description": "Audit the current non-vision automation capability surface and remaining gaps.",
        "inputSchema": SCHEMAS["capability_audit"],
    },
    "mcp_config": {
        "description": "Generate a portable MCP client config snippet for the ai-mcu-debug server.",
        "inputSchema": SCHEMAS["mcp_config"],
    },
    "mcp_smoke": {
        "description": "Launch the ai-mcu-debug MCP server once and verify JSON-RPC tool discovery.",
        "inputSchema": SCHEMAS["mcp_smoke"],
    },
    "skill_bootstrap": {
        "description": "Install/update the skill, generate MCP config, smoke-test MCP, and audit non-vision readiness.",
        "inputSchema": SCHEMAS["skill_bootstrap"],
    },
    "resolve_chip": {
        "description": "Resolve MCU identity from explicit user input and project evidence; returns ambiguity instead of guessing.",
        "inputSchema": SCHEMAS["resolve_chip"],
    },
    "locate_documents": {
        "description": "Locate local/user-provided MCU documents, SVDs, linker scripts, startup files, and document repo manifests without web search.",
        "inputSchema": SCHEMAS["locate_documents"],
    },
    "fetch_user_documents": {
        "description": "Cache user-provided MCU document files or URLs, hash them, and write a manifest.",
        "inputSchema": SCHEMAS["fetch_user_documents"],
    },
    "ingest_documents": {
        "description": "Convert a user-provided document manifest plus SVD/linker/startup evidence into mcu_context.json.",
        "inputSchema": SCHEMAS["ingest_documents"],
    },
    "sync_document_repo": {
        "description": "Clone or update a user-provided MCU document Git repository for later locate/prepare steps.",
        "inputSchema": SCHEMAS["sync_document_repo"],
    },
    "check_mcu_context": {
        "description": "Validate that mcu_context.json is sufficient for safe register, memory, and evidence-backed debug.",
        "inputSchema": SCHEMAS["check_mcu_context"],
    },
    "write_debug_record": {
        "description": "Generate a Markdown MCU debug record from mcu_context.json for AI grounding and handoff.",
        "inputSchema": SCHEMAS["write_debug_record"],
    },
    "doctor": {
        "description": "Check local tool availability for selected debug/build backends.",
        "inputSchema": SCHEMAS["doctor"],
    },
    "probe_scan": {
        "description": "Scan local USB/PnP devices for supported debug probes.",
        "inputSchema": SCHEMAS["probe_scan"],
    },
    "init_workspace": {
        "description": "Persist workspace defaults and optionally generate build/debug/task templates.",
        "inputSchema": SCHEMAS["init_workspace"],
    },
    "validate_target": {
        "description": "Validate a debug target config against optional detected probe evidence.",
        "inputSchema": SCHEMAS["validate_target"],
    },
    "connection_diagnose": {
        "description": "Run a bounded, non-flashing OpenOCD connection matrix for a target config.",
        "inputSchema": SCHEMAS["connection_diagnose"],
    },
    "setup_project": {
        "description": "Run one-pass non-vision project setup: tool checks, document intake, context preparation, and workspace template generation.",
        "inputSchema": SCHEMAS["setup_project"],
    },
    "build_firmware": {
        "description": "Build firmware through the configured build adapter and return parsed errors/warnings.",
        "inputSchema": SCHEMAS["build_firmware"],
    },
    "smoke_test_firmware": {
        "description": "Run the configured non-hardware smoke test command.",
        "inputSchema": SCHEMAS["smoke_test_firmware"],
    },
    "collect_runtime_log": {
        "description": "Collect UART/RTT/SWO/semihosting evidence through the configured runtime log command.",
        "inputSchema": SCHEMAS["collect_runtime_log"],
    },
    "collect_serial_log": {
        "description": "Collect UART/USB-serial evidence directly through pyserial when available.",
        "inputSchema": SCHEMAS["collect_serial_log"],
    },
    "camera_scan": {
        "description": "Discover camera indexes only when allow_camera=true; no image is retained.",
        "inputSchema": SCHEMAS["camera_scan"],
    },
    "capture_board_image": {
        "description": "Capture one bench image, return deterministic quality/change evidence, and attach the image for agent inspection.",
        "inputSchema": SCHEMAS["capture_board_image"],
    },
    "analyze_board_image": {
        "description": "Analyze and attach an existing board image for evidence-backed agent visual inspection.",
        "inputSchema": SCHEMAS["analyze_board_image"],
    },
    "repair_build": {
        "description": "Run the configured AI/code repair build loop only when allow_repair=true.",
        "inputSchema": SCHEMAS["repair_build"],
    },
    "install_skill": {
        "description": "Install or update the local Codex mcu-auto-debug skill package with hash guardrails.",
        "inputSchema": SCHEMAS["install_skill"],
    },
    "mcu_profile": {
        "description": "Return deterministic MCU family document requirements and a user-fillable manifest template without web search.",
        "inputSchema": SCHEMAS["mcu_profile"],
    },
    "lint_mcu_manifest": {
        "description": "Validate a user-provided MCU document repository manifest for required evidence and hash hygiene.",
        "inputSchema": SCHEMAS["lint_mcu_manifest"],
    },
    "accept_nonvision": {
        "description": "Run the replayable non-vision acceptance chain: setup-project, ai-debug dry-run, handoff export, and replay validation.",
        "inputSchema": SCHEMAS["accept_nonvision"],
    },
    "run_ai_debug": {
        "description": "Run the guarded AI MCU debug workflow. Defaults to dry-run unless mode is supplied.",
        "inputSchema": SCHEMAS["run_ai_debug"],
    },
    "debug_op_guarded": {
        "description": "Run one guarded debug operation through the configured debug target.",
        "inputSchema": SCHEMAS["debug_op_guarded"],
    },
    "read_hardware_id": {
        "description": "Read CPUID/vendor silicon identity registers through the configured debug target.",
        "inputSchema": SCHEMAS["read_hardware_id"],
    },
    "export_handoff": {
        "description": "Export a lightweight replayable handoff package with configs, reports, logs, manifests, and evidence.",
        "inputSchema": SCHEMAS["export_handoff"],
    },
    "replay_handoff": {
        "description": "Validate or execute safe replay commands from a handoff manifest; hardware-affecting commands are blocked.",
        "inputSchema": SCHEMAS["replay_handoff"],
    },
    "workspace_status": {
        "description": "Inspect .embeddedskills workspace defaults and required path existence.",
        "inputSchema": SCHEMAS["workspace_status"],
    },
}


def main() -> int:
    server = McpServer()
    return server.serve()


class McpServer:
    def __init__(self) -> None:
        self._handlers: dict[str, Callable[[dict[str, Any]], Any]] = {
            "agent_bootstrap": lambda args: bootstrap_agent(**args),
            "prepare_mcu_context": lambda args: prepare_context(**args),
            "plan_document_intake": lambda args: plan_docs(**args),
            "workflow_plan": lambda args: plan_next_workflow(**args),
            "workflow_run": lambda args: run_next_workflow(**args),
            "capability_audit": lambda args: audit_project_capabilities(**args),
            "mcp_config": lambda args: generate_mcp_client_config(**args),
            "mcp_smoke": lambda args: smoke_test_mcp_server(**args),
            "skill_bootstrap": lambda args: bootstrap_skill(**args),
            "resolve_chip": lambda args: resolve_mcu_chip(**args),
            "locate_documents": lambda args: locate_mcu_documents(**args),
            "fetch_user_documents": lambda args: fetch_user_documents(**args),
            "ingest_documents": lambda args: ingest_user_documents(**args),
            "sync_document_repo": lambda args: sync_document_repo(**args),
            "check_mcu_context": lambda args: check_prepared_context(**args),
            "write_debug_record": lambda args: write_debug_record(**args),
            "doctor": lambda args: check_environment(**args),
            "probe_scan": lambda args: scan_debug_probes_api(),
            "init_workspace": lambda args: initialize_workspace(**args),
            "validate_target": lambda args: validate_target_config(**args),
            "connection_diagnose": lambda args: diagnose_connection(**args),
            "setup_project": lambda args: setup_project(**args),
            "build_firmware": lambda args: build_firmware(**args),
            "smoke_test_firmware": lambda args: smoke_test_firmware(**args),
            "collect_runtime_log": lambda args: collect_runtime_log(**args),
            "collect_serial_log": lambda args: collect_serial_log(**args),
            "camera_scan": lambda args: scan_cameras(**args),
            "capture_board_image": lambda args: capture_board_image(**args),
            "analyze_board_image": lambda args: analyze_board_image(**args),
            "repair_build": lambda args: repair_build(**args),
            "install_skill": lambda args: install_skill_package(**args),
            "mcu_profile": lambda args: get_mcu_profile(**args),
            "lint_mcu_manifest": lambda args: lint_mcu_manifest(**args),
            "accept_nonvision": lambda args: accept_nonvision(**args),
            "run_ai_debug": lambda args: run_ai_debug(**args),
            "debug_op_guarded": lambda args: run_debug_op(**args),
            "read_hardware_id": lambda args: read_hardware_id(**args),
            "export_handoff": lambda args: export_debug_handoff(**args),
            "replay_handoff": lambda args: replay_debug_handoff(**args),
            "workspace_status": lambda args: get_workspace_status(config=args.get("config", ".embeddedskills/config.json")),
        }

    def serve(self) -> int:
        for line in sys.stdin:
            if not line.strip():
                continue
            try:
                request = json.loads(line)
                response = self.handle(request)
            except Exception as exc:
                response = _error_response(None, -32700, str(exc))
            if response is not None:
                sys.stdout.write(json.dumps(response, ensure_ascii=False, default=str) + "\n")
                sys.stdout.flush()
        return 0

    def handle(self, request: dict[str, Any]) -> dict[str, Any] | None:
        method = request.get("method")
        request_id = request.get("id")
        params = request.get("params") or {}
        if method == "notifications/initialized":
            return None
        if method == "initialize":
            return _result_response(
                request_id,
                {
                    "protocolVersion": params.get("protocolVersion") or "2025-06-18",
                    "capabilities": {"tools": {}},
                    "serverInfo": {"name": "ai-mcu-debug", "version": "0.1.0"},
                },
            )
        if method == "tools/list":
            return _result_response(request_id, {"tools": [_tool_descriptor(name, spec) for name, spec in TOOLS.items()]})
        if method == "tools/call":
            name = str(params.get("name") or "")
            args = params.get("arguments") or {}
            return self._call_tool(request_id, name, args)
        if method == "ping":
            return _result_response(request_id, {})
        return _error_response(request_id, -32601, f"Unsupported MCP method: {method}")

    def _call_tool(self, request_id: Any, name: str, args: Any) -> dict[str, Any]:
        handler = self._handlers.get(name)
        if handler is None:
            return _error_response(request_id, -32602, f"Unknown tool: {name}")
        argument_errors = _validate_tool_arguments(TOOLS[name]["inputSchema"], args)
        if argument_errors:
            return _result_response(
                request_id,
                _tool_result(
                    {"ok": False, "status": "invalid_arguments", "tool": name, "errors": argument_errors},
                    is_error=True,
                ),
            )
        try:
            result = handler(args)
            is_error = isinstance(result, dict) and result.get("ok") is False
            return _result_response(request_id, _tool_result(result, is_error=is_error))
        except Exception as exc:
            return _result_response(
                request_id,
                _tool_result({"ok": False, "error": str(exc), "traceback": traceback.format_exc()}, is_error=True),
            )


def _tool_descriptor(name: str, spec: dict[str, Any]) -> dict[str, Any]:
    return {
        "name": name,
        "description": spec["description"],
        "inputSchema": spec["inputSchema"],
    }


def _tool_result(result: Any, is_error: bool) -> dict[str, Any]:
    content: list[dict[str, Any]] = [
        {"type": "text", "text": json.dumps(result, indent=2, ensure_ascii=False, default=str)}
    ]
    if isinstance(result, dict) and result.get("ok") and result.get("image_path"):
        image_path = Path(str(result["image_path"]))
        if image_path.is_file():
            content.append(
                {
                    "type": "image",
                    "data": base64.b64encode(image_path.read_bytes()).decode("ascii"),
                    "mimeType": str(result.get("mime_type") or "image/jpeg"),
                }
            )
    return {"content": content, "isError": is_error}


def _validate_tool_arguments(schema: dict[str, Any], args: Any) -> list[dict[str, Any]]:
    if not isinstance(args, dict):
        return [
            {
                "path": "$",
                "code": "invalid_type",
                "expected": "object",
                "actual": _json_type(args),
                "message": "MCP tool arguments must be a JSON object.",
            }
        ]

    properties = schema.get("properties") or {}
    required = set(schema.get("required") or [])
    errors: list[dict[str, Any]] = []
    for name in sorted(required):
        if name not in args or args[name] is None:
            errors.append(
                {
                    "path": f"$.{name}",
                    "code": "missing_required",
                    "message": f"Missing required argument: {name}.",
                }
            )

    if schema.get("additionalProperties") is False:
        for name in sorted(args):
            if name not in properties:
                errors.append(
                    {
                        "path": f"$.{name}",
                        "code": "unexpected_property",
                        "message": f"Unexpected argument: {name}.",
                    }
                )

    for name, value in args.items():
        property_schema = properties.get(name)
        if property_schema is None or (value is None and name not in required):
            continue
        errors.extend(_validate_json_value(value, property_schema, f"$.{name}"))
    return errors


def _validate_json_value(value: Any, schema: dict[str, Any], path: str) -> list[dict[str, Any]]:
    errors: list[dict[str, Any]] = []
    expected_type = schema.get("type")
    if expected_type is not None:
        expected_types = expected_type if isinstance(expected_type, list) else [expected_type]
        if not any(_matches_json_type(value, item) for item in expected_types):
            errors.append(
                {
                    "path": path,
                    "code": "invalid_type",
                    "expected": expected_types,
                    "actual": _json_type(value),
                    "message": f"Invalid type for {path}.",
                }
            )
            return errors

    enum = schema.get("enum")
    if enum is not None and value not in enum:
        errors.append(
            {
                "path": path,
                "code": "invalid_enum",
                "allowed": enum,
                "actual": value,
                "message": f"Invalid enum value for {path}.",
            }
        )

    if isinstance(value, list) and isinstance(schema.get("items"), dict):
        for index, item in enumerate(value):
            if item is None:
                continue
            errors.extend(_validate_json_value(item, schema["items"], f"{path}[{index}]"))
    return errors


def _matches_json_type(value: Any, expected_type: str) -> bool:
    if expected_type == "object":
        return isinstance(value, dict)
    if expected_type == "array":
        return isinstance(value, list)
    if expected_type == "string":
        return isinstance(value, str)
    if expected_type == "boolean":
        return isinstance(value, bool)
    if expected_type == "integer":
        return isinstance(value, int) and not isinstance(value, bool)
    if expected_type == "number":
        return isinstance(value, (int, float)) and not isinstance(value, bool)
    if expected_type == "null":
        return value is None
    return True


def _json_type(value: Any) -> str:
    if value is None:
        return "null"
    if isinstance(value, bool):
        return "boolean"
    if isinstance(value, dict):
        return "object"
    if isinstance(value, list):
        return "array"
    if isinstance(value, str):
        return "string"
    if isinstance(value, int):
        return "integer"
    if isinstance(value, float):
        return "number"
    return type(value).__name__


def _result_response(request_id: Any, result: Any) -> dict[str, Any]:
    return {"jsonrpc": "2.0", "id": request_id, "result": result}


def _error_response(request_id: Any, code: int, message: str) -> dict[str, Any]:
    return {"jsonrpc": "2.0", "id": request_id, "error": {"code": code, "message": message}}




if __name__ == "__main__":
    raise SystemExit(main())
