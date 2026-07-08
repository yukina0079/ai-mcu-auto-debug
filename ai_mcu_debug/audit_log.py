from __future__ import annotations

import json
import os
from contextvars import ContextVar, Token
from datetime import datetime, timezone
from pathlib import Path
from typing import Any


DEFAULT_AUDIT_LOG = Path("debug_runs/audit_events.jsonl")
_AUDIT_CONTEXT: ContextVar[dict[str, Any]] = ContextVar("ai_mcu_debug_audit_context", default={})


def push_audit_context(**values: Any) -> Token[dict[str, Any]]:
    """Attach run-scoped evidence metadata to nested audit events."""

    current = dict(_AUDIT_CONTEXT.get())
    current.update({key: value for key, value in values.items() if value is not None})
    return _AUDIT_CONTEXT.set(current)


def pop_audit_context(token: Token[dict[str, Any]]) -> None:
    _AUDIT_CONTEXT.reset(token)


def current_audit_context() -> dict[str, Any]:
    return dict(_AUDIT_CONTEXT.get())


def append_audit_event(
    event: str,
    args: dict[str, Any] | None = None,
    result: Any | None = None,
    ok: bool | None = None,
    log_path: Path | None = None,
) -> dict[str, Any]:
    """Append a deterministic audit event without raising on logging failure."""

    selected_log = log_path or _audit_log_path()
    context = current_audit_context()
    record = {
        "timestamp": datetime.now(timezone.utc).isoformat(),
        "event": event,
        **context,
        "args": args or {},
        "result": result,
        "ok": ok,
    }
    try:
        selected_log.parent.mkdir(parents=True, exist_ok=True)
        with selected_log.open("a", encoding="utf-8") as file:
            file.write(json.dumps(record, ensure_ascii=False, default=str) + "\n")
    except OSError as exc:
        record["audit_log_error"] = str(exc)
    return record


def _audit_log_path() -> Path:
    configured = os.environ.get("AI_MCU_DEBUG_AUDIT_LOG")
    return Path(configured) if configured else DEFAULT_AUDIT_LOG


def audit_log_path() -> Path:
    return _audit_log_path()


def tail_text(value: str, max_chars: int = 4000) -> str:
    if len(value) <= max_chars:
        return value
    return value[-max_chars:]
