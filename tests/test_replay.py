from __future__ import annotations

import json
from pathlib import Path

from ai_mcu_debug.api import replay_debug_handoff
from ai_mcu_debug.replay import replay_handoff


ROOT = Path(__file__).resolve().parents[1]


def test_replay_handoff_dry_run_validates_safe_commands(tmp_path: Path) -> None:
    manifest = _manifest(
        tmp_path,
        [
            ["python", "-m", "ai_mcu_debug.cli", "workspace-status", "--config", ".embeddedskills/config.json"],
            ["python", "-m", "ai_mcu_debug.cli", "ai-debug", "--mode", "dry-run", "--workspace-config", ".embeddedskills/config.json"],
            ["python", "-m", "ai_mcu_debug.cli", "workflow-run", "--workspace-config", ".embeddedskills/config.json", "--no-hardware"],
        ],
    )

    report = replay_handoff(manifest_path=manifest, project_path=ROOT)

    assert report["ok"] is True
    assert report["status"] == "ready_to_replay"
    assert all(item["safe"] for item in report["commands"])


def test_replay_handoff_blocks_workflow_run_without_no_hardware(tmp_path: Path) -> None:
    manifest = _manifest(
        tmp_path,
        [["python", "-m", "ai_mcu_debug.cli", "workflow-run", "--workspace-config", ".embeddedskills/config.json"]],
    )

    report = replay_handoff(manifest_path=manifest, project_path=ROOT)

    assert report["ok"] is False
    assert report["status"] == "replay_blocked_by_policy"
    assert {item["code"] for item in report["diagnostics"]} == {"replay_workflow_run_may_touch_hardware"}


def test_replay_handoff_blocks_dangerous_commands(tmp_path: Path) -> None:
    manifest = _manifest(
        tmp_path,
        [["python", "-m", "ai_mcu_debug.cli", "ai-debug", "--mode", "run", "--allow-flash"]],
    )

    report = replay_handoff(manifest_path=manifest, project_path=ROOT)

    assert report["ok"] is False
    assert report["status"] == "replay_blocked_by_policy"
    codes = {item["code"] for item in report["diagnostics"]}
    assert "replay_dangerous_token_blocked" in codes
    assert "replay_ai_debug_not_dry_run" in codes


def test_replay_handoff_can_execute_safe_profile_command(tmp_path: Path) -> None:
    manifest = _manifest(tmp_path, [["python", "-m", "ai_mcu_debug.cli", "mcu-profile", "--chip", "STM32F103RCT6"]])

    report = replay_handoff(
        manifest_path=manifest,
        project_path=ROOT,
        execute=True,
        output_path=tmp_path / "replay_report.json",
    )

    assert report["ok"] is True
    assert report["status"] == "ok"
    assert report["commands"][0]["result"]["returncode"] == 0
    assert (tmp_path / "replay_report.json").exists()


def test_replay_debug_handoff_api_exposes_safe_dry_run(tmp_path: Path) -> None:
    manifest = _manifest(tmp_path, [["python", "-m", "ai_mcu_debug.cli", "mcu-profile", "--chip", "STM32F103RCT6"]])

    report = replay_debug_handoff(manifest=manifest, project=ROOT)

    assert report["ok"] is True
    assert report["status"] == "ready_to_replay"


def _manifest(tmp_path: Path, replay: list[list[str]]) -> Path:
    path = tmp_path / "handoff_manifest.json"
    path.write_text(json.dumps({"schema_version": 1, "replay": replay}), encoding="utf-8")
    return path
