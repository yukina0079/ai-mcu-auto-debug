from __future__ import annotations

import json
from dataclasses import asdict
from pathlib import Path
from typing import Any

from .audit_log import append_audit_event, current_audit_context
from .models import DebugCommandRecord


class JsonlCommandLogger:
    def __init__(self, log_path: Path) -> None:
        self.log_path = log_path
        self.log_path.parent.mkdir(parents=True, exist_ok=True)

    def record(self, command: str, args: dict[str, Any], result: Any, ok: bool) -> None:
        entry = DebugCommandRecord(command=command, args=args, result=result, ok=ok)
        context = current_audit_context()
        payload = {**asdict(entry), **context}
        with self.log_path.open("a", encoding="utf-8") as file:
            file.write(json.dumps(payload, ensure_ascii=False) + "\n")
        append_audit_event(
            "debug_command",
            args={"command": command, **args},
            result=result,
            ok=ok,
        )
