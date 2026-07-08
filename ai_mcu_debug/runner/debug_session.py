from __future__ import annotations

import json
from dataclasses import asdict
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from ai_mcu_debug.audit_log import append_audit_event
from ai_mcu_debug.diagnostics import analyze_debug_failure
from ai_mcu_debug.interfaces import DebugAdapter
from ai_mcu_debug.models import DebugTask


class AutoDebugSession:
    def __init__(self, adapter: DebugAdapter, report_dir: Path = Path("debug_runs")) -> None:
        self.adapter = adapter
        self.report_dir = report_dir
        self.report_dir.mkdir(parents=True, exist_ok=True)

    def run(self, task: DebugTask) -> dict[str, Any]:
        report: dict[str, Any] = {
            "task": task.name,
            "started_at": datetime.now(timezone.utc).isoformat(),
            "breakpoints": [],
            "registers": {},
            "memory": [],
            "steps": 0,
            "events": [],
        }
        try:
            self.adapter.connect()
            if task.reset_before_run:
                self.adapter.reset(halt=True)
                report["events"].append("reset_halt")
            if task.launch_from_vector_table is not None:
                vector = self.adapter.read_memory(task.launch_from_vector_table, 8)
                if len(vector.data) < 8:
                    raise RuntimeError(f"Could not read vector table at 0x{task.launch_from_vector_table:x}")
                initial_sp = int.from_bytes(vector.data[0:4], "little")
                reset_handler = int.from_bytes(vector.data[4:8], "little")
                self.adapter.write_register("sp", initial_sp)
                self.adapter.write_register("pc", reset_handler)
                report["events"].append("launch_from_vector_table")
                report["launch"] = {
                    "vector_table": f"0x{task.launch_from_vector_table:x}",
                    "initial_sp": f"0x{initial_sp:x}",
                    "reset_handler": f"0x{reset_handler:x}",
                }
            for location in task.breakpoints:
                breakpoint = self.adapter.set_breakpoint(location)
                report["breakpoints"].append(asdict(breakpoint))
            if task.breakpoints:
                self.adapter.resume()
                report["events"].append("resume_to_breakpoint")
                stop_output = self.adapter.wait_for_stop(task.break_timeout_s)
                report["events"].append("stopped_after_resume")
                report["stop_output"] = stop_output
            for _ in range(task.step_count):
                self.adapter.step()
                report["steps"] += 1
                step_output = self.adapter.wait_for_stop(task.break_timeout_s)
                report["events"].append("stopped_after_step")
                report.setdefault("step_outputs", []).append(step_output)
            for register in task.registers:
                value = self.adapter.read_register(register)
                report["registers"][register] = f"0x{value.value:x}"
            for address, length in task.memory_reads:
                block = self.adapter.read_memory(address, length)
                report["memory"].append(
                    {
                        "address": f"0x{block.address:x}",
                        "length": length,
                        "data_hex": block.data.hex(),
                    }
                )
            report["conclusions"] = _analyze_debug_report(report)
            report["ok"] = True
        except Exception as exc:
            report["ok"] = False
            report["error"] = str(exc)
            report["diagnostics"] = self.adapter.diagnostics()
            report["failure_analysis"] = analyze_debug_failure(str(exc), report["diagnostics"])
            report["conclusions"] = [f"debug_session_failed: {exc}"]
        finally:
            report["finished_at"] = datetime.now(timezone.utc).isoformat()
            self._write_report(task.name, report)
            append_audit_event(
                "debug_session",
                args={"task": task.name},
                result={
                    "ok": report.get("ok"),
                    "events": report.get("events", []),
                    "conclusions": report.get("conclusions", []),
                },
                ok=bool(report.get("ok")),
            )
            if task.record_path:
                self._append_task_record(task.record_path, report)
            try:
                self.adapter.close()
            except Exception as close_error:
                report["close_error"] = str(close_error)
                self._write_report(task.name, report)
        return report

    def _write_report(self, name: str, report: dict[str, Any]) -> None:
        safe_name = "".join(char if char.isalnum() or char in "-_" else "_" for char in name)
        path = self.report_dir / f"{safe_name}.json"
        with path.open("w", encoding="utf-8") as file:
            json.dump(report, file, indent=2, ensure_ascii=False)

    def _append_task_record(self, path: Path, report: dict[str, Any]) -> None:
        path.parent.mkdir(parents=True, exist_ok=True)
        record = {
            "task": report["task"],
            "ok": report.get("ok", False),
            "finished_at": report.get("finished_at"),
            "conclusions": report.get("conclusions", []),
            "report_path": str(self.report_dir / f"{report['task']}.json"),
        }
        with path.open("a", encoding="utf-8") as file:
            file.write(json.dumps(record, ensure_ascii=False) + "\n")


def _analyze_debug_report(report: dict[str, Any]) -> list[str]:
    conclusions: list[str] = []
    registers = report.get("registers", {})
    pc = _parse_report_int(registers.get("pc"))
    sp = _parse_report_int(registers.get("sp"))
    lr = _parse_report_int(registers.get("lr"))
    xpsr = _parse_report_int(registers.get("xpsr"))

    if pc in {0, 0xFFFFFFFF}:
        conclusions.append("pc_invalid: PC is zero or erased flash value.")
    elif pc is not None:
        conclusions.append(f"pc_observed: PC=0x{pc:x}.")

    if sp in {0, 0xFFFFFFFF}:
        conclusions.append("sp_invalid: SP is zero or erased flash value.")
    elif sp is not None:
        conclusions.append(f"sp_observed: SP=0x{sp:x}.")

    if lr in {0, 0xFFFFFFFF}:
        conclusions.append("lr_suspicious: LR is zero or erased flash value.")

    if xpsr is not None and (xpsr & (1 << 24)) == 0:
        conclusions.append("xpsr_thumb_bit_clear: Cortex-M xPSR T bit is not set.")

    for memory in report.get("memory", []):
        data_hex = memory.get("data_hex", "")
        if not data_hex:
            conclusions.append(f"memory_empty: read at {memory.get('address')} returned no bytes.")
        elif set(data_hex.lower()) == {"0"}:
            conclusions.append(f"memory_all_zero: read at {memory.get('address')} returned only zero bytes.")
        elif set(data_hex.lower()) <= {"f"}:
            conclusions.append(f"memory_all_ff: read at {memory.get('address')} returned only 0xff bytes.")

    if not conclusions:
        conclusions.append("no_obvious_fault: register and memory snapshot has no built-in heuristic warning.")
    return conclusions


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
