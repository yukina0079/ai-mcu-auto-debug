from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from .models import BuildConfig, DebugTargetConfig, DebugTask


def load_target_config(path: Path) -> DebugTargetConfig:
    data = _load_json(path)
    return DebugTargetConfig(
        backend=data["backend"],
        executable=data.get("executable"),
        gdb_path=data.get("gdb_path", "arm-none-eabi-gdb"),
        remote=data.get("remote", "localhost:3333"),
        cwd=Path(data.get("cwd", ".")),
        log_path=Path(data.get("log_path", "debug_runs/debug_commands.jsonl")),
        server_command=data.get("server_command"),
        server_cwd=Path(data["server_cwd"]) if data.get("server_cwd") else None,
        server_startup_delay_s=float(data.get("server_startup_delay_s", 1.0)),
        connect_retries=int(data.get("connect_retries", 3)),
        connect_retry_delay_s=float(data.get("connect_retry_delay_s", 1.0)),
        recover_on_disconnect=bool(data.get("recover_on_disconnect", True)),
        command_retries=int(data.get("command_retries", 2)),
        extra=data.get("extra", {}),
    )


def load_build_config(path: Path) -> BuildConfig:
    data = _load_json(path)
    return BuildConfig(
        backend=data["backend"],
        build_dir=Path(data.get("build_dir", "build")),
        source_dir=Path(data.get("source_dir", ".")),
        configure_command=data.get("configure_command"),
        build_command=data.get("build_command"),
        flash_command=data.get("flash_command"),
        smoke_test_command=data.get("smoke_test_command"),
        runtime_log_command=data.get("runtime_log_command"),
        repair_command=data.get("repair_command"),
        command_timeout_s=(float(data["command_timeout_s"]) if data.get("command_timeout_s") is not None else None),
        runtime_log_timeout_s=(
            float(data["runtime_log_timeout_s"]) if data.get("runtime_log_timeout_s") is not None else None
        ),
        repair_timeout_s=float(data.get("repair_timeout_s", 600.0)),
        max_repair_iterations=int(data.get("max_repair_iterations", 3)),
        extra=data.get("extra", {}),
    )


def load_debug_task(path: Path) -> DebugTask:
    data = _load_json(path)
    memory_reads = [(int(item["address"], 0), int(item["length"])) for item in data.get("memory_reads", [])]
    return DebugTask(
        name=data["name"],
        breakpoints=data.get("breakpoints", []),
        registers=data.get("registers", []),
        memory_reads=memory_reads,
        reset_before_run=data.get("reset_before_run", True),
        launch_from_vector_table=(
            int(str(data["launch_from_vector_table"]), 0)
            if data.get("launch_from_vector_table") is not None
            else None
        ),
        step_count=int(data.get("step_count", 0)),
        break_timeout_s=float(data.get("break_timeout_s", 10.0)),
        record_path=Path(data["record_path"]) if data.get("record_path") else None,
    )


def _load_json(path: Path) -> dict[str, Any]:
    with path.open("r", encoding="utf-8") as file:
        return json.load(file)
