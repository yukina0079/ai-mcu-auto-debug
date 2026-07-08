from __future__ import annotations

import json
from dataclasses import asdict
from pathlib import Path
from typing import Any

from ai_mcu_debug.audit import export_handoff
from ai_mcu_debug.bootstrap import setup_project as setup_mcu_project
from ai_mcu_debug.capability_audit import audit_capabilities
from ai_mcu_debug.cli import _guard_debug_op, _parse_doc_args, _parse_url_args
from ai_mcu_debug.config import load_build_config, load_debug_task, load_target_config
from ai_mcu_debug.connection_diagnostics import run_openocd_connection_matrix
from ai_mcu_debug.doctor import run_doctor
from ai_mcu_debug.factory import create_build_adapter, create_debug_adapter, create_repair_adapter
from ai_mcu_debug.hardware_identity import read_hardware_identity
from ai_mcu_debug.knowledge import (
    check_context,
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
from ai_mcu_debug.mcp_config import generate_mcp_config
from ai_mcu_debug.mcp_smoke import smoke_test_mcp
from ai_mcu_debug.nonvision_acceptance import run_nonvision_acceptance
from ai_mcu_debug.probe_scan import scan_debug_probes
from ai_mcu_debug.replay import replay_handoff as replay_handoff_manifest
from ai_mcu_debug.runner import AiDebugSession, BuildRepairSession, execute_debug_operation
from ai_mcu_debug.skill_bootstrap import bootstrap_skill_environment
from ai_mcu_debug.skill_install import install_skill
from ai_mcu_debug.target_validation import validate_debug_target
from ai_mcu_debug.workflow_plan import plan_workflow
from ai_mcu_debug.workflow_run import run_workflow
from ai_mcu_debug.workspace import init_workspace_config, load_workspace_defaults, workspace_status


def prepare_context(
    *,
    project: str | Path = ".",
    output: str | Path = "examples/mcu_context.json",
    chip: str | None = None,
    svd: str | Path | None = None,
    linker: str | Path | None = None,
    startup: str | Path | None = None,
    board: str | None = None,
    package: str | None = None,
    docs: list[str] | None = None,
    doc_repos: list[str | Path] | None = None,
) -> dict[str, Any]:
    """Prepare mcu_context.json without guessing missing MCU facts."""

    return prepare_mcu(
        project_path=Path(project),
        output_path=Path(output),
        chip=chip,
        svd_path=Path(svd) if svd else None,
        linker_path=Path(linker) if linker else None,
        startup_path=Path(startup) if startup else None,
        board=board,
        package_name=package,
        extra_docs=_parse_doc_args(docs or []),
        doc_repo_paths=[Path(path) for path in doc_repos or []],
    )


def plan_docs(
    *,
    project: str | Path = ".",
    output: str | Path = "examples/mcu_context.json",
    chip: str | None = None,
    svd: str | Path | None = None,
    linker: str | Path | None = None,
    startup: str | Path | None = None,
    docs: list[str] | None = None,
    doc_repos: list[str | Path] | None = None,
) -> dict[str, Any]:
    """Return a deterministic user-document request plan; never searches the web."""

    return plan_document_intake(
        project_path=Path(project),
        chip=chip,
        svd_path=Path(svd) if svd else None,
        linker_path=Path(linker) if linker else None,
        startup_path=Path(startup) if startup else None,
        extra_docs=_parse_doc_args(docs or []),
        doc_repo_paths=[Path(path) for path in doc_repos or []],
        output_path=Path(output),
    )


def plan_next_workflow(
    *,
    project: str | Path = ".",
    context: str | Path = "examples/mcu_context.json",
    workspace_config: str | Path = ".embeddedskills/config.json",
    chip: str | None = None,
    svd: str | Path | None = None,
    linker: str | Path | None = None,
    startup: str | Path | None = None,
    docs: list[str] | None = None,
    doc_repos: list[str | Path] | None = None,
) -> dict[str, Any]:
    """Plan the next safe MCU onboarding/debug tool calls without side effects."""

    return plan_workflow(
        project_path=Path(project),
        context_path=Path(context),
        workspace_config=Path(workspace_config),
        chip=chip,
        svd_path=Path(svd) if svd else None,
        linker_path=Path(linker) if linker else None,
        startup_path=Path(startup) if startup else None,
        extra_docs=_parse_doc_args(docs or []),
        doc_repo_paths=[Path(path) for path in doc_repos or []],
    )


def run_next_workflow(
    *,
    project: str | Path = ".",
    context: str | Path = "examples/mcu_context.json",
    workspace_config: str | Path = ".embeddedskills/config.json",
    report_dir: str | Path = "debug_runs/workflow_run",
    chip: str | None = None,
    svd: str | Path | None = None,
    linker: str | Path | None = None,
    startup: str | Path | None = None,
    docs: list[str] | None = None,
    doc_repos: list[str | Path] | None = None,
    max_steps: int = 8,
    allow_file_writes: bool = True,
    allow_hardware: bool = True,
    stop_on_failure: bool = True,
) -> dict[str, Any]:
    """Execute safe workflow-plan recommendations until blocked or complete."""

    return run_workflow(
        project_path=Path(project),
        context_path=Path(context),
        workspace_config=Path(workspace_config),
        report_dir=Path(report_dir),
        chip=chip,
        svd_path=Path(svd) if svd else None,
        linker_path=Path(linker) if linker else None,
        startup_path=Path(startup) if startup else None,
        extra_docs=_parse_doc_args(docs or []),
        doc_repo_paths=[Path(path) for path in doc_repos or []],
        max_steps=max_steps,
        allow_file_writes=allow_file_writes,
        allow_hardware=allow_hardware,
        stop_on_failure=stop_on_failure,
    )


def audit_project_capabilities(
    *,
    project: str | Path = ".",
    include_vision: bool = False,
    output: str | Path | None = None,
) -> dict[str, Any]:
    """Audit the current non-vision automation capability surface."""

    return audit_capabilities(
        project_path=Path(project),
        include_vision=include_vision,
        output=Path(output) if output else None,
    )


def generate_mcp_client_config(
    *,
    project: str | Path = ".",
    client: str = "codex",
    python_executable: str | Path | None = None,
    server_name: str = "ai_mcu_debug",
    output: str | Path | None = None,
) -> dict[str, Any]:
    """Generate a portable MCP client config snippet for the local server."""

    return generate_mcp_config(
        project_path=Path(project),
        client=client,
        python_executable=python_executable,
        server_name=server_name,
        output=Path(output) if output else None,
    )


def smoke_test_mcp_server(
    *,
    project: str | Path = ".",
    python_executable: str | Path | None = None,
    required_tools: list[str] | None = None,
    timeout_s: float = 10.0,
    output: str | Path | None = None,
) -> dict[str, Any]:
    """Launch the MCP server once and verify core tool discovery."""

    return smoke_test_mcp(
        project_path=Path(project),
        python_executable=python_executable,
        required_tools=required_tools,
        timeout_s=timeout_s,
        output=Path(output) if output else None,
    )


def bootstrap_skill(
    *,
    project: str | Path = ".",
    source: str | Path | None = None,
    destination: str | Path | None = None,
    codex_home: str | Path | None = None,
    skill_name: str = "mcu-auto-debug",
    client: str = "codex",
    python_executable: str | Path | None = None,
    server_name: str = "ai_mcu_debug",
    config_output: str | Path | None = None,
    report_output: str | Path | None = None,
    dry_run: bool = False,
    force: bool = False,
    skip_install: bool = False,
    skip_smoke: bool = False,
    include_vision: bool = False,
    timeout_s: float = 10.0,
) -> dict[str, Any]:
    """Install/update the skill, generate MCP config, smoke-test MCP, and audit non-vision readiness."""

    return bootstrap_skill_environment(
        project_path=Path(project),
        source=source,
        destination=destination,
        codex_home=codex_home,
        skill_name=skill_name,
        client=client,
        python_executable=python_executable,
        server_name=server_name,
        config_output=config_output,
        report_output=report_output,
        dry_run=dry_run,
        force=force,
        skip_install=skip_install,
        skip_smoke=skip_smoke,
        include_vision=include_vision,
        timeout_s=timeout_s,
    )


def resolve_mcu_chip(
    *,
    project: str | Path = ".",
    chip: str | None = None,
    svd: str | Path | None = None,
    linker: str | Path | None = None,
    startup: str | Path | None = None,
    target: str | Path | None = None,
) -> dict[str, Any]:
    """Resolve MCU identity from explicit input and project evidence."""

    return resolve_chip(
        project_path=Path(project),
        chip=chip,
        svd_path=Path(svd) if svd else None,
        linker_path=Path(linker) if linker else None,
        startup_path=Path(startup) if startup else None,
        target_path=Path(target) if target else None,
    )


def locate_mcu_documents(
    *,
    project: str | Path = ".",
    chip: str | None = None,
    svd: str | Path | None = None,
    linker: str | Path | None = None,
    startup: str | Path | None = None,
    docs: list[str] | None = None,
    doc_repos: list[str | Path] | None = None,
) -> dict[str, Any]:
    """Locate user-provided local MCU evidence without web search."""

    return locate_docs(
        project_path=Path(project),
        chip=chip,
        svd_path=Path(svd) if svd else None,
        linker_path=Path(linker) if linker else None,
        startup_path=Path(startup) if startup else None,
        extra_docs=_parse_doc_args(docs or []),
        doc_repo_paths=[Path(path) for path in doc_repos or []],
    )


def fetch_user_documents(
    *,
    manifest: str | Path,
    chip: str | None = None,
    urls: list[str] | None = None,
    timeout_s: float = 30.0,
) -> dict[str, Any]:
    """Cache user-provided local files or URLs and record hashes."""

    return fetch_docs(
        chip=chip,
        urls=_parse_url_args(urls or []),
        manifest_path=Path(manifest),
        timeout_s=timeout_s,
    )


def ingest_user_documents(
    *,
    manifest: str | Path,
    output: str | Path = "examples/mcu_context.json",
    chip: str | None = None,
    svd: str | Path | None = None,
    linker: str | Path | None = None,
    startup: str | Path | None = None,
    board: str | None = None,
    package: str | None = None,
) -> dict[str, Any]:
    """Convert a user document manifest into mcu_context.json."""

    return ingest_docs(
        manifest_path=Path(manifest),
        output_path=Path(output),
        chip=chip,
        svd_path=Path(svd) if svd else None,
        linker_path=Path(linker) if linker else None,
        startup_path=Path(startup) if startup else None,
        board=board,
        package_name=package,
    )


def sync_document_repo(
    *,
    url: str | None = None,
    local_path: str | Path = "knowledge_repos/mcu-docs",
    ref: str | None = None,
    update: bool = True,
) -> dict[str, Any]:
    """Clone or update a user-provided MCU document Git repository."""

    return sync_doc_repo(url=url, local_path=Path(local_path), ref=ref, update=update)


def check_prepared_context(*, context: str | Path = "examples/mcu_context.json") -> dict[str, Any]:
    """Check whether mcu_context.json is sufficient for guarded debugging."""

    return check_context(Path(context))


def write_debug_record(
    *,
    context: str | Path = "examples/mcu_context.json",
    output: str | Path = "docs/MCU_DEBUG_RECORD.md",
) -> dict[str, Any]:
    """Write the MCU debug reference document from mcu_context.json."""

    return write_mcu_debug_doc(Path(context), Path(output))


def setup_project(
    *,
    project: str | Path = ".",
    output_dir: str | Path = ".embeddedskills",
    context: str | Path = "examples/mcu_context.json",
    chip: str | None = None,
    svd: str | Path | None = None,
    linker: str | Path | None = None,
    startup: str | Path | None = None,
    board: str | None = None,
    package: str | None = None,
    docs: list[str] | None = None,
    doc_repos: list[str | Path] | None = None,
    knowledge_repo_url: str | None = None,
    knowledge_repo_path: str | Path | None = None,
    build_config: str | Path | None = None,
    build_backend: str | None = None,
    pio_env: str | None = None,
    keil_project: str | Path | None = None,
    keil_target: str | None = None,
    uv4: str | Path | None = None,
    target: str | Path | None = None,
    task: str | Path | None = None,
    debug_backend: str | None = None,
    executable: str | Path | None = None,
    interface: str | None = None,
    target_cfg: str | None = None,
    transport: str = "swd",
    adapter_speed: int = 100,
    scan_probes: bool = True,
    force: bool = False,
) -> dict[str, Any]:
    """Run the non-vision one-pass project setup workflow."""

    return setup_mcu_project(
        project_path=Path(project),
        output_dir=Path(output_dir),
        context_path=Path(context),
        chip=chip,
        svd_path=Path(svd) if svd else None,
        linker_path=Path(linker) if linker else None,
        startup_path=Path(startup) if startup else None,
        board=board,
        package_name=package,
        extra_docs=_parse_doc_args(docs or []),
        doc_repo_paths=[Path(path) for path in doc_repos or []],
        knowledge_repo_url=knowledge_repo_url,
        knowledge_repo_path=Path(knowledge_repo_path) if knowledge_repo_path else None,
        build_config_path=Path(build_config) if build_config else None,
        build_backend=build_backend,
        pio_env=pio_env,
        keil_project=Path(keil_project) if keil_project else None,
        keil_target=keil_target,
        uv4_path=Path(uv4) if uv4 else None,
        target_path=Path(target) if target else None,
        task_path=Path(task) if task else None,
        debug_backend=debug_backend,
        executable_path=Path(executable) if executable else None,
        interface_cfg=interface,
        target_cfg=target_cfg,
        transport=transport,
        adapter_speed=adapter_speed,
        scan_probes=scan_probes,
        force=force,
    )


def check_environment(
    *,
    debug_backend: str | None = None,
    build_backend: str | None = None,
) -> dict[str, Any]:
    """Check local tool availability for selected debug/build backends."""

    return run_doctor(debug_backend=debug_backend, build_backend=build_backend)


def scan_debug_probes_api() -> dict[str, Any]:
    """Scan local USB/PnP devices for supported debug probes."""

    return scan_debug_probes()


def initialize_workspace(
    *,
    output_dir: str | Path = ".embeddedskills",
    project: str | Path = ".",
    chip: str | None = None,
    context: str | Path | None = None,
    svd: str | Path | None = None,
    linker: str | Path | None = None,
    startup: str | Path | None = None,
    board: str | None = None,
    package: str | None = None,
    knowledge_repo_url: str | None = None,
    knowledge_repo_path: str | Path | None = None,
    build_config: str | Path | None = None,
    build_backend: str | None = None,
    pio_env: str | None = None,
    keil_project: str | Path | None = None,
    keil_target: str | None = None,
    uv4: str | Path | None = None,
    target: str | Path | None = None,
    task: str | Path | None = None,
    debug_backend: str | None = None,
    executable: str | Path | None = None,
    interface: str | None = None,
    target_cfg: str | None = None,
    transport: str = "swd",
    adapter_speed: int = 100,
    generate_templates: bool = True,
    run_doctor_check: bool = True,
    scan_probes: bool = True,
    force: bool = False,
) -> dict[str, Any]:
    """Persist workspace defaults and optionally generate build/debug templates."""

    probe_report = None if interface or not scan_probes or not generate_templates else scan_debug_probes()
    doctor_report = None if not run_doctor_check or not generate_templates else run_doctor()
    report = init_workspace_config(
        output_dir=Path(output_dir),
        project_path=Path(project),
        chip=chip,
        context_path=Path(context) if context else None,
        svd_path=Path(svd) if svd else None,
        linker_path=Path(linker) if linker else None,
        startup_path=Path(startup) if startup else None,
        board=board,
        package_name=package,
        knowledge_repo_url=knowledge_repo_url,
        knowledge_repo_path=Path(knowledge_repo_path) if knowledge_repo_path else None,
        build_config_path=Path(build_config) if build_config else None,
        build_backend=build_backend,
        pio_env=pio_env,
        keil_project=Path(keil_project) if keil_project else None,
        keil_target=keil_target,
        uv4_path=Path(uv4) if uv4 else None,
        target_path=Path(target) if target else None,
        task_path=Path(task) if task else None,
        debug_backend=debug_backend,
        executable_path=Path(executable) if executable else None,
        interface_cfg=interface,
        target_cfg=target_cfg,
        transport=transport,
        adapter_speed=adapter_speed,
        generate_templates=generate_templates,
        doctor_report=doctor_report,
        probe_report=probe_report,
        force=force,
    )
    if probe_report is not None:
        report["probe_scan"] = probe_report
    if doctor_report is not None:
        report["doctor"] = doctor_report
    return report


def validate_target_config(
    *,
    target: str | Path,
    scan_probes: bool = False,
) -> dict[str, Any]:
    """Validate a debug target config against optional detected probe evidence."""

    probe_report = scan_debug_probes() if scan_probes else None
    report = validate_debug_target(Path(target), probe_report=probe_report)
    if probe_report is not None:
        report["probe_scan"] = probe_report
    return report


def diagnose_connection(
    *,
    target: str | Path | None = None,
    report_dir: str | Path = "debug_runs/connection_diagnostics_api",
    timeout_s: float = 12.0,
    workspace_config: str | Path = ".embeddedskills/config.json",
) -> dict[str, Any]:
    """Run the bounded, non-flashing OpenOCD connection matrix for a target config."""

    workspace_defaults = load_workspace_defaults(Path(workspace_config))
    target_path = target or workspace_defaults.get("target")
    if not target_path:
        return {
            "ok": False,
            "status": "target_config_missing",
            "next_actions": ["Provide target or run init-workspace to create .embeddedskills/debug.target.json."],
        }
    return run_openocd_connection_matrix(
        load_target_config(Path(target_path)),
        report_dir=Path(report_dir),
        timeout_s=timeout_s,
    )


def get_mcu_profile(*, chip: str | None = None) -> dict[str, Any]:
    """Return deterministic document/profile hints and a manifest skeleton."""

    return {
        "ok": True,
        "chip": chip,
        "profile": profile_for_chip(chip),
        "manifest_template": manifest_template(chip),
        "policy": {
            "web_search_allowed": False,
            "template_requires_user_sources": True,
        },
    }


def lint_mcu_manifest(
    *,
    manifest: str | Path,
    chip: str | None = None,
    strict_hashes: bool = False,
) -> dict[str, Any]:
    """Validate a user-provided MCU document manifest without fetching documents."""

    return lint_manifest(Path(manifest), chip=chip, strict_hashes=strict_hashes)


def build_firmware(*, config: str | Path) -> dict[str, Any]:
    """Build firmware through the configured build adapter."""

    build_config = load_build_config(Path(config))
    result = create_build_adapter(build_config).build()
    return {"ok": result.ok, "status": "ok" if result.ok else "build_failed", "result": asdict(result)}


def smoke_test_firmware(*, config: str | Path) -> dict[str, Any]:
    """Run the configured non-hardware smoke test command."""

    build_config = load_build_config(Path(config))
    result = create_build_adapter(build_config).smoke_test()
    return {"ok": result.ok, "status": "ok" if result.ok else "smoke_test_failed", "result": asdict(result)}


def collect_runtime_log(*, config: str | Path) -> dict[str, Any]:
    """Collect runtime log evidence through a configured command wrapper."""

    build_config = load_build_config(Path(config))
    result = create_build_adapter(build_config).collect_runtime_log()
    return {"ok": result.ok, "status": "ok" if result.ok else "runtime_log_failed", "result": asdict(result)}


def repair_build(
    *,
    config: str | Path,
    allow_repair: bool = False,
    max_iterations: int | None = None,
) -> dict[str, Any]:
    """Run build repair only when code edits by the configured repair tool are explicitly allowed."""

    if not allow_repair:
        return {
            "ok": False,
            "status": "repair_blocked_by_policy",
            "next_actions": ["Set allow_repair=true only when code edits by the configured repair tool are intended."],
        }
    build_config = load_build_config(Path(config))
    report = BuildRepairSession(
        build_adapter=create_build_adapter(build_config),
        repair_adapter=create_repair_adapter(build_config),
        max_iterations=max_iterations if max_iterations is not None else build_config.max_repair_iterations,
    ).run()
    report["status"] = "ok" if report.get("ok") else str(report.get("stop_reason") or "repair_build_failed")
    return report


def accept_nonvision(
    *,
    project: str | Path = ".",
    output_dir: str | Path = ".embeddedskills",
    context: str | Path = "examples/mcu_context.json",
    report_dir: str | Path = "debug_runs/nonvision_acceptance",
    handoff_output: str | Path | None = None,
    handoff_project: str | Path = ".",
    zip_handoff: bool = False,
    chip: str | None = None,
    svd: str | Path | None = None,
    linker: str | Path | None = None,
    startup: str | Path | None = None,
    board: str | None = None,
    package: str | None = None,
    docs: list[str] | None = None,
    doc_repos: list[str | Path] | None = None,
    knowledge_repo_url: str | None = None,
    knowledge_repo_path: str | Path | None = None,
    build_config: str | Path | None = None,
    build_backend: str | None = None,
    pio_env: str | None = None,
    keil_project: str | Path | None = None,
    keil_target: str | None = None,
    uv4: str | Path | None = None,
    target: str | Path | None = None,
    task: str | Path | None = None,
    debug_backend: str | None = None,
    executable: str | Path | None = None,
    interface: str | None = None,
    target_cfg: str | None = None,
    transport: str = "swd",
    adapter_speed: int = 100,
    scan_probes: bool = True,
    force: bool = False,
) -> dict[str, Any]:
    """Run setup, ai-debug dry-run, handoff export, and replay validation as one non-vision gate."""

    return run_nonvision_acceptance(
        project_path=Path(project),
        output_dir=Path(output_dir),
        context_path=Path(context),
        report_dir=Path(report_dir),
        handoff_output=Path(handoff_output) if handoff_output else None,
        handoff_project_path=Path(handoff_project),
        zip_handoff=zip_handoff,
        chip=chip,
        svd_path=Path(svd) if svd else None,
        linker_path=Path(linker) if linker else None,
        startup_path=Path(startup) if startup else None,
        board=board,
        package_name=package,
        extra_docs=_parse_doc_args(docs or []),
        doc_repo_paths=[Path(path) for path in doc_repos or []],
        knowledge_repo_url=knowledge_repo_url,
        knowledge_repo_path=Path(knowledge_repo_path) if knowledge_repo_path else None,
        build_config_path=Path(build_config) if build_config else None,
        build_backend=build_backend,
        pio_env=pio_env,
        keil_project=Path(keil_project) if keil_project else None,
        keil_target=keil_target,
        uv4_path=Path(uv4) if uv4 else None,
        target_path=Path(target) if target else None,
        task_path=Path(task) if task else None,
        debug_backend=debug_backend,
        executable_path=Path(executable) if executable else None,
        interface_cfg=interface,
        target_cfg=target_cfg,
        transport=transport,
        adapter_speed=adapter_speed,
        scan_probes=scan_probes,
        force=force,
    )


def run_ai_debug(
    *,
    project: str | Path | None = None,
    mode: str = "dry-run",
    context: str | Path | None = None,
    chip: str | None = None,
    svd: str | Path | None = None,
    linker: str | Path | None = None,
    startup: str | Path | None = None,
    board: str | None = None,
    package: str | None = None,
    docs: list[str] | None = None,
    doc_repos: list[str | Path] | None = None,
    build_config: str | Path | None = None,
    target: str | Path | None = None,
    task: str | Path | None = None,
    report_dir: str | Path = "debug_runs/ai_debug_api",
    allow_flash: bool = False,
    allow_repair: bool = False,
    max_repair_iterations: int | None = None,
    connection_diagnostic_timeout_s: float = 12.0,
    workspace_config: str | Path = ".embeddedskills/config.json",
) -> dict[str, Any]:
    """Run the skill orchestration with the same default safety policy as the CLI."""

    workspace_defaults = load_workspace_defaults(Path(workspace_config))
    project_path = Path(project or workspace_defaults.get("project") or ".")
    context_path = Path(context or workspace_defaults.get("context") or "examples/mcu_context.json")
    selected_chip = chip or workspace_defaults.get("chip")
    selected_svd = svd or workspace_defaults.get("svd")
    selected_linker = linker or workspace_defaults.get("linker")
    selected_startup = startup or workspace_defaults.get("startup")
    selected_board = board or workspace_defaults.get("board")
    selected_package = package or workspace_defaults.get("package")
    build_config_path = build_config or workspace_defaults.get("build_config")
    workspace_doc_repo = workspace_defaults.get("knowledge_repo_path")
    target_path = target or workspace_defaults.get("target")
    task_path = task or workspace_defaults.get("task")

    build_adapter = None
    repair_adapter = None
    selected_max_repair_iterations = 3
    if build_config_path:
        loaded_build = load_build_config(Path(build_config_path))
        build_adapter = create_build_adapter(loaded_build)
        repair_adapter = create_repair_adapter(loaded_build)
        selected_max_repair_iterations = (
            max_repair_iterations
            if max_repair_iterations is not None
            else loaded_build.max_repair_iterations
        )

    debug_adapter = None
    debug_task = None
    if target_path and task_path:
        debug_adapter = create_debug_adapter(load_target_config(Path(target_path)))
        debug_task = load_debug_task(Path(task_path))

    return AiDebugSession(
        project_path=project_path,
        context_path=context_path,
        mode=mode,
        prepare_options={
            "chip": selected_chip,
            "svd_path": Path(selected_svd) if selected_svd else None,
            "linker_path": Path(selected_linker) if selected_linker else None,
            "startup_path": Path(selected_startup) if selected_startup else None,
            "board": selected_board,
            "package_name": selected_package,
            "extra_docs": _parse_doc_args(docs or []),
            "doc_repo_paths": [Path(path) for path in doc_repos or ([workspace_doc_repo] if workspace_doc_repo else [])],
        },
        build_adapter=build_adapter,
        repair_adapter=repair_adapter,
        debug_adapter=debug_adapter,
        debug_task=debug_task,
        target_config_path=Path(target_path) if target_path else None,
        report_dir=Path(report_dir),
        allow_flash=allow_flash,
        allow_repair=allow_repair,
        max_repair_iterations=selected_max_repair_iterations,
        connection_diagnostic_timeout_s=connection_diagnostic_timeout_s,
    ).run()


def run_debug_op(
    *,
    target: str | Path,
    operation: str,
    context: str | Path | None = None,
    force: bool = False,
    **params: Any,
) -> dict[str, Any]:
    """Run one debug operation after applying the same knowledge guard as the CLI."""

    clean_params = {key: value for key, value in params.items() if value is not None}
    guard = _guard_debug_op(operation, clean_params, str(context) if context else None, force)
    if guard and not guard.get("ok", False):
        return {"ok": False, "operation": operation, "guard": guard}

    adapter = create_debug_adapter(load_target_config(Path(target)))
    adapter.connect()
    try:
        report = execute_debug_operation(adapter, operation, clean_params)
        if guard:
            report["guard"] = guard
        return report
    finally:
        adapter.close()


def read_hardware_id(
    *,
    target: str | Path | None = None,
    chip: str | None = None,
    report_dir: str | Path = "debug_runs/hardware_identity_api",
    halt: bool = True,
    workspace_config: str | Path = ".embeddedskills/config.json",
) -> dict[str, Any]:
    """Read read-only silicon identity registers through the configured debug target."""

    workspace_defaults = load_workspace_defaults(Path(workspace_config))
    target_path = target or workspace_defaults.get("target")
    selected_chip = chip or workspace_defaults.get("chip")
    if not target_path:
        return {
            "ok": False,
            "status": "target_config_missing",
            "next_actions": ["Provide target or run init-workspace to create .embeddedskills/debug.target.json."],
        }
    return read_hardware_identity(
        create_debug_adapter(load_target_config(Path(target_path))),
        report_dir=Path(report_dir),
        expected_chip=selected_chip,
        halt=halt,
    )


def dumps(report: dict[str, Any]) -> str:
    return json.dumps(report, indent=2, ensure_ascii=False, default=str)


def install_skill_package(
    *,
    source: str | Path | None = None,
    destination: str | Path | None = None,
    codex_home: str | Path | None = None,
    skill_name: str = "mcu-auto-debug",
    dry_run: bool = False,
    force: bool = False,
) -> dict[str, Any]:
    """Install or update the local mcu-auto-debug Codex skill package."""

    return install_skill(
        source=Path(source) if source else None,
        destination=Path(destination) if destination else None,
        codex_home=Path(codex_home) if codex_home else None,
        skill_name=skill_name,
        dry_run=dry_run,
        force=force,
    )


def export_debug_handoff(
    *,
    output: str | Path = "debug_runs/handoff",
    project: str | Path = ".",
    workspace_config: str | Path = ".embeddedskills/config.json",
    report_dir: str | Path | None = None,
    include_globs: list[str] | None = None,
    zip_output: bool = False,
) -> dict[str, Any]:
    """Export a replayable package for another AI or engineer."""

    return export_handoff(
        output=Path(output),
        project_path=Path(project),
        workspace_config=Path(workspace_config),
        report_dir=Path(report_dir) if report_dir else None,
        include_globs=include_globs,
        zip_output=zip_output,
    )


def replay_debug_handoff(
    *,
    manifest: str | Path,
    project: str | Path = ".",
    execute: bool = False,
    output: str | Path | None = None,
    timeout_s: float = 120.0,
    continue_on_failure: bool = False,
) -> dict[str, Any]:
    """Validate or execute safe replay commands from a handoff manifest."""

    return replay_handoff_manifest(
        manifest_path=Path(manifest),
        project_path=Path(project),
        execute=execute,
        output_path=Path(output) if output else None,
        timeout_s=timeout_s,
        stop_on_failure=not continue_on_failure,
    )


def get_workspace_status(*, config: str | Path = ".embeddedskills/config.json") -> dict[str, Any]:
    return workspace_status(Path(config))
