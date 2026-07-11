from __future__ import annotations

from pathlib import Path

from ai_mcu_debug.api import audit_project_capabilities
from ai_mcu_debug.capability_audit import audit_capabilities


ROOT = Path(__file__).resolve().parents[1]


def test_capability_audit_reports_nonvision_ready(tmp_path: Path) -> None:
    report = audit_capabilities(project_path=ROOT, output=tmp_path / "capabilities.json")

    assert report["ok"] is True
    assert report["status"] == "nonvision_ready"
    assert report["scope"]["vision_postponed"] is False
    assert report["scope"]["vision_available"] is True
    capability_ids = {item["id"] for item in report["capabilities"]}
    assert {
        "realtime_debug",
        "build_test_repair_loop",
        "signal_observation",
        "knowledge_guard",
        "user_document_intake",
        "safe_workflow_orchestration",
        "handoff_replay_audit",
        "skill_deployment",
        "safety_policy",
    } <= capability_ids
    safety = next(item for item in report["capabilities"] if item["id"] == "safety_policy")
    assert safety["ok"] is True
    assert (tmp_path / "capabilities.json").exists()


def test_capability_audit_can_include_vision_as_blocking() -> None:
    report = audit_capabilities(project_path=ROOT, include_vision=True)

    assert report["ok"] is True
    assert report["status"] == "vision_ready"
    vision = next(item for item in report["capabilities"] if item["id"] == "vision_loop")
    assert vision["blocking"] is True
    assert vision["status"] == "ok"


def test_capability_audit_api() -> None:
    report = audit_project_capabilities(project=ROOT)

    assert report["ok"] is True
    assert report["summary"]["mcp_tools_found"] >= 1
