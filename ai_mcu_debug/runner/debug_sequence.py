from __future__ import annotations

import json
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from ai_mcu_debug.interfaces import DebugAdapter
from ai_mcu_debug.runner.realtime_ops import execute_debug_operation


class DebugSequenceSession:
    """Runs multiple real-time debug operations through one target connection."""

    def __init__(self, adapter: DebugAdapter, report_dir: Path = Path("debug_runs")) -> None:
        self.adapter = adapter
        self.report_dir = report_dir
        self.report_dir.mkdir(parents=True, exist_ok=True)

    def run(self, name: str, operations: list[dict[str, Any]]) -> dict[str, Any]:
        report: dict[str, Any] = {
            "name": name,
            "started_at": datetime.now(timezone.utc).isoformat(),
            "operations": [],
            "ok": False,
        }
        self.adapter.connect()
        try:
            for index, item in enumerate(operations, start=1):
                operation = str(item["operation"])
                params = dict(item.get("params", {}))
                result = execute_debug_operation(self.adapter, operation, params)
                report["operations"].append({"index": index, "request": item, "result": result})
            report["ok"] = all(operation["result"].get("ok") for operation in report["operations"])
            return report
        except Exception as exc:
            report["error"] = str(exc)
            raise
        finally:
            report["finished_at"] = datetime.now(timezone.utc).isoformat()
            self._write_report(name, report)
            self.adapter.close()

    def _write_report(self, name: str, report: dict[str, Any]) -> None:
        safe_name = "".join(char if char.isalnum() or char in "-_" else "_" for char in name)
        path = self.report_dir / f"{safe_name}_debug_sequence.json"
        with path.open("w", encoding="utf-8") as file:
            json.dump(report, file, indent=2, ensure_ascii=False)
