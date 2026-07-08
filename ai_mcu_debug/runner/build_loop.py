from __future__ import annotations

from dataclasses import asdict
from datetime import datetime, timezone
from typing import Any

from ai_mcu_debug.interfaces import BuildAdapter, RepairAdapter


class BuildRepairSession:
    """Build -> optional AI repair -> rebuild loop."""

    def __init__(
        self,
        build_adapter: BuildAdapter,
        repair_adapter: RepairAdapter | None,
        max_iterations: int = 3,
    ) -> None:
        self.build_adapter = build_adapter
        self.repair_adapter = repair_adapter
        self.max_iterations = max(1, max_iterations)

    def run(self) -> dict[str, Any]:
        report: dict[str, Any] = {
            "started_at": datetime.now(timezone.utc).isoformat(),
            "attempts": [],
            "ok": False,
        }
        for attempt in range(1, self.max_iterations + 1):
            build_result = self.build_adapter.build()
            attempt_record: dict[str, Any] = {
                "attempt": attempt,
                "build": asdict(build_result),
            }
            report["attempts"].append(attempt_record)
            if build_result.ok:
                report["ok"] = True
                report["finished_at"] = datetime.now(timezone.utc).isoformat()
                return report
            if attempt >= self.max_iterations:
                report["stop_reason"] = "max_iterations_reached"
                break
            if not self.repair_adapter:
                report["stop_reason"] = "repair_command_not_configured"
                break
            repair_result = self.repair_adapter.repair_build(build_result, attempt)
            attempt_record["repair"] = asdict(repair_result)
            if not repair_result.ok:
                report["stop_reason"] = "repair_command_failed"
                break
        report["finished_at"] = datetime.now(timezone.utc).isoformat()
        return report
