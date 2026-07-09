from __future__ import annotations

from pathlib import Path

from ai_mcu_debug.agent_bootstrap import bootstrap_agent_environment
from ai_mcu_debug.api import bootstrap_agent


ROOT = Path(__file__).resolve().parents[1]


def test_agent_bootstrap_dry_run_is_non_hardware() -> None:
    report = bootstrap_agent_environment(project_path=ROOT, client="generic-json", dry_run=True)

    assert report["ok"] is True
    assert report["status"] == "would_bootstrap_agent"
    assert report["policy"]["hardware_touched"] is False
    assert report["policy"]["global_client_config_modified"] is False
    assert report["steps"]["capability_audit"]["status"] == "nonvision_ready"
    assert "agent" in report["agent_first_prompt"].lower()


def test_agent_bootstrap_api_supports_qoder_profile() -> None:
    report = bootstrap_agent(project=ROOT, client="qoder")

    assert report["ok"] is True
    assert report["client"] == "qoder"
    assert "mcpServers" in report["steps"]["mcp_config"]["config"]
