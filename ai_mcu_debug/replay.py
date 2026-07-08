from __future__ import annotations

import json
import subprocess
from datetime import datetime, timezone
from pathlib import Path
from typing import Any


ALLOWED_CLI_COMMANDS = {
    "workspace-status",
    "doc-repo-sync",
    "prepare-mcu",
    "workflow-run",
    "ai-debug",
    "check-context",
    "doc-intake",
    "mcu-profile",
    "manifest-lint",
    "locate-docs",
}

DANGEROUS_TOKENS = {
    "flash",
    "debug",
    "debug-op",
    "debug-sequence",
    "accept-first-stage",
    "hardware-id",
    "connection-diagnose",
    "repair-build",
    "closed-loop",
    "--allow-flash",
    "--allow-repair",
    "--force",
}


def replay_handoff(
    *,
    manifest_path: Path,
    project_path: Path = Path("."),
    execute: bool = False,
    output_path: Path | None = None,
    timeout_s: float = 120.0,
    stop_on_failure: bool = True,
) -> dict[str, Any]:
    """Validate or execute safe replay commands from a handoff manifest."""

    report: dict[str, Any] = {
        "ok": False,
        "status": "started",
        "manifest": str(manifest_path),
        "project": str(project_path),
        "execute": execute,
        "started_at": datetime.now(timezone.utc).isoformat(),
        "commands": [],
        "diagnostics": [],
        "policy": {
            "allowed_cli_commands": sorted(ALLOWED_CLI_COMMANDS),
            "dangerous_tokens_blocked": sorted(DANGEROUS_TOKENS),
            "executes_only_with_execute": True,
        },
    }
    try:
        manifest = json.loads(manifest_path.read_text(encoding="utf-8-sig"))
    except (OSError, json.JSONDecodeError) as exc:
        report["status"] = "manifest_unreadable"
        report["diagnostics"].append(_diag("manifest_unreadable", blocks=True, error=str(exc)))
        return _finish(report, output_path)
    replay = manifest.get("replay")
    if not isinstance(replay, list):
        report["status"] = "manifest_missing_replay"
        report["diagnostics"].append(_diag("manifest_missing_replay", blocks=True))
        return _finish(report, output_path)

    command_specs = [_command_spec(item, index) for index, item in enumerate(replay)]
    report["commands"] = command_specs
    blockers = [diag for spec in command_specs for diag in spec["diagnostics"] if diag.get("blocks")]
    if blockers:
        report["status"] = "replay_blocked_by_policy"
        report["diagnostics"].extend(blockers)
        return _finish(report, output_path)

    if not execute:
        report["ok"] = True
        report["status"] = "ready_to_replay"
        report["next_actions"] = ["Rerun replay-handoff with --execute to run the safe replay commands."]
        return _finish(report, output_path)

    for spec in command_specs:
        result = _execute_command(spec["command"], project_path, timeout_s)
        spec["result"] = result
        if not result["ok"] and stop_on_failure:
            break
    failed = [spec for spec in command_specs if spec.get("result") and not spec["result"].get("ok")]
    skipped = [spec for spec in command_specs if "result" not in spec]
    report["ok"] = not failed and not skipped
    report["status"] = "ok" if report["ok"] else "replay_command_failed"
    if failed:
        report["diagnostics"].append(
            _diag(
                "replay_command_failed",
                blocks=True,
                command_index=failed[0]["index"],
                returncode=failed[0]["result"].get("returncode"),
            )
        )
    return _finish(report, output_path)


def _command_spec(item: Any, index: int) -> dict[str, Any]:
    if not isinstance(item, list) or not all(isinstance(part, str) for part in item):
        return {
            "index": index,
            "command": item,
            "safe": False,
            "diagnostics": [_diag("replay_command_not_string_list", blocks=True, command_index=index)],
        }
    diagnostics = _command_diagnostics(item, index)
    return {
        "index": index,
        "command": item,
        "safe": not any(diag.get("blocks") for diag in diagnostics),
        "diagnostics": diagnostics,
    }


def _command_diagnostics(command: list[str], index: int) -> list[dict[str, Any]]:
    diagnostics: list[dict[str, Any]] = []
    cli_index = _cli_command_index(command)
    if cli_index is None or cli_index >= len(command):
        diagnostics.append(_diag("replay_command_not_ai_mcu_debug_cli", blocks=True, command_index=index, command=command))
        return diagnostics
    cli_command = command[cli_index]
    if cli_command not in ALLOWED_CLI_COMMANDS:
        diagnostics.append(
            _diag(
                "replay_cli_command_not_allowed",
                blocks=True,
                command_index=index,
                cli_command=cli_command,
            )
        )
    lowered = {part.lower() for part in command}
    dangerous = sorted(lowered & DANGEROUS_TOKENS)
    if dangerous:
        diagnostics.append(_diag("replay_dangerous_token_blocked", blocks=True, command_index=index, tokens=dangerous))
    if cli_command == "ai-debug" and not _is_ai_debug_dry_run(command[cli_index + 1 :]):
        diagnostics.append(_diag("replay_ai_debug_not_dry_run", blocks=True, command_index=index))
    if cli_command == "workflow-run" and "--no-hardware" not in command[cli_index + 1 :]:
        diagnostics.append(_diag("replay_workflow_run_may_touch_hardware", blocks=True, command_index=index))
    return diagnostics


def _cli_command_index(command: list[str]) -> int | None:
    for index, part in enumerate(command):
        normalized = part.lower().replace("\\", "/")
        if normalized.endswith("ai_mcu_debug.cli"):
            return index + 1
        if normalized in {"ai-mcu-debug", "ai-mcu-debug.exe"}:
            return index + 1
    return None


def _is_ai_debug_dry_run(args: list[str]) -> bool:
    if "--mode" not in args:
        return False
    mode_index = args.index("--mode")
    return mode_index + 1 < len(args) and args[mode_index + 1] == "dry-run"


def _execute_command(command: list[str], project_path: Path, timeout_s: float) -> dict[str, Any]:
    try:
        completed = subprocess.run(
            command,
            cwd=project_path,
            capture_output=True,
            text=True,
            check=False,
            timeout=timeout_s,
        )
    except (OSError, subprocess.TimeoutExpired) as exc:
        return {
            "ok": False,
            "returncode": None,
            "stdout_tail": _tail(str(getattr(exc, "stdout", "") or "")),
            "stderr_tail": _tail(str(exc)),
            "error": str(exc),
        }
    return {
        "ok": completed.returncode == 0,
        "returncode": completed.returncode,
        "stdout_tail": _tail(completed.stdout),
        "stderr_tail": _tail(completed.stderr),
    }


def _tail(text: str, max_chars: int = 4000) -> str:
    return text[-max_chars:]


def _diag(code: str, blocks: bool, **extra: Any) -> dict[str, Any]:
    severity = "error" if blocks else "warning"
    return {"code": code, "severity": severity, "blocks": blocks, **extra}


def _finish(report: dict[str, Any], output_path: Path | None) -> dict[str, Any]:
    report["finished_at"] = datetime.now(timezone.utc).isoformat()
    if output_path:
        output_path.parent.mkdir(parents=True, exist_ok=True)
        output_path.write_text(json.dumps(report, indent=2, ensure_ascii=False, default=str), encoding="utf-8")
        report["report_path"] = str(output_path)
    return report
