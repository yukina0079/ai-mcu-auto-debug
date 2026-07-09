from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from ai_mcu_debug.capability_audit import audit_capabilities
from ai_mcu_debug.doctor import run_doctor
from ai_mcu_debug.mcp_config import generate_mcp_config
from ai_mcu_debug.mcp_smoke import smoke_test_mcp


def bootstrap_agent_environment(
    *,
    project_path: str | Path = ".",
    client: str = "generic-json",
    python_executable: str | Path | None = None,
    server_name: str = "ai_mcu_debug",
    output: str | Path | None = None,
    timeout_s: float = 10.0,
    dry_run: bool = True,
    include_vision: bool = False,
) -> dict[str, Any]:
    """Run the portable non-hardware bootstrap that any AI coding agent can follow."""

    project = Path(project_path).resolve()
    doctor_report = run_doctor()
    mcp_config_report = generate_mcp_config(
        project_path=project,
        client=client,
        python_executable=python_executable,
        server_name=server_name,
    )
    smoke_report = smoke_test_mcp(
        project_path=project,
        python_executable=python_executable,
        timeout_s=timeout_s,
    )
    capability_report = audit_capabilities(project_path=project, include_vision=include_vision)

    steps = {
        "doctor": doctor_report,
        "mcp_config": mcp_config_report,
        "mcp_smoke": smoke_report,
        "capability_audit": capability_report,
    }
    failed_steps = [name for name, report in steps.items() if not report.get("ok")]
    report: dict[str, Any] = {
        "ok": not failed_steps,
        "status": "would_bootstrap_agent" if dry_run and not failed_steps else ("agent_ready" if not failed_steps else "agent_bootstrap_failed"),
        "project": str(project),
        "client": client,
        "dry_run": dry_run,
        "policy": {
            "hardware_touched": False,
            "global_client_config_modified": False,
            "flash_allowed": False,
            "repair_allowed": False,
            "force_allowed": False,
            "vision_required": include_vision,
        },
        "steps": steps,
        "failed_steps": failed_steps,
        "agent_first_prompt": _agent_first_prompt(),
        "next_actions": _next_actions(failed_steps=failed_steps, client=client),
    }
    if output:
        output_path = Path(output)
        output_path.parent.mkdir(parents=True, exist_ok=True)
        output_path.write_text(json.dumps(report, indent=2, ensure_ascii=False, default=str), encoding="utf-8")
        report["output"] = str(output_path)
    return report


def _agent_first_prompt() -> str:
    return (
        "Use this repository as an AI MCU automation toolchain. Run agent-bootstrap first, "
        "then use workflow-plan before hardware actions. Do not flash, repair, force writes, "
        "or run parallel hardware debug sessions unless I explicitly approve the current board and operation."
    )


def _next_actions(*, failed_steps: list[str], client: str) -> list[str]:
    if failed_steps:
        return [f"Fix failed bootstrap step: {name}." for name in failed_steps]
    return [
        "Give AGENT_QUICKSTART.md and this report to the AI coding agent.",
        "Use steps.mcp_config.config_text when the selected client supports MCP configuration.",
        "For clients without MCP support, call the ai-mcu-debug CLI commands directly from the repository root.",
        f"Selected client profile: {client}.",
    ]
