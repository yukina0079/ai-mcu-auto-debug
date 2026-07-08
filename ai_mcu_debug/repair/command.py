from __future__ import annotations

import json
import subprocess
from dataclasses import asdict
from pathlib import Path

from ai_mcu_debug.audit_log import append_audit_event, tail_text
from ai_mcu_debug.interfaces import RepairAdapter
from ai_mcu_debug.models import BuildResult, RepairResult


class CommandRepairAdapter(RepairAdapter):
    """Delegates code repair to an existing AI coding CLI through stdin JSON."""

    def __init__(self, command: list[str], cwd: Path = Path("."), timeout_s: float = 600.0) -> None:
        self.command = command
        self.cwd = cwd
        self.timeout_s = timeout_s

    def repair_build(self, result: BuildResult, attempt: int) -> RepairResult:
        context = {
            "attempt": attempt,
            "instruction": "Fix the project build errors, keep changes minimal, then exit.",
            "build_result": asdict(result),
        }
        try:
            completed = subprocess.run(
                self.command,
                cwd=self.cwd,
                input=json.dumps(context, ensure_ascii=False),
                capture_output=True,
                text=True,
                timeout=self.timeout_s,
                check=False,
            )
        except (OSError, subprocess.TimeoutExpired) as exc:
            result = RepairResult(
                ok=False,
                command=self.command,
                stdout=getattr(exc, "stdout", "") or "",
                stderr=str(exc),
                returncode=-1,
            )
            append_audit_event(
                "repair_command",
                args={"command": self.command, "cwd": str(self.cwd), "attempt": attempt},
                result={
                    "returncode": result.returncode,
                    "stdout_tail": tail_text(result.stdout),
                    "stderr_tail": tail_text(result.stderr),
                },
                ok=False,
            )
            return result
        result = RepairResult(
            ok=completed.returncode == 0,
            command=self.command,
            stdout=completed.stdout,
            stderr=completed.stderr,
            returncode=completed.returncode,
        )
        append_audit_event(
            "repair_command",
            args={"command": self.command, "cwd": str(self.cwd), "attempt": attempt},
            result={
                "returncode": result.returncode,
                "stdout_tail": tail_text(result.stdout),
                "stderr_tail": tail_text(result.stderr),
            },
            ok=result.ok,
        )
        return result
