from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from ai_mcu_debug.doctor import run_doctor


def write_detected_openocd_target(
    output_path: Path,
    executable: str,
    interface_cfg: str,
    target_cfg: str,
    remote: str = "localhost:3333",
    report: dict[str, Any] | None = None,
) -> dict[str, Any]:
    doctor_report = report or run_doctor()
    checks = {item["name"]: item for item in doctor_report["checks"]}
    target_gdb = checks.get("target_gdb", {})
    openocd = checks.get("openocd", {})
    if not target_gdb.get("available"):
        raise RuntimeError("target_gdb is not available; run doctor for installation guidance.")
    if not openocd.get("available"):
        raise RuntimeError("openocd is not available; run doctor for installation guidance.")

    config = {
        "backend": "openocd-gdb",
        "executable": executable,
        "gdb_path": target_gdb["path"],
        "remote": remote,
        "cwd": ".",
        "log_path": "debug_runs/debug_commands.jsonl",
        "server_command": [
            openocd["path"],
            "-f",
            interface_cfg,
            "-f",
            target_cfg,
            "-c",
            "init; reset halt",
        ],
        "server_startup_delay_s": 2.0,
        "connect_retries": 5,
        "connect_retry_delay_s": 1.0,
        "recover_on_disconnect": True,
        "command_retries": 2,
    }
    output_path.parent.mkdir(parents=True, exist_ok=True)
    with output_path.open("w", encoding="utf-8") as file:
        json.dump(config, file, indent=2, ensure_ascii=False)
    return config
