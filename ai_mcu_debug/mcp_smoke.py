from __future__ import annotations

import json
import subprocess
import sys
from pathlib import Path
from typing import Any


DEFAULT_REQUIRED_TOOLS = (
    "workflow_plan",
    "workflow_run",
    "capability_audit",
    "mcp_config",
    "mcp_smoke",
    "run_ai_debug",
    "debug_op_guarded",
    "workspace_status",
)


def smoke_test_mcp(
    *,
    project_path: str | Path = ".",
    python_executable: str | Path | None = None,
    required_tools: list[str] | tuple[str, ...] | None = None,
    timeout_s: float = 10.0,
    output: str | Path | None = None,
) -> dict[str, Any]:
    """Launch the stdio MCP server once and verify JSON-RPC tool discovery."""

    project = Path(project_path).resolve()
    selected_python = str(python_executable or sys.executable)
    required = list(required_tools or DEFAULT_REQUIRED_TOOLS)
    command = [selected_python, "-m", "ai_mcu_debug.cli", "mcp-server"]
    requests = [
        {
            "jsonrpc": "2.0",
            "id": 1,
            "method": "initialize",
            "params": {"protocolVersion": "2025-06-18"},
        },
        {"jsonrpc": "2.0", "id": 2, "method": "tools/list", "params": {}},
    ]
    stdin = "\n".join(json.dumps(item, ensure_ascii=False) for item in requests) + "\n"

    if not project.exists():
        return _finalize(
            {
                "ok": False,
                "status": "project_path_missing",
                "project": str(project),
                "command": command,
                "required_tools": required,
            },
            output,
        )

    try:
        completed = subprocess.run(
            command,
            cwd=project,
            input=stdin,
            text=True,
            encoding="utf-8",
            errors="replace",
            capture_output=True,
            timeout=timeout_s,
            check=False,
        )
    except subprocess.TimeoutExpired as exc:
        return _finalize(
            {
                "ok": False,
                "status": "timeout",
                "project": str(project),
                "command": command,
                "timeout_s": timeout_s,
                "stdout_tail": _tail_text(exc.stdout),
                "stderr_tail": _tail_text(exc.stderr),
                "required_tools": required,
            },
            output,
        )

    responses = _parse_json_lines(completed.stdout)
    if completed.returncode != 0:
        return _finalize(
            {
                "ok": False,
                "status": "mcp_server_failed",
                "project": str(project),
                "command": command,
                "returncode": completed.returncode,
                "responses": responses,
                "stdout_tail": _tail_text(completed.stdout),
                "stderr_tail": _tail_text(completed.stderr),
                "required_tools": required,
            },
            output,
        )

    tools_response = next((item for item in responses if item.get("id") == 2), None)
    if not tools_response or "result" not in tools_response:
        return _finalize(
            {
                "ok": False,
                "status": "tools_list_missing",
                "project": str(project),
                "command": command,
                "returncode": completed.returncode,
                "responses": responses,
                "stdout_tail": _tail_text(completed.stdout),
                "stderr_tail": _tail_text(completed.stderr),
                "required_tools": required,
            },
            output,
        )

    tools = tools_response.get("result", {}).get("tools", [])
    tool_names = sorted(str(item.get("name")) for item in tools if isinstance(item, dict) and item.get("name"))
    missing = sorted(set(required) - set(tool_names))
    return _finalize(
        {
            "ok": not missing,
            "status": "ok" if not missing else "missing_required_tools",
            "project": str(project),
            "command": command,
            "returncode": completed.returncode,
            "tools_found": len(tool_names),
            "required_tools": required,
            "missing_tools": missing,
            "tool_names": tool_names,
            "stderr_tail": _tail_text(completed.stderr),
        },
        output,
    )


def _parse_json_lines(text: str | bytes | None) -> list[dict[str, Any]]:
    if not text:
        return []
    if isinstance(text, bytes):
        text = text.decode("utf-8", errors="replace")
    responses: list[dict[str, Any]] = []
    for line in text.splitlines():
        if not line.strip():
            continue
        try:
            value = json.loads(line)
        except json.JSONDecodeError:
            responses.append({"parse_error": line})
            continue
        if isinstance(value, dict):
            responses.append(value)
    return responses


def _tail_text(text: str | bytes | None, *, limit: int = 4000) -> str:
    if text is None:
        return ""
    if isinstance(text, bytes):
        text = text.decode("utf-8", errors="replace")
    return text[-limit:]


def _finalize(report: dict[str, Any], output: str | Path | None) -> dict[str, Any]:
    if output:
        output_path = Path(output)
        output_path.parent.mkdir(parents=True, exist_ok=True)
        output_path.write_text(json.dumps(report, indent=2, ensure_ascii=False, default=str), encoding="utf-8")
        report["output"] = str(output_path)
    return report
