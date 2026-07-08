from __future__ import annotations

import json
from pathlib import Path

from ai_mcu_debug.api import generate_mcp_client_config
from ai_mcu_debug.mcp_config import generate_mcp_config


ROOT = Path(__file__).resolve().parents[1]


def test_generate_codex_mcp_config_contains_stdio_server() -> None:
    report = generate_mcp_config(project_path=ROOT, client="codex", python_executable="python")
    escaped_root = str(ROOT).replace("\\", "\\\\")

    assert report["ok"] is True
    assert report["server"]["command"] == "python"
    assert report["server"]["args"] == ["-m", "ai_mcu_debug.cli", "mcp-server"]
    assert report["smoke_test_command"] == ["python", "-m", "ai_mcu_debug.cli", "mcp-smoke", "--project", str(ROOT)]
    assert f'cwd = "{escaped_root}"' in report["config_text"]
    assert "[mcp_servers.ai_mcu_debug]" in report["config_text"]


def test_generate_generic_json_mcp_config_is_parseable(tmp_path: Path) -> None:
    output = tmp_path / "mcp.json"

    report = generate_mcp_config(project_path=ROOT, client="generic-json", output=output)

    assert report["ok"] is True
    payload = json.loads(output.read_text(encoding="utf-8"))
    assert payload["mcpServers"]["ai_mcu_debug"]["cwd"] == str(ROOT)


def test_generate_mcp_config_rejects_unknown_client() -> None:
    report = generate_mcp_config(project_path=ROOT, client="unknown")

    assert report["ok"] is False
    assert report["status"] == "unsupported_client"


def test_generate_mcp_client_config_api() -> None:
    report = generate_mcp_client_config(project=ROOT, client="claude-desktop")

    assert report["ok"] is True
    assert "mcpServers" in report["config"]
