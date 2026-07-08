from __future__ import annotations

from pathlib import Path
from typing import Any, Callable

from ai_mcu_debug.doctor import run_doctor
from ai_mcu_debug.knowledge import check_context, plan_document_intake, prepare_mcu
from ai_mcu_debug.probe_scan import scan_debug_probes
from ai_mcu_debug.workspace import init_workspace_config, workspace_status


DoctorRunner = Callable[[str | None, str | None], dict[str, Any]]
ProbeScanner = Callable[[], dict[str, Any]]


def setup_project(
    *,
    project_path: Path = Path("."),
    output_dir: Path = Path(".embeddedskills"),
    context_path: Path = Path("examples/mcu_context.json"),
    chip: str | None = None,
    svd_path: Path | None = None,
    linker_path: Path | None = None,
    startup_path: Path | None = None,
    board: str | None = None,
    package_name: str | None = None,
    extra_docs: list[tuple[str, Path]] | None = None,
    doc_repo_paths: list[Path] | None = None,
    knowledge_repo_url: str | None = None,
    knowledge_repo_path: Path | None = None,
    build_config_path: Path | None = None,
    build_backend: str | None = None,
    pio_env: str | None = None,
    keil_project: Path | None = None,
    keil_target: str | None = None,
    uv4_path: Path | None = None,
    target_path: Path | None = None,
    task_path: Path | None = None,
    debug_backend: str | None = None,
    executable_path: Path | None = None,
    interface_cfg: str | None = None,
    target_cfg: str | None = None,
    transport: str = "swd",
    adapter_speed: int = 100,
    scan_probes: bool = True,
    force: bool = False,
    doctor_runner: DoctorRunner = run_doctor,
    probe_scanner: ProbeScanner = scan_debug_probes,
) -> dict[str, Any]:
    """Set up the deterministic non-vision skill workspace in one pass.

    The function intentionally asks for missing MCU documents instead of
    searching the web or guessing vendor URLs.
    """

    selected_doc_repos = _doc_repo_paths(doc_repo_paths, knowledge_repo_path)
    doctor = doctor_runner(debug_backend, build_backend)
    probe = probe_scanner() if scan_probes else None
    report: dict[str, Any] = {
        "ok": False,
        "status": "started",
        "project": str(project_path),
        "context": str(context_path),
        "doctor": doctor,
        "probe_scan": probe,
        "artifacts": [],
        "next_actions": [],
    }

    existing_context_check = _existing_context_check(context_path)
    if existing_context_check is not None:
        report["existing_context_check"] = existing_context_check

    context_ready = bool(existing_context_check and existing_context_check.get("ok"))
    prepare_report: dict[str, Any] | None = None
    doc_plan = plan_document_intake(
        project_path=project_path,
        chip=chip,
        svd_path=svd_path,
        linker_path=linker_path,
        startup_path=startup_path,
        extra_docs=extra_docs,
        doc_repo_paths=selected_doc_repos,
        output_path=context_path,
    )
    report["document_intake"] = doc_plan

    if not context_ready:
        if doc_plan.get("ok"):
            prepare_report = prepare_mcu(
                project_path=project_path,
                output_path=context_path,
                chip=chip,
                svd_path=svd_path,
                linker_path=linker_path,
                startup_path=startup_path,
                board=board,
                package_name=package_name,
                extra_docs=extra_docs,
                doc_repo_paths=selected_doc_repos,
            )
            report["prepare_mcu"] = prepare_report
            context_ready = bool(prepare_report.get("ok")) and context_path.exists()
            if context_ready:
                report["artifacts"].append({"kind": "mcu_context", "path": str(context_path), "generated": True})
        else:
            report["status"] = doc_plan.get("status", "awaiting_user_documents")
            report["next_actions"] = _next_actions_for_missing_documents(doc_plan)
            return report

    if not context_ready:
        report["status"] = (prepare_report or {}).get("status", "context_not_ready")
        report["next_actions"] = (prepare_report or {}).get("next_actions", ["Fix context preparation errors and rerun setup-project."])
        return report

    workspace = init_workspace_config(
        output_dir=output_dir,
        project_path=project_path,
        chip=chip or doc_plan.get("chip"),
        context_path=context_path,
        svd_path=svd_path,
        linker_path=linker_path,
        startup_path=startup_path,
        board=board,
        package_name=package_name,
        knowledge_repo_url=knowledge_repo_url,
        knowledge_repo_path=knowledge_repo_path or (selected_doc_repos[0] if selected_doc_repos else None),
        build_config_path=build_config_path,
        build_backend=build_backend,
        pio_env=pio_env,
        keil_project=keil_project,
        keil_target=keil_target,
        uv4_path=uv4_path,
        target_path=target_path,
        task_path=task_path,
        debug_backend=debug_backend,
        executable_path=executable_path,
        interface_cfg=interface_cfg,
        target_cfg=target_cfg,
        transport=transport,
        adapter_speed=adapter_speed,
        doctor_report=doctor,
        probe_report=probe,
        force=force,
    )
    report["workspace_init"] = workspace
    report["artifacts"].extend(workspace.get("artifacts", []))
    report["artifacts"].extend(
        [
            {"kind": "workspace_config", "path": workspace["config"], "generated": True},
            {"kind": "workspace_state", "path": workspace["state"], "generated": True},
        ]
    )

    status = workspace_status(output_dir / "config.json")
    report["workspace_status"] = status
    hardware_ready = _workspace_path_exists(status, "target") and _workspace_path_exists(status, "task")
    report["status"] = (
        "ready_for_ai_debug"
        if status.get("ok") and hardware_ready
        else "ready_for_dry_run"
        if status.get("ok")
        else "workspace_ready_with_warnings"
    )
    report["ok"] = bool(status.get("ok"))
    report["next_actions"] = _next_actions_for_ready_workspace(doctor, probe, status, hardware_ready=hardware_ready)
    return report


def _doc_repo_paths(doc_repo_paths: list[Path] | None, knowledge_repo_path: Path | None) -> list[Path]:
    paths: list[Path] = []
    for path in doc_repo_paths or []:
        if path not in paths:
            paths.append(path)
    if knowledge_repo_path and knowledge_repo_path not in paths:
        paths.append(knowledge_repo_path)
    return paths


def _existing_context_check(context_path: Path) -> dict[str, Any] | None:
    if not context_path.exists():
        return None
    return check_context(context_path)


def _next_actions_for_missing_documents(doc_plan: dict[str, Any]) -> list[str]:
    actions = []
    required = doc_plan.get("required_requests", [])
    if required:
        kinds = ", ".join(str(item.get("kind")) for item in required)
        actions.append(f"Ask the user for the missing MCU document(s): {kinds}.")
    elif doc_plan.get("blocking_diagnostics"):
        actions.append("Resolve document repository diagnostics before generating mcu_context.json.")
    actions.append("Rerun setup-project with the user-provided --doc/--svd/--linker/--startup/--doc-repo inputs.")
    return actions


def _next_actions_for_ready_workspace(
    doctor: dict[str, Any],
    probe: dict[str, Any] | None,
    status: dict[str, Any],
    *,
    hardware_ready: bool,
) -> list[str]:
    actions = ["Run python -m ai_mcu_debug.cli ai-debug --mode dry-run."]
    if hardware_ready:
        actions.extend(
            [
                "For connected hardware, run python -m ai_mcu_debug.cli ai-debug --mode read-only.",
                "Only for an explicitly authorized board, run python -m ai_mcu_debug.cli ai-debug --mode run --allow-flash.",
            ]
        )
    else:
        actions.append("Provide or generate target/task config before read-only or run mode.")
    if not doctor.get("ok"):
        actions.extend(str(item) for item in doctor.get("recommendations", []))
    if probe is not None and not probe.get("ok"):
        actions.extend(str(item) for item in probe.get("recommendations", []))
    if not status.get("ok"):
        actions.append("Inspect workspace_status.missing and provide the missing workspace path(s).")
    return actions


def _workspace_path_exists(status: dict[str, Any], name: str) -> bool:
    return any(item.get("name") == name and item.get("exists") for item in status.get("checks", []))
