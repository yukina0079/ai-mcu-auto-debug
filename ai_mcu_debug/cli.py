from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

from .audit import export_handoff
from .audit_log import append_audit_event
from .bootstrap import setup_project
from .capability_audit import audit_capabilities
from .config import load_build_config, load_debug_task, load_target_config
from .connection_diagnostics import run_openocd_connection_matrix
from .doctor import run_doctor
from .elf_check import check_elf
from .factory import create_build_adapter, create_debug_adapter, create_repair_adapter
from .hardware_identity import read_hardware_identity
from .knowledge import (
    JsonKnowledgeAdapter,
    build_mcu_context,
    check_context,
    compare_debug_report,
    discover_docs,
    fetch_docs,
    ingest_docs,
    lint_manifest,
    locate_docs,
    manifest_template,
    plan_document_intake,
    prepare_mcu,
    profile_for_chip,
    resolve_chip,
    sync_doc_repo,
    write_mcu_debug_doc,
)
from .local_config import write_detected_openocd_target
from .mcp_config import generate_mcp_config
from .mcp_smoke import smoke_test_mcp
from .nonvision_acceptance import run_nonvision_acceptance
from .probe_scan import scan_debug_probes
from .replay import replay_handoff
from .runner import (
    AiDebugSession,
    AutoDebugSession,
    BuildRepairSession,
    ClosedLoopSession,
    DebugSequenceSession,
    FirstPhaseAcceptance,
    execute_debug_operation,
)
from .skill_bootstrap import bootstrap_skill_environment
from .skill_install import install_skill
from .target_validation import validate_debug_target
from .workflow_plan import plan_workflow
from .workflow_run import run_workflow
from .workspace import init_workspace_config, load_workspace_defaults, workspace_status


def main() -> int:
    _configure_utf8_stdout()
    parser = argparse.ArgumentParser(description="AI MCU debug automation")
    subparsers = parser.add_subparsers(dest="command", required=True)

    doctor_parser = subparsers.add_parser("doctor")
    doctor_parser.add_argument("--debug-backend")
    doctor_parser.add_argument("--build-backend")
    subparsers.add_parser("probe-scan")
    subparsers.add_parser("mcp-server")

    mcp_config_parser = subparsers.add_parser("mcp-config")
    mcp_config_parser.add_argument("--client", choices=["codex", "generic-json", "claude-desktop"], default="codex")
    mcp_config_parser.add_argument("--project", default=".")
    mcp_config_parser.add_argument("--python-executable")
    mcp_config_parser.add_argument("--server-name", default="ai_mcu_debug")
    mcp_config_parser.add_argument("--output")

    mcp_smoke_parser = subparsers.add_parser("mcp-smoke")
    mcp_smoke_parser.add_argument("--project", default=".")
    mcp_smoke_parser.add_argument("--python-executable")
    mcp_smoke_parser.add_argument("--required-tool", action="append", default=[])
    mcp_smoke_parser.add_argument("--timeout-s", type=float, default=10.0)
    mcp_smoke_parser.add_argument("--output")

    skill_bootstrap_parser = subparsers.add_parser("skill-bootstrap")
    skill_bootstrap_parser.add_argument("--project", default=".")
    skill_bootstrap_parser.add_argument("--source")
    skill_bootstrap_parser.add_argument("--destination")
    skill_bootstrap_parser.add_argument("--codex-home")
    skill_bootstrap_parser.add_argument("--skill-name", default="mcu-auto-debug")
    skill_bootstrap_parser.add_argument("--client", choices=["codex", "generic-json", "claude-desktop"], default="codex")
    skill_bootstrap_parser.add_argument("--python-executable")
    skill_bootstrap_parser.add_argument("--server-name", default="ai_mcu_debug")
    skill_bootstrap_parser.add_argument("--config-output")
    skill_bootstrap_parser.add_argument("--report-output")
    skill_bootstrap_parser.add_argument("--dry-run", action="store_true")
    skill_bootstrap_parser.add_argument("--force", action="store_true")
    skill_bootstrap_parser.add_argument("--skip-install", action="store_true")
    skill_bootstrap_parser.add_argument("--skip-smoke", action="store_true")
    skill_bootstrap_parser.add_argument("--include-vision", action="store_true")
    skill_bootstrap_parser.add_argument("--timeout-s", type=float, default=10.0)

    install_skill_parser = subparsers.add_parser("install-skill")
    install_skill_parser.add_argument("--source")
    install_skill_parser.add_argument("--destination")
    install_skill_parser.add_argument("--codex-home")
    install_skill_parser.add_argument("--skill-name", default="mcu-auto-debug")
    install_skill_parser.add_argument("--dry-run", action="store_true")
    install_skill_parser.add_argument("--force", action="store_true")

    workflow_plan_parser = subparsers.add_parser("workflow-plan")
    workflow_plan_parser.add_argument("--project", default=".")
    workflow_plan_parser.add_argument("--context", default="examples/mcu_context.json")
    workflow_plan_parser.add_argument("--workspace-config", default=".embeddedskills/config.json")
    workflow_plan_parser.add_argument("--chip")
    workflow_plan_parser.add_argument("--svd")
    workflow_plan_parser.add_argument("--linker")
    workflow_plan_parser.add_argument("--startup")
    workflow_plan_parser.add_argument("--doc", action="append", default=[])
    workflow_plan_parser.add_argument("--doc-repo", action="append", default=[])

    workflow_run_parser = subparsers.add_parser("workflow-run")
    workflow_run_parser.add_argument("--project", default=".")
    workflow_run_parser.add_argument("--context", default="examples/mcu_context.json")
    workflow_run_parser.add_argument("--workspace-config", default=".embeddedskills/config.json")
    workflow_run_parser.add_argument("--report-dir", default="debug_runs/workflow_run")
    workflow_run_parser.add_argument("--chip")
    workflow_run_parser.add_argument("--svd")
    workflow_run_parser.add_argument("--linker")
    workflow_run_parser.add_argument("--startup")
    workflow_run_parser.add_argument("--doc", action="append", default=[])
    workflow_run_parser.add_argument("--doc-repo", action="append", default=[])
    workflow_run_parser.add_argument("--max-steps", type=int, default=8)
    workflow_run_parser.add_argument("--no-file-writes", action="store_true")
    workflow_run_parser.add_argument("--no-hardware", action="store_true")
    workflow_run_parser.add_argument("--continue-on-failure", action="store_true")

    capability_audit_parser = subparsers.add_parser("capability-audit")
    capability_audit_parser.add_argument("--project", default=".")
    capability_audit_parser.add_argument("--include-vision", action="store_true")
    capability_audit_parser.add_argument("--output")

    init_workspace_parser = subparsers.add_parser("init-workspace")
    init_workspace_parser.add_argument("--output-dir", default=".embeddedskills")
    init_workspace_parser.add_argument("--project", default=".")
    init_workspace_parser.add_argument("--chip")
    init_workspace_parser.add_argument("--context")
    init_workspace_parser.add_argument("--svd")
    init_workspace_parser.add_argument("--linker")
    init_workspace_parser.add_argument("--startup")
    init_workspace_parser.add_argument("--board")
    init_workspace_parser.add_argument("--package")
    init_workspace_parser.add_argument("--knowledge-repo-url")
    init_workspace_parser.add_argument("--knowledge-repo-path")
    init_workspace_parser.add_argument("--build-config")
    init_workspace_parser.add_argument("--build-backend")
    init_workspace_parser.add_argument("--pio-env")
    init_workspace_parser.add_argument("--keil-project")
    init_workspace_parser.add_argument("--keil-target")
    init_workspace_parser.add_argument("--uv4")
    init_workspace_parser.add_argument("--target")
    init_workspace_parser.add_argument("--task")
    init_workspace_parser.add_argument("--debug-backend")
    init_workspace_parser.add_argument("--executable")
    init_workspace_parser.add_argument("--interface")
    init_workspace_parser.add_argument("--target-cfg")
    init_workspace_parser.add_argument("--transport", default="swd")
    init_workspace_parser.add_argument("--adapter-speed", type=int, default=100)
    init_workspace_parser.add_argument("--no-generate-templates", action="store_true")
    init_workspace_parser.add_argument("--force", action="store_true")

    setup_parser = subparsers.add_parser("setup-project")
    setup_parser.add_argument("--output-dir", default=".embeddedskills")
    setup_parser.add_argument("--project", default=".")
    setup_parser.add_argument("--context", default="examples/mcu_context.json")
    setup_parser.add_argument("--chip")
    setup_parser.add_argument("--svd")
    setup_parser.add_argument("--linker")
    setup_parser.add_argument("--startup")
    setup_parser.add_argument("--board")
    setup_parser.add_argument("--package")
    setup_parser.add_argument("--doc", action="append", default=[])
    setup_parser.add_argument("--doc-repo", action="append", default=[])
    setup_parser.add_argument("--knowledge-repo-url")
    setup_parser.add_argument("--knowledge-repo-path")
    setup_parser.add_argument("--build-config")
    setup_parser.add_argument("--build-backend")
    setup_parser.add_argument("--pio-env")
    setup_parser.add_argument("--keil-project")
    setup_parser.add_argument("--keil-target")
    setup_parser.add_argument("--uv4")
    setup_parser.add_argument("--target")
    setup_parser.add_argument("--task")
    setup_parser.add_argument("--debug-backend")
    setup_parser.add_argument("--executable")
    setup_parser.add_argument("--interface")
    setup_parser.add_argument("--target-cfg")
    setup_parser.add_argument("--transport", default="swd")
    setup_parser.add_argument("--adapter-speed", type=int, default=100)
    setup_parser.add_argument("--no-scan-probes", action="store_true")
    setup_parser.add_argument("--force", action="store_true")

    accept_nonvision_parser = subparsers.add_parser("accept-nonvision")
    accept_nonvision_parser.add_argument("--output-dir", default=".embeddedskills")
    accept_nonvision_parser.add_argument("--project", default=".")
    accept_nonvision_parser.add_argument("--context", default="examples/mcu_context.json")
    accept_nonvision_parser.add_argument("--report-dir", default="debug_runs/nonvision_acceptance")
    accept_nonvision_parser.add_argument("--handoff-output")
    accept_nonvision_parser.add_argument("--handoff-project", default=".")
    accept_nonvision_parser.add_argument("--zip-handoff", action="store_true")
    accept_nonvision_parser.add_argument("--chip")
    accept_nonvision_parser.add_argument("--svd")
    accept_nonvision_parser.add_argument("--linker")
    accept_nonvision_parser.add_argument("--startup")
    accept_nonvision_parser.add_argument("--board")
    accept_nonvision_parser.add_argument("--package")
    accept_nonvision_parser.add_argument("--doc", action="append", default=[])
    accept_nonvision_parser.add_argument("--doc-repo", action="append", default=[])
    accept_nonvision_parser.add_argument("--knowledge-repo-url")
    accept_nonvision_parser.add_argument("--knowledge-repo-path")
    accept_nonvision_parser.add_argument("--build-config")
    accept_nonvision_parser.add_argument("--build-backend")
    accept_nonvision_parser.add_argument("--pio-env")
    accept_nonvision_parser.add_argument("--keil-project")
    accept_nonvision_parser.add_argument("--keil-target")
    accept_nonvision_parser.add_argument("--uv4")
    accept_nonvision_parser.add_argument("--target")
    accept_nonvision_parser.add_argument("--task")
    accept_nonvision_parser.add_argument("--debug-backend")
    accept_nonvision_parser.add_argument("--executable")
    accept_nonvision_parser.add_argument("--interface")
    accept_nonvision_parser.add_argument("--target-cfg")
    accept_nonvision_parser.add_argument("--transport", default="swd")
    accept_nonvision_parser.add_argument("--adapter-speed", type=int, default=100)
    accept_nonvision_parser.add_argument("--no-scan-probes", action="store_true")
    accept_nonvision_parser.add_argument("--force", action="store_true")

    workspace_status_parser = subparsers.add_parser("workspace-status")
    workspace_status_parser.add_argument("--config", default=".embeddedskills/config.json")

    validate_target_parser = subparsers.add_parser("validate-target")
    validate_target_parser.add_argument("--target", required=True)
    validate_target_parser.add_argument("--scan-probes", action="store_true")

    hardware_id_parser = subparsers.add_parser("hardware-id")
    hardware_id_parser.add_argument("--target", default="examples/debug.target.json")
    hardware_id_parser.add_argument("--chip")
    hardware_id_parser.add_argument("--report-dir", default="debug_runs/hardware_identity")
    hardware_id_parser.add_argument("--no-halt", action="store_true")

    connection_diag_parser = subparsers.add_parser("connection-diagnose")
    connection_diag_parser.add_argument("--target", required=True)
    connection_diag_parser.add_argument("--report-dir", default="debug_runs/connection_diagnostics")
    connection_diag_parser.add_argument("--timeout-s", type=float, default=12.0)

    elf_parser = subparsers.add_parser("elf-check")
    elf_parser.add_argument("--elf", required=True)

    context_parser = subparsers.add_parser("build-mcu-context")
    context_parser.add_argument("--chip", required=True)
    context_parser.add_argument("--svd", required=True)
    context_parser.add_argument("--output", default="examples/mcu_context.json")
    context_parser.add_argument("--linker")
    context_parser.add_argument("--startup")
    context_parser.add_argument("--board")
    context_parser.add_argument("--package")
    context_parser.add_argument(
        "--doc",
        action="append",
        default=[],
        help="Document in kind=path form, for example datasheet=docs/chip.txt",
    )

    resolve_parser = subparsers.add_parser("resolve-chip")
    resolve_parser.add_argument("--project", default=".")
    resolve_parser.add_argument("--chip")
    resolve_parser.add_argument("--svd")
    resolve_parser.add_argument("--linker")
    resolve_parser.add_argument("--startup")
    resolve_parser.add_argument("--target")

    locate_parser = subparsers.add_parser("locate-docs")
    locate_parser.add_argument("--project", default=".")
    locate_parser.add_argument("--chip")
    locate_parser.add_argument("--svd")
    locate_parser.add_argument("--linker")
    locate_parser.add_argument("--startup")
    locate_parser.add_argument("--doc", action="append", default=[])
    locate_parser.add_argument("--doc-repo", action="append", default=[])

    doc_intake_parser = subparsers.add_parser("doc-intake")
    doc_intake_parser.add_argument("--project", default=".")
    doc_intake_parser.add_argument("--chip")
    doc_intake_parser.add_argument("--svd")
    doc_intake_parser.add_argument("--linker")
    doc_intake_parser.add_argument("--startup")
    doc_intake_parser.add_argument("--doc", action="append", default=[])
    doc_intake_parser.add_argument("--doc-repo", action="append", default=[])
    doc_intake_parser.add_argument("--output", default="examples/mcu_context.json")

    profile_parser = subparsers.add_parser("mcu-profile")
    profile_parser.add_argument("--chip")

    manifest_lint_parser = subparsers.add_parser("manifest-lint")
    manifest_lint_parser.add_argument("--manifest", required=True)
    manifest_lint_parser.add_argument("--chip")
    manifest_lint_parser.add_argument("--strict-hashes", action="store_true")

    doc_repo_parser = subparsers.add_parser("doc-repo-sync")
    doc_repo_parser.add_argument("--url")
    doc_repo_parser.add_argument("--local-path")
    doc_repo_parser.add_argument("--ref")
    doc_repo_parser.add_argument("--no-update", action="store_true")

    discover_parser = subparsers.add_parser("discover-docs")
    discover_parser.add_argument("--chip", required=True)
    discover_parser.add_argument("--vendor")
    discover_parser.add_argument("--no-cmsis-pack", action="store_true")

    fetch_parser = subparsers.add_parser("fetch-docs")
    fetch_parser.add_argument("--chip")
    fetch_parser.add_argument("--manifest", required=True)
    fetch_parser.add_argument(
        "--url",
        action="append",
        default=[],
        help="Document URL in kind=url form, for example datasheet=https://vendor/chip.pdf",
    )
    fetch_parser.add_argument("--timeout-s", type=float, default=30.0)

    ingest_parser = subparsers.add_parser("ingest-docs")
    ingest_parser.add_argument("--manifest", required=True)
    ingest_parser.add_argument("--output", default="examples/mcu_context.json")
    ingest_parser.add_argument("--chip")
    ingest_parser.add_argument("--svd")
    ingest_parser.add_argument("--linker")
    ingest_parser.add_argument("--startup")
    ingest_parser.add_argument("--board")
    ingest_parser.add_argument("--package")

    check_context_parser = subparsers.add_parser("check-context")
    check_context_parser.add_argument("--context", required=True)

    prepare_parser = subparsers.add_parser("prepare-mcu")
    prepare_parser.add_argument("--project", default=".")
    prepare_parser.add_argument("--output", default="examples/mcu_context.json")
    prepare_parser.add_argument("--chip")
    prepare_parser.add_argument("--svd")
    prepare_parser.add_argument("--linker")
    prepare_parser.add_argument("--startup")
    prepare_parser.add_argument("--board")
    prepare_parser.add_argument("--package")
    prepare_parser.add_argument("--doc", action="append", default=[])
    prepare_parser.add_argument("--doc-repo", action="append", default=[])

    query_parser = subparsers.add_parser("knowledge-query")
    query_parser.add_argument("--context", default="examples/mcu_context.json")
    query_parser.add_argument("--query", required=True)
    query_parser.add_argument("--limit", type=int, default=5)
    query_parser.add_argument("--mode", choices=["keyword", "vector"], default="keyword")

    explain_parser = subparsers.add_parser("explain-register")
    explain_parser.add_argument("--context", default="examples/mcu_context.json")
    explain_parser.add_argument("--register", required=True)

    validate_reg_parser = subparsers.add_parser("validate-register-write")
    validate_reg_parser.add_argument("--context", default="examples/mcu_context.json")
    validate_reg_parser.add_argument("--register", required=True)
    validate_reg_parser.add_argument("--value", required=True)

    validate_addr_parser = subparsers.add_parser("validate-address-write")
    validate_addr_parser.add_argument("--context", default="examples/mcu_context.json")
    validate_addr_parser.add_argument("--address", required=True)
    validate_addr_parser.add_argument("--length", type=int, required=True)

    doc_parser = subparsers.add_parser("write-mcu-debug-doc")
    doc_parser.add_argument("--context", default="examples/mcu_context.json")
    doc_parser.add_argument("--output", default="docs/MCU_DEBUG_RECORD.md")

    compare_parser = subparsers.add_parser("compare-debug-report")
    compare_parser.add_argument("--context", default="examples/mcu_context.json")
    compare_parser.add_argument("--report", required=True)
    compare_parser.add_argument("--output")

    analyze_parser = subparsers.add_parser("analyze-debug-report")
    analyze_parser.add_argument("--context", default="examples/mcu_context.json")
    analyze_parser.add_argument("--report", required=True)
    analyze_parser.add_argument("--output")

    config_parser = subparsers.add_parser("make-openocd-target")
    config_parser.add_argument("--output", default="examples/debug.target.openocd.local.json")
    config_parser.add_argument("--executable", default="build/firmware.elf")
    config_parser.add_argument("--interface", default="interface/stlink.cfg")
    config_parser.add_argument("--target-cfg", default="target/stm32f1x.cfg")
    config_parser.add_argument("--remote", default="localhost:3333")

    build_parser = subparsers.add_parser("build")
    build_parser.add_argument("--config", default="examples/build.cmake.json")

    flash_parser = subparsers.add_parser("flash")
    flash_parser.add_argument("--config", default="examples/build.cmake.json")

    repair_parser = subparsers.add_parser("repair-build")
    repair_parser.add_argument("--config", default="examples/build.cmake.json")

    smoke_parser = subparsers.add_parser("smoke-test")
    smoke_parser.add_argument("--config", default="examples/build.cmake.json")

    runtime_log_parser = subparsers.add_parser("runtime-log")
    runtime_log_parser.add_argument("--config", default="examples/build.cmake.json")

    loop_parser = subparsers.add_parser("closed-loop")
    loop_parser.add_argument("--build-config", default="examples/build.cmake.json")
    loop_parser.add_argument("--target")
    loop_parser.add_argument("--task")
    loop_parser.add_argument("--report-dir", default="debug_runs")

    debug_parser = subparsers.add_parser("debug")
    debug_parser.add_argument("--target", default="examples/debug.target.json")
    debug_parser.add_argument("--task", default="examples/debug_task.json")
    debug_parser.add_argument("--report-dir", default="debug_runs")

    accept_parser = subparsers.add_parser("accept-first-stage")
    accept_parser.add_argument("--target", default="examples/debug.target.json")
    accept_parser.add_argument("--task", default="examples/debug_task.json")
    accept_parser.add_argument("--report-dir", default="debug_runs")

    sequence_parser = subparsers.add_parser("debug-sequence")
    sequence_parser.add_argument("--target", default="examples/debug.target.json")
    sequence_parser.add_argument("--sequence", default="examples/debug_sequence.json")
    sequence_parser.add_argument("--report-dir", default="debug_runs")

    op_parser = subparsers.add_parser("debug-op")
    op_parser.add_argument("--target", default="examples/debug.target.json")
    op_parser.add_argument(
        "operation",
        choices=[
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
    op_parser.add_argument("--register")
    op_parser.add_argument("--value")
    op_parser.add_argument("--address")
    op_parser.add_argument("--length", type=int)
    op_parser.add_argument("--data-hex")
    op_parser.add_argument("--location")
    op_parser.add_argument("--breakpoint-id")
    op_parser.add_argument("--timeout-s", type=float, default=10.0)
    op_parser.add_argument("--run-after-reset", action="store_true")
    op_parser.add_argument("--context")
    op_parser.add_argument("--force", action="store_true")

    ai_debug_parser = subparsers.add_parser("ai-debug")
    ai_debug_parser.add_argument("--project")
    ai_debug_parser.add_argument("--mode", choices=["dry-run", "read-only", "run"], default="dry-run")
    ai_debug_parser.add_argument("--context")
    ai_debug_parser.add_argument("--chip")
    ai_debug_parser.add_argument("--svd")
    ai_debug_parser.add_argument("--linker")
    ai_debug_parser.add_argument("--startup")
    ai_debug_parser.add_argument("--board")
    ai_debug_parser.add_argument("--package")
    ai_debug_parser.add_argument("--doc", action="append", default=[])
    ai_debug_parser.add_argument("--doc-repo", action="append", default=[])
    ai_debug_parser.add_argument("--build-config")
    ai_debug_parser.add_argument("--target")
    ai_debug_parser.add_argument("--task")
    ai_debug_parser.add_argument("--report-dir", default="debug_runs/ai_debug")
    ai_debug_parser.add_argument("--workspace-config", default=".embeddedskills/config.json")
    ai_debug_parser.add_argument("--allow-flash", action="store_true")
    ai_debug_parser.add_argument("--allow-repair", action="store_true")
    ai_debug_parser.add_argument("--max-repair-iterations", type=int)
    ai_debug_parser.add_argument("--connection-diagnostic-timeout-s", type=float, default=12.0)

    export_parser = subparsers.add_parser("export-handoff")
    export_parser.add_argument("--output", default="debug_runs/handoff")
    export_parser.add_argument("--project", default=".")
    export_parser.add_argument("--workspace-config", default=".embeddedskills/config.json")
    export_parser.add_argument("--report-dir")
    export_parser.add_argument("--include-glob", action="append", default=[])
    export_parser.add_argument("--zip", action="store_true")

    replay_parser = subparsers.add_parser("replay-handoff")
    replay_parser.add_argument("--manifest", required=True)
    replay_parser.add_argument("--project", default=".")
    replay_parser.add_argument("--output")
    replay_parser.add_argument("--execute", action="store_true")
    replay_parser.add_argument("--timeout-s", type=float, default=120.0)
    replay_parser.add_argument("--continue-on-failure", action="store_true")

    args = parser.parse_args()

    if args.command == "doctor":
        report = run_doctor(debug_backend=args.debug_backend, build_backend=args.build_backend)
        print(json.dumps(report, indent=2, ensure_ascii=False))
        return 0 if report.get("ok") else 1

    if args.command == "probe-scan":
        report = scan_debug_probes()
        print(json.dumps(report, indent=2, ensure_ascii=False))
        return 0 if report.get("ok") else 1

    if args.command == "mcp-server":
        from .mcp_server import main as run_mcp_server

        return run_mcp_server()

    if args.command == "mcp-config":
        report = generate_mcp_config(
            project_path=Path(args.project),
            client=args.client,
            python_executable=args.python_executable,
            server_name=args.server_name,
            output=Path(args.output) if args.output else None,
        )
        print(json.dumps(report, indent=2, ensure_ascii=False, default=str))
        return 0 if report.get("ok") else 1

    if args.command == "mcp-smoke":
        report = smoke_test_mcp(
            project_path=Path(args.project),
            python_executable=args.python_executable,
            required_tools=args.required_tool or None,
            timeout_s=args.timeout_s,
            output=Path(args.output) if args.output else None,
        )
        print(json.dumps(report, indent=2, ensure_ascii=False, default=str))
        return 0 if report.get("ok") else 1

    if args.command == "skill-bootstrap":
        report = bootstrap_skill_environment(
            project_path=Path(args.project),
            source=Path(args.source) if args.source else None,
            destination=Path(args.destination) if args.destination else None,
            codex_home=Path(args.codex_home) if args.codex_home else None,
            skill_name=args.skill_name,
            client=args.client,
            python_executable=args.python_executable,
            server_name=args.server_name,
            config_output=Path(args.config_output) if args.config_output else None,
            report_output=Path(args.report_output) if args.report_output else None,
            dry_run=args.dry_run,
            force=args.force,
            skip_install=args.skip_install,
            skip_smoke=args.skip_smoke,
            include_vision=args.include_vision,
            timeout_s=args.timeout_s,
        )
        print(json.dumps(report, indent=2, ensure_ascii=False, default=str))
        return 0 if report.get("ok") else 1

    if args.command == "install-skill":
        report = install_skill(
            source=Path(args.source) if args.source else None,
            destination=Path(args.destination) if args.destination else None,
            codex_home=Path(args.codex_home) if args.codex_home else None,
            skill_name=args.skill_name,
            dry_run=args.dry_run,
            force=args.force,
        )
        print(json.dumps(report, indent=2, ensure_ascii=False))
        return 0 if report.get("ok") else 1

    if args.command == "workflow-plan":
        report = plan_workflow(
            project_path=Path(args.project),
            context_path=Path(args.context),
            workspace_config=Path(args.workspace_config),
            chip=args.chip,
            svd_path=Path(args.svd) if args.svd else None,
            linker_path=Path(args.linker) if args.linker else None,
            startup_path=Path(args.startup) if args.startup else None,
            extra_docs=_parse_doc_args(args.doc),
            doc_repo_paths=_doc_repo_paths(args.doc_repo),
        )
        print(json.dumps(report, indent=2, ensure_ascii=False))
        return 0 if report.get("status") else 1

    if args.command == "workflow-run":
        report = run_workflow(
            project_path=Path(args.project),
            context_path=Path(args.context),
            workspace_config=Path(args.workspace_config),
            report_dir=Path(args.report_dir),
            chip=args.chip,
            svd_path=Path(args.svd) if args.svd else None,
            linker_path=Path(args.linker) if args.linker else None,
            startup_path=Path(args.startup) if args.startup else None,
            extra_docs=_parse_doc_args(args.doc),
            doc_repo_paths=_doc_repo_paths(args.doc_repo),
            max_steps=args.max_steps,
            allow_file_writes=not args.no_file_writes,
            allow_hardware=not args.no_hardware,
            stop_on_failure=not args.continue_on_failure,
        )
        print(json.dumps(report, indent=2, ensure_ascii=False, default=str))
        return 0 if report.get("ok") else 1

    if args.command == "capability-audit":
        report = audit_capabilities(
            project_path=Path(args.project),
            include_vision=args.include_vision,
            output=Path(args.output) if args.output else None,
        )
        print(json.dumps(report, indent=2, ensure_ascii=False, default=str))
        return 0 if report.get("ok") else 1

    if args.command == "init-workspace":
        probe_report = None if args.interface or args.no_generate_templates else scan_debug_probes()
        doctor_report = None if args.no_generate_templates else run_doctor()
        report = init_workspace_config(
            output_dir=Path(args.output_dir),
            project_path=Path(args.project),
            chip=args.chip,
            context_path=Path(args.context) if args.context else None,
            svd_path=Path(args.svd) if args.svd else None,
            linker_path=Path(args.linker) if args.linker else None,
            startup_path=Path(args.startup) if args.startup else None,
            board=args.board,
            package_name=args.package,
            knowledge_repo_url=args.knowledge_repo_url,
            knowledge_repo_path=Path(args.knowledge_repo_path) if args.knowledge_repo_path else None,
            build_config_path=Path(args.build_config) if args.build_config else None,
            build_backend=args.build_backend,
            pio_env=args.pio_env,
            keil_project=Path(args.keil_project) if args.keil_project else None,
            keil_target=args.keil_target,
            uv4_path=Path(args.uv4) if args.uv4 else None,
            target_path=Path(args.target) if args.target else None,
            task_path=Path(args.task) if args.task else None,
            debug_backend=args.debug_backend,
            executable_path=Path(args.executable) if args.executable else None,
            interface_cfg=args.interface,
            target_cfg=args.target_cfg,
            transport=args.transport,
            adapter_speed=args.adapter_speed,
            generate_templates=not args.no_generate_templates,
            doctor_report=doctor_report,
            probe_report=probe_report,
            force=args.force,
        )
        if probe_report is not None:
            report["probe_scan"] = probe_report
        if doctor_report is not None:
            report["doctor"] = doctor_report
        print(json.dumps(report, indent=2, ensure_ascii=False))
        return 0 if report.get("ok") else 1

    if args.command == "setup-project":
        report = setup_project(
            output_dir=Path(args.output_dir),
            project_path=Path(args.project),
            context_path=Path(args.context),
            chip=args.chip,
            svd_path=Path(args.svd) if args.svd else None,
            linker_path=Path(args.linker) if args.linker else None,
            startup_path=Path(args.startup) if args.startup else None,
            board=args.board,
            package_name=args.package,
            extra_docs=_parse_doc_args(args.doc),
            doc_repo_paths=_doc_repo_paths(args.doc_repo),
            knowledge_repo_url=args.knowledge_repo_url,
            knowledge_repo_path=Path(args.knowledge_repo_path) if args.knowledge_repo_path else None,
            build_config_path=Path(args.build_config) if args.build_config else None,
            build_backend=args.build_backend,
            pio_env=args.pio_env,
            keil_project=Path(args.keil_project) if args.keil_project else None,
            keil_target=args.keil_target,
            uv4_path=Path(args.uv4) if args.uv4 else None,
            target_path=Path(args.target) if args.target else None,
            task_path=Path(args.task) if args.task else None,
            debug_backend=args.debug_backend,
            executable_path=Path(args.executable) if args.executable else None,
            interface_cfg=args.interface,
            target_cfg=args.target_cfg,
            transport=args.transport,
            adapter_speed=args.adapter_speed,
            scan_probes=not args.no_scan_probes,
            force=args.force,
        )
        print(json.dumps(report, indent=2, ensure_ascii=False))
        return 0 if report.get("ok") else 1

    if args.command == "accept-nonvision":
        report = run_nonvision_acceptance(
            output_dir=Path(args.output_dir),
            project_path=Path(args.project),
            context_path=Path(args.context),
            report_dir=Path(args.report_dir),
            handoff_output=Path(args.handoff_output) if args.handoff_output else None,
            handoff_project_path=Path(args.handoff_project),
            zip_handoff=args.zip_handoff,
            chip=args.chip,
            svd_path=Path(args.svd) if args.svd else None,
            linker_path=Path(args.linker) if args.linker else None,
            startup_path=Path(args.startup) if args.startup else None,
            board=args.board,
            package_name=args.package,
            extra_docs=_parse_doc_args(args.doc),
            doc_repo_paths=_doc_repo_paths(args.doc_repo),
            knowledge_repo_url=args.knowledge_repo_url,
            knowledge_repo_path=Path(args.knowledge_repo_path) if args.knowledge_repo_path else None,
            build_config_path=Path(args.build_config) if args.build_config else None,
            build_backend=args.build_backend,
            pio_env=args.pio_env,
            keil_project=Path(args.keil_project) if args.keil_project else None,
            keil_target=args.keil_target,
            uv4_path=Path(args.uv4) if args.uv4 else None,
            target_path=Path(args.target) if args.target else None,
            task_path=Path(args.task) if args.task else None,
            debug_backend=args.debug_backend,
            executable_path=Path(args.executable) if args.executable else None,
            interface_cfg=args.interface,
            target_cfg=args.target_cfg,
            transport=args.transport,
            adapter_speed=args.adapter_speed,
            scan_probes=not args.no_scan_probes,
            force=args.force,
        )
        print(json.dumps(report, indent=2, ensure_ascii=False))
        return 0 if report.get("ok") else 1

    if args.command == "workspace-status":
        report = workspace_status(Path(args.config))
        print(json.dumps(report, indent=2, ensure_ascii=False))
        return 0 if report.get("ok") else 1

    if args.command == "validate-target":
        probe_report = scan_debug_probes() if args.scan_probes else None
        report = validate_debug_target(Path(args.target), probe_report=probe_report)
        if probe_report is not None:
            report["probe_scan"] = probe_report
        print(json.dumps(report, indent=2, ensure_ascii=False))
        return 0 if report.get("ok") else 1

    if args.command == "hardware-id":
        target = load_target_config(Path(args.target))
        report = read_hardware_identity(
            create_debug_adapter(target),
            report_dir=Path(args.report_dir),
            expected_chip=args.chip,
            halt=not args.no_halt,
        )
        print(json.dumps(report, indent=2, ensure_ascii=False))
        return 0 if report.get("ok") else 1

    if args.command == "connection-diagnose":
        report = run_openocd_connection_matrix(
            load_target_config(Path(args.target)),
            report_dir=Path(args.report_dir),
            timeout_s=args.timeout_s,
        )
        print(json.dumps(report, indent=2, ensure_ascii=False))
        return 0 if report.get("ok") else 1

    if args.command == "elf-check":
        report = check_elf(Path(args.elf))
        print(json.dumps(report, indent=2, ensure_ascii=False))
        return 0 if report.get("ok") else 1

    if args.command == "build-mcu-context":
        context = build_mcu_context(
            chip=args.chip,
            svd_path=Path(args.svd),
            output_path=Path(args.output),
            linker_path=Path(args.linker) if args.linker else None,
            startup_path=Path(args.startup) if args.startup else None,
            documents=_parse_doc_args(args.doc),
            board=args.board,
            package_name=args.package,
        )
        print(json.dumps({"ok": True, "output": args.output, "registers": len(context["register_index"])}, indent=2))
        return 0

    if args.command == "resolve-chip":
        report = resolve_chip(
            project_path=Path(args.project),
            chip=args.chip,
            svd_path=Path(args.svd) if args.svd else None,
            linker_path=Path(args.linker) if args.linker else None,
            startup_path=Path(args.startup) if args.startup else None,
            target_path=Path(args.target) if args.target else None,
        )
        print(json.dumps(report, indent=2, ensure_ascii=False))
        return 0 if report.get("ok") else 1

    if args.command == "locate-docs":
        doc_repo_paths = _doc_repo_paths(args.doc_repo)
        report = locate_docs(
            project_path=Path(args.project),
            chip=args.chip,
            svd_path=Path(args.svd) if args.svd else None,
            linker_path=Path(args.linker) if args.linker else None,
            startup_path=Path(args.startup) if args.startup else None,
            extra_docs=_parse_doc_args(args.doc),
            doc_repo_paths=doc_repo_paths,
        )
        print(json.dumps(report, indent=2, ensure_ascii=False))
        return 0 if report.get("ok") else 1

    if args.command == "doc-intake":
        doc_repo_paths = _doc_repo_paths(args.doc_repo)
        report = plan_document_intake(
            project_path=Path(args.project),
            chip=args.chip,
            svd_path=Path(args.svd) if args.svd else None,
            linker_path=Path(args.linker) if args.linker else None,
            startup_path=Path(args.startup) if args.startup else None,
            extra_docs=_parse_doc_args(args.doc),
            doc_repo_paths=doc_repo_paths,
            output_path=Path(args.output),
        )
        print(json.dumps(report, indent=2, ensure_ascii=False))
        return 0 if report.get("ok") else 1

    if args.command == "mcu-profile":
        report = {
            "ok": True,
            "chip": args.chip,
            "profile": profile_for_chip(args.chip),
            "manifest_template": manifest_template(args.chip),
            "policy": {
                "web_search_allowed": False,
                "template_requires_user_sources": True,
            },
        }
        print(json.dumps(report, indent=2, ensure_ascii=False))
        return 0

    if args.command == "manifest-lint":
        report = lint_manifest(Path(args.manifest), chip=args.chip, strict_hashes=args.strict_hashes)
        print(json.dumps(report, indent=2, ensure_ascii=False))
        return 0 if report.get("ok") else 1

    if args.command == "doc-repo-sync":
        workspace_defaults = load_workspace_defaults()
        url = args.url or workspace_defaults.get("knowledge_repo_url")
        local_path = Path(args.local_path or workspace_defaults.get("knowledge_repo_path") or "knowledge_repos/mcu-docs")
        report = sync_doc_repo(
            url=url,
            local_path=local_path,
            ref=args.ref,
            update=not args.no_update,
        )
        print(json.dumps(report, indent=2, ensure_ascii=False))
        return 0 if report.get("ok") else 1

    if args.command == "discover-docs":
        report = discover_docs(
            chip=args.chip,
            vendor=args.vendor,
            include_cmsis_pack=not args.no_cmsis_pack,
        )
        print(json.dumps(report, indent=2, ensure_ascii=False))
        return 0 if report.get("ok") else 1

    if args.command == "fetch-docs":
        report = fetch_docs(
            chip=args.chip,
            urls=_parse_url_args(args.url),
            manifest_path=Path(args.manifest),
            timeout_s=args.timeout_s,
        )
        print(json.dumps(report, indent=2, ensure_ascii=False))
        return 0 if report.get("ok") else 1

    if args.command == "ingest-docs":
        report = ingest_docs(
            manifest_path=Path(args.manifest),
            output_path=Path(args.output),
            chip=args.chip,
            svd_path=Path(args.svd) if args.svd else None,
            linker_path=Path(args.linker) if args.linker else None,
            startup_path=Path(args.startup) if args.startup else None,
            board=args.board,
            package_name=args.package,
        )
        print(json.dumps(report, indent=2, ensure_ascii=False))
        return 0 if report.get("ok") else 1

    if args.command == "check-context":
        report = check_context(Path(args.context))
        print(json.dumps(report, indent=2, ensure_ascii=False))
        return 0 if report.get("ok") else 1

    if args.command == "prepare-mcu":
        doc_repo_paths = _doc_repo_paths(args.doc_repo)
        report = prepare_mcu(
            project_path=Path(args.project),
            output_path=Path(args.output),
            chip=args.chip,
            svd_path=Path(args.svd) if args.svd else None,
            linker_path=Path(args.linker) if args.linker else None,
            startup_path=Path(args.startup) if args.startup else None,
            board=args.board,
            package_name=args.package,
            extra_docs=_parse_doc_args(args.doc),
            doc_repo_paths=doc_repo_paths,
        )
        print(json.dumps(report, indent=2, ensure_ascii=False))
        return 0 if report.get("ok") else 1

    if args.command == "knowledge-query":
        adapter = JsonKnowledgeAdapter(Path(args.context))
        if args.mode == "vector":
            hits = adapter.vector_search(args.query, args.limit)
        else:
            hits = adapter.search(args.query, args.limit)
        print(json.dumps(hits, indent=2, ensure_ascii=False))
        return 0

    if args.command == "explain-register":
        adapter = JsonKnowledgeAdapter(Path(args.context))
        report = adapter.explain_register(args.register)
        print(json.dumps(report, indent=2, ensure_ascii=False))
        return 0 if report.get("ok") else 1

    if args.command == "validate-register-write":
        adapter = JsonKnowledgeAdapter(Path(args.context))
        report = adapter.validate_register_write(args.register, int(args.value, 0))
        print(json.dumps(report, indent=2, ensure_ascii=False))
        return 0 if report.get("ok") else 1

    if args.command == "validate-address-write":
        adapter = JsonKnowledgeAdapter(Path(args.context))
        report = adapter.validate_address_write(int(args.address, 0), args.length)
        print(json.dumps(report, indent=2, ensure_ascii=False))
        return 0 if report.get("ok") else 1

    if args.command == "write-mcu-debug-doc":
        report = write_mcu_debug_doc(Path(args.context), Path(args.output))
        print(json.dumps(report, indent=2, ensure_ascii=False))
        return 0 if report.get("ok") else 1

    if args.command in {"compare-debug-report", "analyze-debug-report"}:
        report = compare_debug_report(
            Path(args.context),
            Path(args.report),
            Path(args.output) if args.output else None,
        )
        print(json.dumps(report, indent=2, ensure_ascii=False))
        return 0 if report.get("ok") else 1

    if args.command == "make-openocd-target":
        config = write_detected_openocd_target(
            output_path=Path(args.output),
            executable=args.executable,
            interface_cfg=args.interface,
            target_cfg=args.target_cfg,
            remote=args.remote,
        )
        print(json.dumps(config, indent=2, ensure_ascii=False))
        return 0

    if args.command == "build":
        adapter = create_build_adapter(load_build_config(Path(args.config)))
        result = adapter.build()
        _print_result(result)
        return 0 if result.ok else 1

    if args.command == "flash":
        adapter = create_build_adapter(load_build_config(Path(args.config)))
        result = adapter.flash()
        _print_result(result)
        return 0 if result.ok else 1

    if args.command == "repair-build":
        config = load_build_config(Path(args.config))
        session = BuildRepairSession(
            build_adapter=create_build_adapter(config),
            repair_adapter=create_repair_adapter(config),
            max_iterations=config.max_repair_iterations,
        )
        report = session.run()
        print(json.dumps(report, indent=2, ensure_ascii=False, default=str))
        return 0 if report.get("ok") else 1

    if args.command == "smoke-test":
        adapter = create_build_adapter(load_build_config(Path(args.config)))
        result = adapter.smoke_test()
        _print_result(result)
        return 0 if result.ok else 1

    if args.command == "runtime-log":
        adapter = create_build_adapter(load_build_config(Path(args.config)))
        result = adapter.collect_runtime_log()
        _print_result(result)
        return 0 if result.ok else 1

    if args.command == "closed-loop":
        build_config = load_build_config(Path(args.build_config))
        debug_adapter = None
        debug_task = None
        if args.target and args.task:
            debug_adapter = create_debug_adapter(load_target_config(Path(args.target)))
            debug_task = load_debug_task(Path(args.task))
        session = ClosedLoopSession(
            build_adapter=create_build_adapter(build_config),
            repair_adapter=create_repair_adapter(build_config),
            max_repair_iterations=build_config.max_repair_iterations,
            debug_adapter=debug_adapter,
            debug_task=debug_task,
            report_dir=Path(args.report_dir),
        )
        report = session.run()
        print(json.dumps(report, indent=2, ensure_ascii=False, default=str))
        return 0 if report.get("ok") else 1

    if args.command == "ai-debug":
        workspace_defaults = load_workspace_defaults(Path(args.workspace_config))
        project_path = Path(args.project or workspace_defaults.get("project") or ".")
        context_path = Path(args.context or workspace_defaults.get("context") or "examples/mcu_context.json")
        chip = args.chip or workspace_defaults.get("chip")
        svd = args.svd or workspace_defaults.get("svd")
        linker = args.linker or workspace_defaults.get("linker")
        startup = args.startup or workspace_defaults.get("startup")
        board = args.board or workspace_defaults.get("board")
        package_name = args.package or workspace_defaults.get("package")
        workspace_doc_repo = workspace_defaults.get("knowledge_repo_path")
        build_config_path = args.build_config or workspace_defaults.get("build_config")
        target_path = args.target or workspace_defaults.get("target")
        task_path = args.task or workspace_defaults.get("task")
        build_adapter = None
        repair_adapter = None
        max_repair_iterations = 3
        if build_config_path:
            build_config = load_build_config(Path(build_config_path))
            build_adapter = create_build_adapter(build_config)
            repair_adapter = create_repair_adapter(build_config)
            max_repair_iterations = (
                args.max_repair_iterations
                if args.max_repair_iterations is not None
                else build_config.max_repair_iterations
            )
        debug_adapter = None
        debug_task = None
        if target_path and task_path:
            debug_adapter = create_debug_adapter(load_target_config(Path(target_path)))
            debug_task = load_debug_task(Path(task_path))
        session = AiDebugSession(
            project_path=project_path,
            context_path=context_path,
            mode=args.mode,
            prepare_options={
                "chip": chip,
                "svd_path": Path(svd) if svd else None,
                "linker_path": Path(linker) if linker else None,
                "startup_path": Path(startup) if startup else None,
                "board": board,
                "package_name": package_name,
                "extra_docs": _parse_doc_args(args.doc),
                "doc_repo_paths": _doc_repo_paths(args.doc_repo, workspace_defaults=workspace_defaults),
            },
            build_adapter=build_adapter,
            repair_adapter=repair_adapter,
            debug_adapter=debug_adapter,
            debug_task=debug_task,
            target_config_path=Path(target_path) if target_path else None,
            report_dir=Path(args.report_dir),
            allow_flash=args.allow_flash,
            allow_repair=args.allow_repair,
            max_repair_iterations=max_repair_iterations,
            connection_diagnostic_timeout_s=args.connection_diagnostic_timeout_s,
        )
        report = session.run()
        print(json.dumps(report, indent=2, ensure_ascii=False, default=str))
        return 0 if report.get("ok") else 1

    if args.command == "export-handoff":
        report = export_handoff(
            output=Path(args.output),
            project_path=Path(args.project),
            workspace_config=Path(args.workspace_config),
            report_dir=Path(args.report_dir) if args.report_dir else None,
            include_globs=args.include_glob,
            zip_output=args.zip,
        )
        print(json.dumps(report, indent=2, ensure_ascii=False))
        return 0 if report.get("ok") else 1

    if args.command == "replay-handoff":
        report = replay_handoff(
            manifest_path=Path(args.manifest),
            project_path=Path(args.project),
            execute=args.execute,
            output_path=Path(args.output) if args.output else None,
            timeout_s=args.timeout_s,
            stop_on_failure=not args.continue_on_failure,
        )
        print(json.dumps(report, indent=2, ensure_ascii=False))
        return 0 if report.get("ok") else 1

    if args.command == "debug":
        target = load_target_config(Path(args.target))
        task = load_debug_task(Path(args.task))
        session = AutoDebugSession(create_debug_adapter(target), Path(args.report_dir))
        report = session.run(task)
        print(json.dumps(report, indent=2, ensure_ascii=False))
        return 0 if report.get("ok") else 1

    if args.command == "accept-first-stage":
        target = load_target_config(Path(args.target))
        task = load_debug_task(Path(args.task))
        acceptance = FirstPhaseAcceptance(create_debug_adapter(target), Path(args.report_dir))
        report = acceptance.run(task)
        print(json.dumps(report, indent=2, ensure_ascii=False))
        return 0 if report.get("ok") else 1

    if args.command == "debug-sequence":
        target = load_target_config(Path(args.target))
        with Path(args.sequence).open("r", encoding="utf-8") as file:
            sequence = json.load(file)
        session = DebugSequenceSession(create_debug_adapter(target), Path(args.report_dir))
        report = session.run(sequence["name"], sequence["operations"])
        print(json.dumps(report, indent=2, ensure_ascii=False))
        return 0 if report.get("ok") else 1

    if args.command == "debug-op":
        target = load_target_config(Path(args.target))
        params = _debug_op_params(args)
        guard = _guard_debug_op(args.operation, params, args.context, args.force)
        if guard and not guard.get("ok", False):
            report = {"ok": False, "operation": args.operation, "guard": guard}
            append_audit_event(
                "debug_guard_blocked",
                args={"operation": args.operation, "params": params, "context": args.context, "force": args.force},
                result=guard,
                ok=False,
            )
            print(json.dumps(report, indent=2, ensure_ascii=False))
            return 2
        adapter = create_debug_adapter(target)
        adapter.connect()
        try:
            report = execute_debug_operation(adapter, args.operation, params)
            if guard:
                report["guard"] = guard
        finally:
            adapter.close()
        print(json.dumps(report, indent=2, ensure_ascii=False))
        return 0 if report.get("ok") else 1

    return 1


def _print_result(result) -> None:
    print(json.dumps(result.__dict__, indent=2, ensure_ascii=False, default=str))


def _configure_utf8_stdout() -> None:
    if hasattr(sys.stdout, "reconfigure"):
        try:
            sys.stdout.reconfigure(encoding="utf-8")
        except Exception:
            pass


def _debug_op_params(args) -> dict[str, object]:
    return {
        "register": args.register,
        "value": args.value,
        "address": args.address,
        "length": args.length,
        "data_hex": args.data_hex,
        "location": args.location,
        "breakpoint_id": args.breakpoint_id,
        "timeout_s": args.timeout_s,
        "halt": not args.run_after_reset,
    }


def _parse_doc_args(values: list[str]) -> list[tuple[str, Path]]:
    documents: list[tuple[str, Path]] = []
    for value in values:
        if "=" not in value:
            raise ValueError(f"Document must be kind=path: {value}")
        kind, path = value.split("=", 1)
        documents.append((kind, Path(path)))
    return documents


def _parse_url_args(values: list[str]) -> list[tuple[str, str]]:
    urls: list[tuple[str, str]] = []
    for value in values:
        if "=" not in value:
            raise ValueError(f"URL must be kind=url: {value}")
        kind, url = value.split("=", 1)
        urls.append((kind, url))
    return urls


def _doc_repo_paths(
    values: list[str],
    workspace_defaults: dict[str, object] | None = None,
) -> list[Path]:
    if values:
        return [Path(path) for path in values]
    defaults = workspace_defaults if workspace_defaults is not None else load_workspace_defaults()
    configured = defaults.get("knowledge_repo_path") if defaults else None
    return [Path(str(configured))] if configured else []


def _guard_debug_op(
    operation: str,
    params: dict[str, object],
    context_path: str | None,
    force: bool,
) -> dict[str, object] | None:
    register_name = str(params.get("register") or "")
    if not context_path and operation == "read-register" and not _is_core_register(register_name):
        return {
            "ok": force,
            "forced": force,
            "checks": [],
            "reason": "mcu_context_required_for_peripheral_register_read",
        }
    if not context_path and operation in {"write-register", "write-memory"}:
        return {
            "ok": force,
            "forced": force,
            "checks": [],
            "reason": "mcu_context_required_for_write_operation",
        }
    if not context_path:
        return None
    adapter = JsonKnowledgeAdapter(Path(context_path))
    if operation == "read-register":
        if _is_core_register(register_name):
            return {
                "ok": True,
                "forced": force,
                "checks": [],
                "reason": "core_register_read_allowed_without_svd_semantics",
            }
        check = adapter.explain_register(register_name)
        if check.get("ok"):
            register = check["register"]
            params["mapped_register"] = {
                "qualified_name": register["qualified_name"],
                "address": register["address"],
                "size_bytes": max(1, int(register.get("size") or 32) // 8),
            }
        return {"ok": force or bool(check.get("ok")), "forced": force, "checks": [check]}
    if operation == "write-register":
        check = adapter.validate_register_write(str(params["register"]), int(str(params["value"]), 0))
        return {"ok": force or bool(check.get("allowed", check.get("ok"))), "forced": force, "checks": [check]}
    if operation == "write-memory":
        address = int(str(params["address"]), 0)
        data = bytes.fromhex(str(params["data_hex"]))
        checks: list[dict[str, object]] = [adapter.validate_address_write(address, len(data))]
        register_explanation = adapter.explain_register(f"0x{address:08X}")
        if register_explanation.get("ok") and len(data) <= 4:
            checks.append(adapter.validate_register_write(f"0x{address:08X}", int.from_bytes(data, "little")))
        failed = [check for check in checks if not check.get("allowed", check.get("ok"))]
        return {"ok": force or not failed, "forced": force, "checks": checks}
    return {"ok": True, "forced": force, "checks": [], "reason": "operation_has_no_context_guard"}


def _is_core_register(name: str) -> bool:
    normalized = name.strip().lower()
    if normalized in {"pc", "sp", "msp", "psp", "lr", "xpsr", "ipsr", "epsr", "apsr", "primask", "basepri", "faultmask", "control"}:
        return True
    if normalized.startswith("r") and normalized[1:].isdigit():
        index = int(normalized[1:])
        return 0 <= index <= 15
    return False


if __name__ == "__main__":
    raise SystemExit(main())
