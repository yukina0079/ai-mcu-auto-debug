from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from ai_mcu_debug.interfaces import DebugAdapter
from ai_mcu_debug.models import DebugTask
from ai_mcu_debug.runner.debug_session import AutoDebugSession


REQUIRED_CORE_REGISTERS = ("pc", "sp", "lr", "xpsr")


class FirstPhaseAcceptance:
    """Hardware acceptance wrapper for first-stage MCU debug requirements."""

    def __init__(self, adapter: DebugAdapter, report_dir: Path = Path("debug_runs")) -> None:
        self.adapter = adapter
        self.report_dir = report_dir

    def run(self, task: DebugTask) -> dict[str, Any]:
        debug_report = AutoDebugSession(self.adapter, self.report_dir).run(task)
        acceptance = _evaluate_first_phase(debug_report)
        report = {"ok": all(item["ok"] for item in acceptance), "acceptance": acceptance, "debug_report": debug_report}
        path = self.report_dir / f"{task.name}_first_phase_acceptance.json"
        path.parent.mkdir(parents=True, exist_ok=True)
        with path.open("w", encoding="utf-8") as file:
            json.dump(report, file, indent=2, ensure_ascii=False)
        return report


def _evaluate_first_phase(debug_report: dict[str, Any]) -> list[dict[str, Any]]:
    registers = debug_report.get("registers", {})
    events = debug_report.get("events", [])
    pc = _parse_report_int(registers.get("pc"))
    sp = _parse_report_int(registers.get("sp"))
    xpsr = _parse_report_int(registers.get("xpsr"))
    stop_output = str(debug_report.get("stop_output", ""))
    stopped_at_breakpoint = "breakpoint-hit" in stop_output
    sane_core_registers = (
        all(register in registers for register in REQUIRED_CORE_REGISTERS)
        and pc not in {None, 0, 0xFFFFFFFF}
        and sp not in {None, 0, 0xFFFFFFFF}
        and bool(xpsr is not None and xpsr & (1 << 24))
    )
    return [
        {
            "name": "read_core_registers",
            "ok": sane_core_registers,
            "evidence": {register: registers.get(register) for register in REQUIRED_CORE_REGISTERS},
        },
        {
            "name": "read_memory_address",
            "ok": any(memory.get("data_hex") for memory in debug_report.get("memory", [])),
            "evidence": debug_report.get("memory", []),
        },
        {
            "name": "reset_and_halt",
            "ok": "reset_halt" in events,
            "evidence": events,
        },
        {
            "name": "breakpoint_and_stop",
            "ok": bool(debug_report.get("breakpoints")) and stopped_at_breakpoint,
            "evidence": {"breakpoints": debug_report.get("breakpoints"), "events": events, "stop_output": stop_output},
        },
        {
            "name": "single_step",
            "ok": int(debug_report.get("steps", 0)) > 0 and "stopped_after_step" in events,
            "evidence": {"steps": debug_report.get("steps", 0), "events": events},
        },
        {
            "name": "debug_record",
            "ok": bool(debug_report.get("finished_at")) and "conclusions" in debug_report,
            "evidence": {
                "finished_at": debug_report.get("finished_at"),
                "conclusions": debug_report.get("conclusions", []),
            },
        },
    ]


def _parse_report_int(value: Any) -> int | None:
    if value is None:
        return None
    if isinstance(value, int):
        return value
    if isinstance(value, str):
        try:
            return int(value, 0)
        except ValueError:
            return None
    return None
