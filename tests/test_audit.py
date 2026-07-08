from __future__ import annotations

import json
from pathlib import Path

from ai_mcu_debug.audit import export_handoff
from ai_mcu_debug.audit_log import append_audit_event, pop_audit_context, push_audit_context


def test_export_handoff_collects_workspace_reports_and_replay(tmp_path: Path) -> None:
    project = tmp_path / "project"
    project.mkdir()
    config_dir = project / ".embeddedskills"
    config_dir.mkdir()
    (config_dir / "config.json").write_text(
        json.dumps(
            {
                "schema_version": 1,
                "project": ".",
                "mcu": {"chip": "STM32F103RCT6", "context": "mcu_context.json"},
                "build": {"config": ".embeddedskills/build.json"},
                "knowledge_repo": {
                    "url": "https://github.com/example/mcu-docs.git",
                    "local_path": "knowledge_repos/mcu-docs",
                },
            }
        ),
        encoding="utf-8",
    )
    (config_dir / "build.json").write_text('{"backend":"cmake"}', encoding="utf-8")
    (project / "mcu_context.json").write_text('{"chip":"STM32F103RCT6"}', encoding="utf-8")
    report_dir = project / "debug_runs" / "ai_debug"
    report_dir.mkdir(parents=True)
    (report_dir / "ai_debug_report.json").write_text('{"ok":true}', encoding="utf-8")
    (report_dir / "evidence.md").write_text("# Evidence\n", encoding="utf-8")
    (project / "debug_runs" / "debug_commands.jsonl").write_text('{"command":"read_register"}\n', encoding="utf-8")
    manifest = project / "knowledge_repos" / "mcu-docs" / "vendors" / "st" / "stm32f1" / "STM32F103RCT6" / "manifest.json"
    manifest.parent.mkdir(parents=True)
    manifest.write_text('{"chip":"STM32F103RCT6","documents":[]}', encoding="utf-8")

    report = export_handoff(output=tmp_path / "handoff", project_path=project)

    assert report["ok"] is True
    package = Path(report["package_dir"])
    assert (package / "handoff_manifest.json").exists()
    assert (package / "README.md").exists()
    artifact_paths = {item["package_path"] for item in report["artifacts"]}
    assert "artifacts/.embeddedskills/config.json" in artifact_paths
    assert "artifacts/mcu_context.json" in artifact_paths
    assert "artifacts/debug_runs/ai_debug/ai_debug_report.json" in artifact_paths
    assert "artifacts/debug_runs/ai_debug/evidence.md" in artifact_paths
    assert "artifacts/debug_runs/debug_commands.jsonl" in artifact_paths
    assert any("doc-repo-sync" in command for command in report["replay"])
    assert any(command[:5] == ["python", "-m", "ai_mcu_debug.cli", "workspace-status", "--config"] for command in report["replay"])
    ai_debug_replay = next(command for command in report["replay"] if "ai-debug" in command)
    assert "--workspace-config" in ai_debug_replay
    workflow_run_replay = next(command for command in report["replay"] if "workflow-run" in command)
    assert "--workspace-config" in workflow_run_replay
    assert "--no-hardware" in workflow_run_replay


def test_export_handoff_can_write_zip(tmp_path: Path) -> None:
    project = tmp_path / "project"
    project.mkdir()
    (project / "mcu_context.json").write_text("{}", encoding="utf-8")

    report = export_handoff(output=tmp_path / "handoff.zip", project_path=project, zip_output=True)

    assert report["ok"] is True
    assert Path(report["zip"]).exists()


def test_export_handoff_skips_existing_handoff_packages(tmp_path: Path) -> None:
    project = tmp_path / "project"
    project.mkdir()
    (project / "mcu_context.json").write_text("{}", encoding="utf-8")
    old_handoff = project / "debug_runs" / "old" / "handoff"
    old_artifacts = old_handoff / "artifacts" / "debug_runs" / "old"
    old_artifacts.mkdir(parents=True)
    (old_handoff / "handoff_manifest.json").write_text('{"schema_version":1}', encoding="utf-8")
    (old_handoff / "README.md").write_text("# MCU Debug Handoff Package\n", encoding="utf-8")
    (old_artifacts / "ai_debug_report.json").write_text('{"ok":true}', encoding="utf-8")

    report = export_handoff(output=tmp_path / "handoff", project_path=project)

    assert report["ok"] is True
    artifact_paths = {item["package_path"] for item in report["artifacts"]}
    assert "artifacts/debug_runs/old/handoff/handoff_manifest.json" not in artifact_paths
    assert "artifacts/debug_runs/old/handoff/artifacts/debug_runs/old/ai_debug_report.json" not in artifact_paths


def test_export_handoff_rejects_project_root_output(tmp_path: Path) -> None:
    project = tmp_path / "project"
    project.mkdir()

    report = export_handoff(output=project, project_path=project)

    assert report["ok"] is False
    assert report["status"] == "unsafe_output_path"


def test_append_audit_event_writes_jsonl(tmp_path: Path) -> None:
    log = tmp_path / "audit_events.jsonl"

    append_audit_event(
        "read_register",
        args={"register": "pc"},
        result={"value": "0x08000000"},
        ok=True,
        log_path=log,
    )

    records = [json.loads(line) for line in log.read_text(encoding="utf-8").splitlines()]
    assert records[0]["event"] == "read_register"
    assert records[0]["args"]["register"] == "pc"
    assert records[0]["ok"] is True


def test_audit_context_adds_run_metadata(tmp_path: Path) -> None:
    log = tmp_path / "audit_events.jsonl"
    token = push_audit_context(run_id="run-test", step_id="build")
    try:
        append_audit_event("build_command", ok=True, log_path=log)
    finally:
        pop_audit_context(token)

    record = json.loads(log.read_text(encoding="utf-8").splitlines()[0])
    assert record["run_id"] == "run-test"
    assert record["step_id"] == "build"
