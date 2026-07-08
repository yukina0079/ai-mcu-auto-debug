from __future__ import annotations

import json
from pathlib import Path

from ai_mcu_debug.config import load_build_config, load_debug_task, load_target_config


def test_load_target_config(tmp_path: Path) -> None:
    path = tmp_path / "target.json"
    path.write_text(
        json.dumps(
            {
                "backend": "openocd-gdb",
                "remote": "localhost:3333",
                "server_command": ["openocd", "-f", "board.cfg"],
                "server_startup_delay_s": 0.1,
                "connect_retries": 2,
                "recover_on_disconnect": True,
                "command_retries": 4,
            }
        ),
        encoding="utf-8",
    )

    config = load_target_config(path)

    assert config.backend == "openocd-gdb"
    assert config.remote == "localhost:3333"
    assert config.server_command == ["openocd", "-f", "board.cfg"]
    assert config.server_startup_delay_s == 0.1
    assert config.connect_retries == 2
    assert config.recover_on_disconnect is True
    assert config.command_retries == 4


def test_load_debug_task_hex_memory_address(tmp_path: Path) -> None:
    path = tmp_path / "task.json"
    path.write_text(
        json.dumps(
            {
                "name": "task",
                "record_path": "debug_runs/task_records.jsonl",
                "memory_reads": [{"address": "0x20000000", "length": 16}],
                "launch_from_vector_table": "0x08000000",
            }
        ),
        encoding="utf-8",
    )

    task = load_debug_task(path)

    assert task.memory_reads == [(0x20000000, 16)]
    assert task.launch_from_vector_table == 0x08000000
    assert task.record_path == Path("debug_runs/task_records.jsonl")


def test_load_build_config_keeps_extra_and_timeouts(tmp_path: Path) -> None:
    path = tmp_path / "build.json"
    path.write_text(
        json.dumps(
            {
                "backend": "platformio",
                "source_dir": ".",
                "build_command": ["pio", "run", "-e", "bluepill"],
                "command_timeout_s": 30,
                "runtime_log_timeout_s": 5,
                "extra": {"pio_env": "bluepill"},
            }
        ),
        encoding="utf-8",
    )

    config = load_build_config(path)

    assert config.backend == "platformio"
    assert config.command_timeout_s == 30
    assert config.runtime_log_timeout_s == 5
    assert config.extra == {"pio_env": "bluepill"}
