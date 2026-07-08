from __future__ import annotations

import json
import re
import subprocess
from dataclasses import asdict
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Callable

from ai_mcu_debug.diagnostics import analyze_debug_failure
from ai_mcu_debug.models import DebugTargetConfig


Runner = Callable[[list[str], Path, float], dict[str, Any]]


def run_openocd_connection_matrix(
    target: DebugTargetConfig,
    report_dir: Path,
    timeout_s: float = 12.0,
    runner: Runner | None = None,
) -> dict[str, Any]:
    """Try safe OpenOCD attach variants after a target connection failure.

    The matrix only attempts OpenOCD init/target discovery and optional reset
    assertion. It does not flash, erase, or write MCU memory/registers.
    """

    report_dir.mkdir(parents=True, exist_ok=True)
    report: dict[str, Any] = {
        "ok": False,
        "status": "unsupported_target",
        "started_at": datetime.now(timezone.utc).isoformat(),
        "target": _target_summary(target),
        "safety": {
            "flash_allowed": False,
            "erase_allowed": False,
            "register_write_allowed": False,
            "memory_write_allowed": False,
            "reset_assertion_allowed": True,
        },
        "attempts": [],
        "next_actions": [],
    }
    if target.backend != "openocd-gdb" or not target.server_command:
        report["next_actions"].append("Connection matrix currently supports OpenOCD target configs with server_command.")
        return _write_report(report, report_dir)

    run = runner or _run_command
    for variant in _matrix_variants():
        command = _variant_command(target.server_command, variant)
        result = run(command, target.server_cwd or target.cwd, timeout_s)
        output_tail = _output_tail(result.get("stdout", ""), result.get("stderr", ""))
        failure_analysis = analyze_debug_failure(
            "connection_matrix_attempt",
            {"server_output_tail": output_tail},
        )
        attempt = {
            "name": variant["name"],
            "description": variant["description"],
            "ok": _attempt_connected(result, output_tail),
            "returncode": result.get("returncode"),
            "command": command,
            "output_tail": output_tail,
            "failure_analysis": failure_analysis,
        }
        report["attempts"].append(attempt)
        if attempt["ok"]:
            break

    successful = next((attempt for attempt in report["attempts"] if attempt["ok"]), None)
    if successful:
        report["ok"] = True
        report["status"] = "connection_variant_succeeded"
        report["next_actions"].append(
            f"OpenOCD variant `{successful['name']}` connected. Update the target config with that speed/reset policy and rerun read-only acceptance."
        )
    else:
        report["status"] = "all_variants_failed"
        report["next_actions"].extend(_dedupe_matrix_actions(report["attempts"]))
    return _write_report(report, report_dir)


def _matrix_variants() -> list[dict[str, Any]]:
    return [
        {
            "name": "configured_speed",
            "description": "Use the configured OpenOCD command and force init/shutdown for a bounded probe.",
            "adapter_speed": None,
            "under_reset": False,
        },
        {
            "name": "swd_50khz",
            "description": "Retry at 50 kHz SWD clock.",
            "adapter_speed": 50,
            "under_reset": False,
        },
        {
            "name": "swd_10khz",
            "description": "Retry at 10 kHz SWD clock.",
            "adapter_speed": 10,
            "under_reset": False,
        },
        {
            "name": "under_reset_50khz",
            "description": "Retry at 50 kHz while asserting SRST during connect.",
            "adapter_speed": 50,
            "under_reset": True,
        },
        {
            "name": "under_reset_10khz",
            "description": "Retry at 10 kHz while asserting SRST during connect.",
            "adapter_speed": 10,
            "under_reset": True,
        },
    ]


def _variant_command(base_command: list[str], variant: dict[str, Any]) -> list[str]:
    command = _remove_bounded_probe_commands(base_command)
    if variant["adapter_speed"] is not None:
        command = _replace_or_append_c_command(command, "adapter speed", f"adapter speed {variant['adapter_speed']}")
    if variant["under_reset"]:
        command.extend(["-c", "reset_config srst_only srst_nogate connect_assert_srst"])
    command.extend(["-c", "init; targets; shutdown"])
    return command


def _remove_bounded_probe_commands(command: list[str]) -> list[str]:
    cleaned: list[str] = []
    index = 0
    while index < len(command):
        if index + 1 < len(command) and command[index] == "-c":
            lowered = command[index + 1].lower()
            if "shutdown" in lowered or lowered.strip().startswith("init"):
                index += 2
                continue
        cleaned.append(command[index])
        index += 1
    return cleaned


def _replace_or_append_c_command(command: list[str], prefix: str, value: str) -> list[str]:
    replaced = list(command)
    index = 0
    while index < len(replaced) - 1:
        if replaced[index] == "-c" and replaced[index + 1].lower().strip().startswith(prefix):
            replaced[index + 1] = value
            return replaced
        index += 1
    replaced.extend(["-c", value])
    return replaced


def _run_command(command: list[str], cwd: Path, timeout_s: float) -> dict[str, Any]:
    try:
        result = subprocess.run(
            command,
            cwd=cwd,
            text=True,
            errors="replace",
            capture_output=True,
            timeout=timeout_s,
            check=False,
        )
        return {
            "returncode": result.returncode,
            "stdout": result.stdout,
            "stderr": result.stderr,
        }
    except subprocess.TimeoutExpired as exc:
        return {
            "returncode": None,
            "stdout": exc.stdout or "",
            "stderr": (exc.stderr or "") + "\nconnection_matrix_timeout",
            "timeout": True,
        }
    except OSError as exc:
        return {
            "returncode": None,
            "stdout": "",
            "stderr": str(exc),
            "os_error": True,
        }


def _attempt_connected(result: dict[str, Any], output_tail: list[str]) -> bool:
    if result.get("returncode") != 0:
        return False
    combined = "\n".join(output_tail).lower()
    failure_terms = (
        "cannot read idr",
        "error connecting dp",
        "no ack",
        "open failed",
        "no cmsis-dap device found",
        "communication failure",
    )
    if any(term in combined for term in failure_terms):
        return False
    success_terms = ("target halted", "examined", "cortex_m", "stm32f1x.cpu")
    return any(term in combined for term in success_terms) or "shutdown command invoked" in combined


def _output_tail(stdout: str, stderr: str, limit: int = 80) -> list[str]:
    lines = [line.rstrip() for line in f"{stdout}\n{stderr}".splitlines()]
    return lines[-limit:]


def _target_summary(target: DebugTargetConfig) -> dict[str, Any]:
    data = asdict(target)
    data["cwd"] = str(target.cwd)
    data["log_path"] = str(target.log_path)
    data["server_cwd"] = str(target.server_cwd) if target.server_cwd else None
    return data


def _dedupe_matrix_actions(attempts: list[dict[str, Any]]) -> list[str]:
    actions: list[str] = []
    for attempt in attempts:
        for action in attempt.get("failure_analysis", {}).get("next_actions", []):
            if action not in actions:
                actions.append(action)
    if not actions:
        actions.append("Inspect OpenOCD output tails from connection_diagnostics attempts.")
    if any(_line_mentions_nreset_low(attempt.get("output_tail", [])) for attempt in attempts):
        actions.append("At least one attempt sampled nRESET=0; inspect reset wiring and reset capacitor.")
    return actions


def _line_mentions_nreset_low(lines: list[str]) -> bool:
    return bool(re.search(r"\bnRESET\s*=\s*0\b", "\n".join(lines)))


def _write_report(report: dict[str, Any], report_dir: Path) -> dict[str, Any]:
    report["finished_at"] = datetime.now(timezone.utc).isoformat()
    path = report_dir / "connection_diagnostics.json"
    report["report_path"] = str(path)
    path.write_text(json.dumps(report, indent=2, ensure_ascii=False, default=str), encoding="utf-8")
    return report
