from __future__ import annotations

from dataclasses import asdict
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from ai_mcu_debug.interfaces import BuildAdapter, DebugAdapter, RepairAdapter
from ai_mcu_debug.models import DebugTask
from ai_mcu_debug.runner.build_loop import BuildRepairSession
from ai_mcu_debug.runner.debug_session import AutoDebugSession


class ClosedLoopSession:
    """Code repair/build -> flash -> smoke test -> optional hardware debug."""

    def __init__(
        self,
        build_adapter: BuildAdapter,
        repair_adapter: RepairAdapter | None,
        max_repair_iterations: int,
        debug_adapter: DebugAdapter | None = None,
        debug_task: DebugTask | None = None,
        report_dir: Path = Path("debug_runs"),
    ) -> None:
        self.build_adapter = build_adapter
        self.repair_adapter = repair_adapter
        self.max_repair_iterations = max_repair_iterations
        self.debug_adapter = debug_adapter
        self.debug_task = debug_task
        self.report_dir = report_dir

    def run(self) -> dict[str, Any]:
        report: dict[str, Any] = {
            "started_at": datetime.now(timezone.utc).isoformat(),
            "ok": False,
        }
        build_report = BuildRepairSession(
            self.build_adapter,
            self.repair_adapter,
            self.max_repair_iterations,
        ).run()
        report["build_repair"] = build_report
        if not build_report.get("ok"):
            report["stop_reason"] = "build_repair_failed"
            report["finished_at"] = datetime.now(timezone.utc).isoformat()
            return report

        flash_result = self.build_adapter.flash()
        report["flash"] = asdict(flash_result)
        if not flash_result.ok:
            report["stop_reason"] = "flash_failed"
            report["finished_at"] = datetime.now(timezone.utc).isoformat()
            return report

        smoke_result = self.build_adapter.smoke_test()
        report["smoke_test"] = asdict(smoke_result)
        if not smoke_result.ok:
            report["stop_reason"] = "smoke_test_failed"
            report["finished_at"] = datetime.now(timezone.utc).isoformat()
            return report

        if self.debug_adapter and self.debug_task:
            report["debug"] = AutoDebugSession(self.debug_adapter, self.report_dir).run(self.debug_task)
            if not report["debug"].get("ok"):
                report["stop_reason"] = "debug_failed"
                report["finished_at"] = datetime.now(timezone.utc).isoformat()
                return report

        report["ok"] = True
        report["finished_at"] = datetime.now(timezone.utc).isoformat()
        return report
