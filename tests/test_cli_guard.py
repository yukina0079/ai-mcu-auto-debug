from __future__ import annotations

import json
import subprocess
import sys
from pathlib import Path

from ai_mcu_debug.cli import _guard_debug_op
from ai_mcu_debug.knowledge import build_mcu_context


ROOT = Path(__file__).resolve().parents[1]


def _context(tmp_path: Path) -> Path:
    path = tmp_path / "mcu_context.json"
    build_mcu_context(
        chip="STM32F103C8",
        svd_path=ROOT / "examples/svd/STM32F103_min.svd",
        output_path=path,
        linker_path=ROOT / "examples/firmware/stm32f103_blinky/linker.ld",
    )
    return path


def test_guard_blocks_flash_write_memory(tmp_path: Path) -> None:
    guard = _guard_debug_op(
        "write-memory",
        {"address": "0x08000000", "data_hex": "01020304"},
        str(_context(tmp_path)),
        force=False,
    )

    assert guard is not None
    assert guard["ok"] is False
    assert guard["checks"][0]["reason"] == "dangerous_address_range"


def test_guard_requires_context_for_write_operations() -> None:
    guard = _guard_debug_op(
        "write-register",
        {"register": "GPIOC.CRH", "value": "0x00200000"},
        None,
        force=False,
    )

    assert guard is not None
    assert guard["ok"] is False
    assert guard["reason"] == "mcu_context_required_for_write_operation"


def test_guard_requires_context_for_peripheral_register_reads() -> None:
    guard = _guard_debug_op(
        "read-register",
        {"register": "GPIOC.CRH"},
        None,
        force=False,
    )

    assert guard is not None
    assert guard["ok"] is False
    assert guard["reason"] == "mcu_context_required_for_peripheral_register_read"


def test_guard_allows_core_register_reads_without_context() -> None:
    guard = _guard_debug_op(
        "read-register",
        {"register": "pc"},
        None,
        force=False,
    )

    assert guard is None


def test_guard_explains_peripheral_register_before_read(tmp_path: Path) -> None:
    params = {"register": "GPIOC.CRH"}

    guard = _guard_debug_op(
        "read-register",
        params,
        str(_context(tmp_path)),
        force=False,
    )

    assert guard is not None
    assert guard["ok"] is True
    assert guard["checks"][0]["reference"]["register"] == "GPIOC.CRH"
    assert params["mapped_register"]["address"] == 0x40011004


def test_guard_validates_write_register_with_context(tmp_path: Path) -> None:
    guard = _guard_debug_op(
        "write-register",
        {"register": "GPIOC.CRH", "value": "0x00000001"},
        str(_context(tmp_path)),
        force=False,
    )

    assert guard is not None
    assert guard["ok"] is False
    assert guard["checks"][0]["reason"] == ["reserved_bits_set"]


def test_guard_blocks_reserved_register_bits(tmp_path: Path) -> None:
    guard = _guard_debug_op(
        "write-memory",
        {"address": "0x40011004", "data_hex": "01000000"},
        str(_context(tmp_path)),
        force=False,
    )

    assert guard is not None
    assert guard["ok"] is False
    assert guard["checks"][1]["reason"] == ["reserved_bits_set"]


def test_cli_guard_block_writes_audit_event(tmp_path: Path, monkeypatch) -> None:
    target = tmp_path / "target.json"
    target.write_text('{"backend":"openocd-gdb","server_command":["openocd"]}', encoding="utf-8")
    audit_log = tmp_path / "audit_events.jsonl"
    monkeypatch.setenv("AI_MCU_DEBUG_AUDIT_LOG", str(audit_log))

    completed = subprocess.run(
        [
            sys.executable,
            "-m",
            "ai_mcu_debug.cli",
            "debug-op",
            "--target",
            str(target),
            "write-register",
            "--register",
            "GPIOC.CRH",
            "--value",
            "0x1",
        ],
        capture_output=True,
        text=True,
        check=False,
    )

    assert completed.returncode == 2
    records = [json.loads(line) for line in audit_log.read_text(encoding="utf-8").splitlines()]
    assert records[0]["event"] == "debug_guard_blocked"
    assert records[0]["args"]["operation"] == "write-register"
