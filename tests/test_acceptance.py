from __future__ import annotations

from pathlib import Path

from tests.test_debug_session import FakeDebugAdapter

from ai_mcu_debug.models import DebugTask
from ai_mcu_debug.runner.acceptance import FirstPhaseAcceptance, _evaluate_first_phase


def test_evaluate_first_phase_acceptance_from_debug_report() -> None:
    debug_report = {
        "registers": {"pc": "0x8000100", "sp": "0x20001000", "lr": "0xfffffffd", "xpsr": "0x1000000"},
        "memory": [{"address": "0x20000000", "data_hex": "0102"}],
        "events": ["reset_halt", "resume_to_breakpoint", "stopped_after_resume", "stopped_after_step"],
        "breakpoints": [{"id": "1", "location": "main"}],
        "steps": 1,
        "stop_output": '*stopped,reason="breakpoint-hit"',
        "finished_at": "now",
        "conclusions": ["pc_observed"],
    }

    acceptance = _evaluate_first_phase(debug_report)

    assert all(item["ok"] for item in acceptance)


def test_evaluate_first_phase_rejects_zero_register_snapshot() -> None:
    debug_report = {
        "registers": {"pc": "0x0", "sp": "0x0", "lr": "0x0", "xpsr": "0x0"},
        "memory": [{"address": "0x20000000", "data_hex": "00"}],
        "events": ["reset_halt", "resume_to_breakpoint", "stopped_after_resume"],
        "breakpoints": [{"id": "1", "location": "main"}],
        "steps": 1,
        "stop_output": '*stopped,reason="signal-received"',
        "finished_at": "now",
        "conclusions": ["pc_invalid"],
    }

    acceptance = {item["name"]: item for item in _evaluate_first_phase(debug_report)}

    assert acceptance["read_core_registers"]["ok"] is False
    assert acceptance["breakpoint_and_stop"]["ok"] is False
    assert acceptance["single_step"]["ok"] is False


def test_first_phase_acceptance_writes_report(tmp_path: Path) -> None:
    task = DebugTask(
        name="acceptance",
        breakpoints=["main"],
        registers=["pc", "sp", "lr", "xpsr"],
        memory_reads=[(0x20000000, 4)],
        step_count=1,
    )

    report = FirstPhaseAcceptance(FakeDebugAdapter(), tmp_path).run(task)

    assert report["ok"] is True
    assert (tmp_path / "acceptance_first_phase_acceptance.json").exists()
