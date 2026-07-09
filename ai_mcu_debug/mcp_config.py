from __future__ import annotations

import json
import sys
from pathlib import Path
from typing import Any


SUPPORTED_CLIENTS = {
    "codex",
    "generic-json",
    "claude-desktop",
    "claude-code",
    "opencode",
    "trae",
    "qoder",
}
DEFAULT_SERVER_NAME = "ai_mcu_debug"


def generate_mcp_config(
    *,
    project_path: str | Path = ".",
    client: str = "codex",
    python_executable: str | Path | None = None,
    server_name: str = DEFAULT_SERVER_NAME,
    output: str | Path | None = None,
) -> dict[str, Any]:
    """Generate a portable MCP client config snippet for this repo's server."""

    project = Path(project_path).resolve()
    selected_python = str(python_executable or sys.executable)
    if client not in SUPPORTED_CLIENTS:
        return {
            "ok": False,
            "status": "unsupported_client",
            "client": client,
            "supported_clients": sorted(SUPPORTED_CLIENTS),
        }

    checks = _checks(project=project, python_executable=selected_python)
    ok = all(item["ok"] for item in checks)
    server = {
        "type": "stdio",
        "command": selected_python,
        "args": ["-m", "ai_mcu_debug.cli", "mcp-server"],
        "cwd": str(project),
    }
    if client == "codex":
        config = {"mcp_servers": {server_name: server}}
        config_text = _codex_toml(server_name, server)
        target_hint = "Append this TOML table to Codex config.toml after reviewing it."
    else:
        config = {"mcpServers": {server_name: server}}
        config_text = json.dumps(config, indent=2, ensure_ascii=False)
        target_hint = _json_target_hint(client)

    report: dict[str, Any] = {
        "ok": ok,
        "status": "ok" if ok else "environment_not_ready",
        "client": client,
        "server_name": server_name,
        "project": str(project),
        "server": server,
        "smoke_test_command": [
            selected_python,
            "-m",
            "ai_mcu_debug.cli",
            "mcp-smoke",
            "--project",
            str(project),
        ],
        "config": config,
        "config_text": config_text,
        "checks": checks,
        "next_actions": [
            target_hint,
            "Run the smoke_test_command before editing client config if you want to verify the server first.",
            "Restart the AI client after adding the MCP server config.",
            "Run the MCP tool mcp_smoke or capability_audit from the client to confirm wiring.",
        ],
    }
    if output:
        output_path = Path(output)
        output_path.parent.mkdir(parents=True, exist_ok=True)
        output_path.write_text(config_text + "\n", encoding="utf-8")
        report["output"] = str(output_path)
    return report


def _checks(*, project: Path, python_executable: str) -> list[dict[str, Any]]:
    return [
        {
            "name": "project_path_exists",
            "ok": project.exists(),
            "path": str(project),
        },
        {
            "name": "ai_mcu_debug_package_exists",
            "ok": (project / "ai_mcu_debug" / "cli.py").exists(),
            "path": str(project / "ai_mcu_debug" / "cli.py"),
        },
        {
            "name": "python_executable_set",
            "ok": bool(python_executable),
            "path": python_executable,
        },
    ]


def _codex_toml(server_name: str, server: dict[str, Any]) -> str:
    lines = [
        f"[mcp_servers.{server_name}]",
        f"type = {_toml_string(str(server['type']))}",
        f"command = {_toml_string(str(server['command']))}",
        f"args = {_toml_array([str(item) for item in server['args']])}",
        f"cwd = {_toml_string(str(server['cwd']))}",
    ]
    return "\n".join(lines)


def _json_target_hint(client: str) -> str:
    if client == "claude-desktop":
        return "Merge this JSON object into Claude Desktop's MCP server configuration after reviewing it."
    if client in {"claude-code", "opencode", "trae", "qoder"}:
        return (
            "Use this as a generic stdio MCP server definition for the selected AI coding client. "
            "If that client does not expose an MCP config file, use the CLI flow from AGENT_QUICKSTART.md."
        )
    return "Merge this JSON object into the client's MCP configuration."


def _toml_string(value: str) -> str:
    return json.dumps(value, ensure_ascii=False)


def _toml_array(values: list[str]) -> str:
    return "[" + ", ".join(_toml_string(value) for value in values) + "]"
