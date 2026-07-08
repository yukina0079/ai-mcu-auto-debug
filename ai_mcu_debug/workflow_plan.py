from __future__ import annotations

from pathlib import Path
from typing import Any

from ai_mcu_debug.knowledge import check_context, plan_document_intake, resolve_chip
from ai_mcu_debug.workspace import workspace_status


def plan_workflow(
    *,
    project_path: Path = Path("."),
    context_path: Path = Path("examples/mcu_context.json"),
    workspace_config: Path = Path(".embeddedskills/config.json"),
    chip: str | None = None,
    svd_path: Path | None = None,
    linker_path: Path | None = None,
    startup_path: Path | None = None,
    extra_docs: list[tuple[str, Path]] | None = None,
    doc_repo_paths: list[Path] | None = None,
) -> dict[str, Any]:
    """Return the next safe tool calls for MCU onboarding/debug without side effects."""

    resolved = resolve_chip(
        project_path=project_path,
        chip=chip,
        svd_path=svd_path,
        linker_path=linker_path,
        startup_path=startup_path,
    )
    selected_chip = chip or resolved.get("selected")
    context_check = check_context(context_path) if context_path.exists() else None
    workspace = workspace_status(workspace_config)
    doc_plan = plan_document_intake(
        project_path=project_path,
        chip=str(selected_chip) if selected_chip else None,
        svd_path=svd_path,
        linker_path=linker_path,
        startup_path=startup_path,
        extra_docs=extra_docs or [],
        doc_repo_paths=doc_repo_paths or [],
        output_path=context_path,
    )

    report: dict[str, Any] = {
        "ok": False,
        "status": "planning",
        "project": str(project_path),
        "context": str(context_path),
        "workspace_config": str(workspace_config),
        "resolved_chip": resolved,
        "document_intake": doc_plan,
        "context_check": context_check,
        "workspace_status": workspace,
        "user_requests": [],
        "recommended_tool_calls": [],
        "next_actions": [],
        "policy": {
            "side_effects": False,
            "flash_allowed": False,
            "repair_allowed": False,
            "vision_allowed": False,
            "web_search_allowed": False,
        },
    }

    if not selected_chip:
        return _finish(
            report,
            "awaiting_chip",
            ["Ask the user for the exact MCU part number before selecting datasheets or register semantics."],
            user_requests=[{"kind": "chip", "question": "请提供 MCU 的完整型号，例如 STM32F103RCT6。"}],
        )
    if resolved.get("status") == "ambiguous_chip":
        return _finish(
            report,
            "ambiguous_chip",
            ["Ask the user to choose the exact MCU part number from the reported candidates."],
            user_requests=[{"kind": "chip", "question": "检测到多个 MCU 候选，请确认准确型号。"}],
        )

    context_ready = bool(context_check and context_check.get("ok"))
    if not context_ready and not doc_plan.get("ok"):
        requests = list(doc_plan.get("required_requests", []))
        actions = _missing_document_actions(doc_plan)
        return _finish(
            report,
            str(doc_plan.get("status") or "awaiting_user_documents"),
            actions,
            user_requests=requests,
        )

    if not context_ready:
        args = _context_args(
            project_path=project_path,
            context_path=context_path,
            chip=str(selected_chip),
            svd_path=svd_path,
            linker_path=linker_path,
            startup_path=startup_path,
            extra_docs=extra_docs or [],
            doc_repo_paths=doc_repo_paths or [],
        )
        return _finish(
            report,
            "context_not_ready",
            ["Generate and validate mcu_context.json from the available user-provided evidence."],
            recommended_tool_calls=[
                _tool_call("prepare_mcu_context", args),
                _tool_call("check_mcu_context", {"context": str(context_path)}),
            ],
        )

    if not workspace.get("ok"):
        args = {
            "project": str(project_path),
            "chip": str(selected_chip),
            "context": str(context_path),
            "scan_probes": True,
        }
        return _finish(
            report,
            "workspace_not_ready",
            ["Initialize workspace-local defaults and generated templates, then re-check workspace status."],
            recommended_tool_calls=[
                _tool_call("init_workspace", args),
                _tool_call("workspace_status", {"config": str(workspace_config)}),
            ],
        )

    hardware_ready = _workspace_path_exists(workspace, "target") and _workspace_path_exists(workspace, "task")
    tool_calls = [
        _tool_call("run_ai_debug", {"mode": "dry-run", "workspace_config": str(workspace_config)}),
        _tool_call(
            "accept_nonvision",
            {
                "project": str(project_path),
                "context": str(context_path),
                "chip": str(selected_chip),
                "output_dir": str(workspace_config.parent),
                "handoff_project": str(project_path),
            },
        ),
    ]
    actions = ["Run the non-vision dry-run/debug acceptance path from workspace defaults."]
    if hardware_ready:
        tool_calls.append(
            _tool_call("run_ai_debug", {"mode": "read-only", "workspace_config": str(workspace_config)})
        )
        actions.append("For connected hardware, run read-only mode before any flashing.")
    return _finish(report, "ready_for_nonvision_debug", actions, recommended_tool_calls=tool_calls, ok=True)


def _context_args(
    *,
    project_path: Path,
    context_path: Path,
    chip: str,
    svd_path: Path | None,
    linker_path: Path | None,
    startup_path: Path | None,
    extra_docs: list[tuple[str, Path]],
    doc_repo_paths: list[Path],
) -> dict[str, Any]:
    args: dict[str, Any] = {"project": str(project_path), "chip": chip, "output": str(context_path)}
    if svd_path:
        args["svd"] = str(svd_path)
    if linker_path:
        args["linker"] = str(linker_path)
    if startup_path:
        args["startup"] = str(startup_path)
    if extra_docs:
        args["docs"] = [f"{kind}={path}" for kind, path in extra_docs]
    if doc_repo_paths:
        args["doc_repos"] = [str(path) for path in doc_repo_paths]
    return args


def _missing_document_actions(doc_plan: dict[str, Any]) -> list[str]:
    actions: list[str] = []
    required = doc_plan.get("required_requests", [])
    if required:
        kinds = ", ".join(str(item.get("kind")) for item in required)
        actions.append(f"Ask the user for missing MCU evidence: {kinds}.")
    actions.append("Do not search the web or guess datasheet URLs; rerun workflow-plan after the user provides files, URLs, or a repo.")
    return actions


def _workspace_path_exists(status: dict[str, Any], name: str) -> bool:
    return any(item.get("name") == name and item.get("exists") for item in status.get("checks", []))


def _tool_call(tool: str, arguments: dict[str, Any]) -> dict[str, Any]:
    clean_args = {key: value for key, value in arguments.items() if value is not None}
    cli_args = _cli_args_for_tool(tool, clean_args)
    return {
        "tool": tool,
        "arguments": clean_args,
        "cli": _render_cli(cli_args),
        "cli_args": cli_args,
        "safety": _safety_for_tool(tool, clean_args),
    }


def _cli_args_for_tool(tool: str, arguments: dict[str, Any]) -> list[str]:
    command_name = {
        "prepare_mcu_context": "prepare-mcu",
        "check_mcu_context": "check-context",
        "init_workspace": "init-workspace",
        "workspace_status": "workspace-status",
        "run_ai_debug": "ai-debug",
        "accept_nonvision": "accept-nonvision",
    }.get(tool, tool.replace("_", "-"))
    command = ["python", "-m", "ai_mcu_debug.cli", command_name]

    if tool == "prepare_mcu_context":
        _append_value(command, "--project", arguments.get("project"))
        _append_value(command, "--chip", arguments.get("chip"))
        _append_value(command, "--svd", arguments.get("svd"))
        _append_value(command, "--linker", arguments.get("linker"))
        _append_value(command, "--startup", arguments.get("startup"))
        for document in arguments.get("docs", []):
            _append_value(command, "--doc", document)
        for repo in arguments.get("doc_repos", []):
            _append_value(command, "--doc-repo", repo)
        _append_value(command, "--output", arguments.get("output"))
    elif tool == "check_mcu_context":
        _append_value(command, "--context", arguments.get("context"))
    elif tool == "init_workspace":
        _append_value(command, "--output-dir", arguments.get("output_dir"))
        _append_value(command, "--project", arguments.get("project"))
        _append_value(command, "--chip", arguments.get("chip"))
        _append_value(command, "--context", arguments.get("context"))
        _append_value(command, "--svd", arguments.get("svd"))
        _append_value(command, "--linker", arguments.get("linker"))
        _append_value(command, "--startup", arguments.get("startup"))
        _append_value(command, "--build-config", arguments.get("build_config"))
        _append_value(command, "--build-backend", arguments.get("build_backend"))
        _append_value(command, "--target", arguments.get("target"))
        _append_value(command, "--task", arguments.get("task"))
        _append_value(command, "--debug-backend", arguments.get("debug_backend"))
        _append_value(command, "--interface", arguments.get("interface"))
        _append_value(command, "--target-cfg", arguments.get("target_cfg"))
        if arguments.get("generate_templates") is False:
            command.append("--no-generate-templates")
        if arguments.get("force") is True:
            command.append("--force")
    elif tool == "workspace_status":
        _append_value(command, "--config", arguments.get("config"))
    elif tool == "run_ai_debug":
        _append_value(command, "--mode", arguments.get("mode"))
        _append_value(command, "--project", arguments.get("project"))
        _append_value(command, "--context", arguments.get("context"))
        _append_value(command, "--chip", arguments.get("chip"))
        _append_value(command, "--build-config", arguments.get("build_config"))
        _append_value(command, "--target", arguments.get("target"))
        _append_value(command, "--task", arguments.get("task"))
        _append_value(command, "--report-dir", arguments.get("report_dir"))
        _append_value(command, "--workspace-config", arguments.get("workspace_config"))
        if arguments.get("allow_flash") is True:
            command.append("--allow-flash")
        if arguments.get("allow_repair") is True:
            command.append("--allow-repair")
    elif tool == "accept_nonvision":
        _append_value(command, "--output-dir", arguments.get("output_dir"))
        _append_value(command, "--project", arguments.get("project"))
        _append_value(command, "--context", arguments.get("context"))
        _append_value(command, "--report-dir", arguments.get("report_dir"))
        _append_value(command, "--handoff-output", arguments.get("handoff_output"))
        _append_value(command, "--handoff-project", arguments.get("handoff_project"))
        _append_value(command, "--chip", arguments.get("chip"))
        _append_value(command, "--svd", arguments.get("svd"))
        _append_value(command, "--linker", arguments.get("linker"))
        _append_value(command, "--startup", arguments.get("startup"))
        for document in arguments.get("docs", []):
            _append_value(command, "--doc", document)
        for repo in arguments.get("doc_repos", []):
            _append_value(command, "--doc-repo", repo)
        if arguments.get("zip_handoff") is True:
            command.append("--zip-handoff")
        if arguments.get("scan_probes") is False:
            command.append("--no-scan-probes")
        if arguments.get("force") is True:
            command.append("--force")
    return command


def _append_value(command: list[str], flag: str, value: Any) -> None:
    if value is None or value is False:
        return
    command.extend([flag, str(value)])


def _render_cli(args: list[str]) -> str:
    return " ".join(_quote_cli_arg(arg) for arg in args)


def _quote_cli_arg(arg: str) -> str:
    if arg == "":
        return '""'
    if not any(char.isspace() or char in '"`$&|<>^' for char in arg):
        return arg
    return '"' + arg.replace('"', '\\"') + '"'


def _safety_for_tool(tool: str, arguments: dict[str, Any]) -> dict[str, Any]:
    safety = {
        "side_effects": False,
        "safe_to_execute_by_default": True,
        "requires_approval": False,
        "writes_files": False,
        "reads_host_devices": False,
        "touches_hardware": False,
        "target_control": False,
        "target_register_write_allowed": False,
        "target_memory_write_allowed": False,
        "flash_allowed": bool(arguments.get("allow_flash", False)),
        "repair_allowed": bool(arguments.get("allow_repair", False)),
        "force_allowed": bool(arguments.get("force", False)),
        "vision_allowed": False,
        "web_search_allowed": False,
    }
    if tool == "prepare_mcu_context":
        safety.update(side_effects=True, writes_files=True)
    elif tool == "init_workspace":
        safety.update(side_effects=True, writes_files=True, reads_host_devices=arguments.get("scan_probes", True))
    elif tool == "run_ai_debug":
        mode = str(arguments.get("mode") or "dry-run")
        touches_hardware = mode in {"read-only", "run"}
        safety.update(
            side_effects=True,
            writes_files=True,
            reads_host_devices=True,
            touches_hardware=touches_hardware,
            target_control=touches_hardware,
        )
    elif tool == "accept_nonvision":
        safety.update(
            side_effects=True,
            writes_files=True,
            reads_host_devices=arguments.get("scan_probes", True),
        )

    requires_approval = (
        safety["flash_allowed"]
        or safety["repair_allowed"]
        or safety["force_allowed"]
        or safety["target_register_write_allowed"]
        or safety["target_memory_write_allowed"]
    )
    safety["requires_approval"] = bool(requires_approval)
    safety["safe_to_execute_by_default"] = not safety["requires_approval"]
    return safety


def _finish(
    report: dict[str, Any],
    status: str,
    next_actions: list[str],
    *,
    recommended_tool_calls: list[dict[str, Any]] | None = None,
    user_requests: list[dict[str, Any]] | None = None,
    ok: bool = False,
) -> dict[str, Any]:
    report["ok"] = ok
    report["status"] = status
    report["next_actions"] = next_actions
    if recommended_tool_calls is not None:
        report["recommended_tool_calls"] = recommended_tool_calls
    if user_requests is not None:
        report["user_requests"] = user_requests
    return report
