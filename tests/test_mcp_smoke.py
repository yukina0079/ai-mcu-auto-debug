from __future__ import annotations

import sys
from pathlib import Path

from ai_mcu_debug.api import smoke_test_mcp_server
from ai_mcu_debug.mcp_smoke import smoke_test_mcp


ROOT = Path(__file__).resolve().parents[1]


def test_smoke_test_mcp_reports_required_tools() -> None:
    report = smoke_test_mcp(
        project_path=ROOT,
        python_executable=sys.executable,
        required_tools=["workflow_plan", "mcp_config", "capability_audit"],
    )

    assert report["ok"] is True
    assert report["status"] == "ok"
    assert report["tools_found"] >= 3
    assert report["missing_tools"] == []


def test_smoke_test_mcp_reports_missing_required_tool() -> None:
    report = smoke_test_mcp(
        project_path=ROOT,
        python_executable=sys.executable,
        required_tools=["not_a_real_tool"],
    )

    assert report["ok"] is False
    assert report["status"] == "missing_required_tools"
    assert report["missing_tools"] == ["not_a_real_tool"]


def test_smoke_test_mcp_api(tmp_path: Path) -> None:
    output = tmp_path / "mcp_smoke.json"

    report = smoke_test_mcp_server(
        project=ROOT,
        python_executable=sys.executable,
        required_tools=["mcp_smoke"],
        output=output,
    )

    assert report["ok"] is True
    assert output.exists()
