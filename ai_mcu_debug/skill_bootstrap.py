from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from ai_mcu_debug.capability_audit import audit_capabilities
from ai_mcu_debug.mcp_config import generate_mcp_config
from ai_mcu_debug.mcp_smoke import smoke_test_mcp
from ai_mcu_debug.skill_install import install_skill


def bootstrap_skill_environment(
    *,
    project_path: str | Path = ".",
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
    """Bootstrap the local skill and MCP wiring using deterministic non-hardware steps."""

    project = Path(project_path).resolve()
    install_force = force or dry_run
    install_report = (
        {"ok": True, "status": "skipped", "reason": "skip_install=true"}
        if skip_install
        else install_skill(
            source=Path(source) if source else None,
            destination=Path(destination) if destination else None,
            codex_home=Path(codex_home) if codex_home else None,
            skill_name=skill_name,
            dry_run=dry_run,
            force=install_force,
        )
    )
    mcp_config_report = generate_mcp_config(
        project_path=project,
        client=client,
        python_executable=python_executable,
        server_name=server_name,
        output=None if dry_run else (Path(config_output) if config_output else None),
    )
    smoke_report = (
        {"ok": True, "status": "skipped", "reason": "skip_smoke=true"}
        if skip_smoke
        else smoke_test_mcp(
            project_path=project,
            python_executable=python_executable,
            timeout_s=timeout_s,
        )
    )
    capability_report = audit_capabilities(project_path=project, include_vision=include_vision)

    steps = {
        "install_skill": install_report,
        "mcp_config": mcp_config_report,
        "mcp_smoke": smoke_report,
        "capability_audit": capability_report,
    }
    failed_steps = [name for name, report in steps.items() if not report.get("ok")]
    ok = not failed_steps
    report: dict[str, Any] = {
        "ok": ok,
        "status": "would_bootstrap" if dry_run and ok else ("bootstrapped" if ok else "bootstrap_failed"),
        "project": str(project),
        "dry_run": dry_run,
        "policy": {
            "hardware_touched": False,
            "flash_allowed": False,
            "repair_allowed": False,
            "force_install": force,
            "dry_run_install_conflicts_are_previewed": dry_run,
            "global_client_config_modified": False,
            "vision_required": include_vision,
        },
        "steps": steps,
        "failed_steps": failed_steps,
        "next_actions": _next_actions(
            ok=ok,
            dry_run=dry_run,
            config_output=config_output,
            install_report=install_report,
            mcp_config_report=mcp_config_report,
            failed_steps=failed_steps,
        ),
    }
    if report_output:
        if dry_run:
            report["report_output_skipped"] = str(Path(report_output))
            report["report_output_skip_reason"] = "dry_run"
        else:
            output_path = Path(report_output)
            output_path.parent.mkdir(parents=True, exist_ok=True)
            output_path.write_text(json.dumps(report, indent=2, ensure_ascii=False, default=str), encoding="utf-8")
            report["report_output"] = str(output_path)
    return report


def _next_actions(
    *,
    ok: bool,
    dry_run: bool,
    config_output: str | Path | None,
    install_report: dict[str, Any],
    mcp_config_report: dict[str, Any],
    failed_steps: list[str],
) -> list[str]:
    if not ok:
        return [f"Fix failed bootstrap step: {name}." for name in failed_steps]
    if dry_run:
        actions = ["Rerun without dry_run when you want to copy the skill package and write requested outputs."]
        if _has_planned_overwrite(install_report):
            actions.append("Add --force when applying this dry-run if the listed installed skill overwrites are intended.")
        return actions
    actions: list[str] = []
    if config_output:
        actions.append(f"Review generated MCP config snippet at {config_output} before merging it into the AI client.")
    else:
        actions.append("Review steps.mcp_config.config_text before merging it into the AI client.")
    actions.extend(
        [
            "Restart the AI client after adding the MCP server config.",
            "Run mcp-smoke or the MCP mcp_smoke tool again after the client restart.",
        ]
    )
    if mcp_config_report.get("smoke_test_command"):
        actions.append("The report includes steps.mcp_config.smoke_test_command for repeatable server verification.")
    return actions


def _has_planned_overwrite(install_report: dict[str, Any]) -> bool:
    return any(item.get("action") == "would_overwrite" for item in install_report.get("files", []))
