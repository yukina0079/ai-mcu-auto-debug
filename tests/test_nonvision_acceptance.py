from __future__ import annotations

import json
from pathlib import Path

from ai_mcu_debug.nonvision_acceptance import run_nonvision_acceptance


ROOT = Path(__file__).resolve().parents[1]
PROJECT = ROOT / "examples/firmware/stm32f103_blinky"
SVD = ROOT / "examples/svd/STM32F103_min.svd"
LINKER = PROJECT / "linker.stm32f103rct6.ld"
STARTUP = PROJECT / "src/startup_stm32f103.c"
DATASHEET = ROOT / "examples/docs/stm32f103_datasheet_notes.md"
ERRATA = ROOT / "examples/docs/stm32f103_errata_notes.md"


def test_nonvision_acceptance_runs_setup_dry_run_and_handoff(tmp_path: Path) -> None:
    report = run_nonvision_acceptance(
        project_path=PROJECT,
        output_dir=tmp_path / ".embeddedskills",
        context_path=tmp_path / "mcu_context.json",
        report_dir=tmp_path / "report",
        handoff_project_path=tmp_path,
        chip="STM32F103RCT6",
        svd_path=SVD,
        linker_path=LINKER,
        startup_path=STARTUP,
        extra_docs=[("datasheet", DATASHEET), ("errata", ERRATA)],
        force=True,
        doctor_runner=_ready_doctor,
        probe_scanner=_ready_probe,
        ai_debug_runner=_fake_ai_debug_ok,
    )

    assert report["ok"] is True
    assert report["status"] == "ok"
    assert [step["name"] for step in report["steps"]] == [
        "setup-project",
        "ai-debug-dry-run",
        "export-handoff",
        "replay-handoff-validate",
    ]
    assert (tmp_path / "report/nonvision_acceptance_report.json").exists()
    assert (tmp_path / "report/ai_debug_dry_run/ai_debug_report.json").exists()
    assert (tmp_path / "report/replay_handoff_report.json").exists()
    assert Path(report["handoff"]["manifest"]).exists()
    assert report["handoff_replay"]["ok"] is True
    assert report["handoff_replay"]["execute"] is False
    handoff_manifest = json.loads(Path(report["handoff"]["manifest"]).read_text(encoding="utf-8"))
    artifact_names = {Path(item["source"]).name for item in handoff_manifest["artifacts"]}
    assert {"nonvision_acceptance_report.json", "ai_debug_report.json"} <= artifact_names
    assert report["policy"]["flash_allowed"] is False
    assert report["policy"]["repair_allowed"] is False
    assert report["policy"]["vision_allowed"] is False
    assert report["policy"]["handoff_replay_execute"] is False


def test_nonvision_acceptance_stops_when_user_documents_are_missing(tmp_path: Path, monkeypatch) -> None:
    monkeypatch.chdir(tmp_path)
    project = tmp_path / "empty_project"
    project.mkdir()

    report = run_nonvision_acceptance(
        project_path=project,
        output_dir=tmp_path / ".embeddedskills",
        context_path=tmp_path / "mcu_context.json",
        report_dir=tmp_path / "report",
        handoff_project_path=tmp_path,
        chip="STM32F103RCT6",
        doctor_runner=_ready_doctor,
        probe_scanner=_ready_probe,
        ai_debug_runner=_fake_ai_debug_should_not_run,
    )

    assert report["ok"] is False
    assert report["status"] == "awaiting_user_documents"
    assert [step["name"] for step in report["steps"]] == ["setup-project"]
    assert "ai_debug" not in report
    assert "handoff" not in report


def test_nonvision_acceptance_fails_when_handoff_replay_is_blocked(tmp_path: Path) -> None:
    replay_report = tmp_path / "report/replay_handoff_report.json"

    report = run_nonvision_acceptance(
        project_path=PROJECT,
        output_dir=tmp_path / ".embeddedskills",
        context_path=tmp_path / "mcu_context.json",
        report_dir=tmp_path / "report",
        handoff_project_path=tmp_path,
        chip="STM32F103RCT6",
        svd_path=SVD,
        linker_path=LINKER,
        startup_path=STARTUP,
        extra_docs=[("datasheet", DATASHEET), ("errata", ERRATA)],
        force=True,
        doctor_runner=_ready_doctor,
        probe_scanner=_ready_probe,
        ai_debug_runner=_fake_ai_debug_ok,
        handoff_replayer=lambda **kwargs: _fake_replay_blocked(replay_report),
    )

    assert report["ok"] is False
    assert report["status"] == "replay_blocked_by_policy"
    assert [step["name"] for step in report["steps"]] == [
        "setup-project",
        "ai-debug-dry-run",
        "export-handoff",
        "replay-handoff-validate",
    ]
    assert report["next_actions"] == ["Inspect blocked replay commands."]


def _fake_ai_debug_ok(**kwargs) -> dict[str, object]:
    report_dir = Path(kwargs["report_dir"])
    report_dir.mkdir(parents=True, exist_ok=True)
    report_path = report_dir / "ai_debug_report.json"
    report = {
        "ok": True,
        "status": "ok",
        "mode": "dry-run",
        "report_path": str(report_path),
        "next_actions": [],
    }
    report_path.write_text(json.dumps(report), encoding="utf-8")
    return report


def _fake_ai_debug_should_not_run(**kwargs) -> dict[str, object]:
    raise AssertionError("ai-debug dry-run should not run when setup-project asks for documents")


def _fake_replay_blocked(report_path: Path) -> dict[str, object]:
    report_path.parent.mkdir(parents=True, exist_ok=True)
    report = {
        "ok": False,
        "status": "replay_blocked_by_policy",
        "report_path": str(report_path),
        "next_actions": ["Inspect blocked replay commands."],
    }
    report_path.write_text(json.dumps(report), encoding="utf-8")
    return report


def _ready_doctor(debug_backend: str | None, build_backend: str | None) -> dict[str, object]:
    return {
        "ok": True,
        "debug_backend": debug_backend,
        "build_backend": build_backend,
        "checks": [
            {"name": "target_gdb", "available": True, "path": "C:/tools/arm-none-eabi-gdb.exe"},
            {"name": "openocd", "available": True, "path": "C:/tools/openocd.exe"},
            {"name": "cmake", "available": True, "path": "C:/tools/cmake.exe"},
        ],
        "recommendations": ["Toolchain looks ready for first-stage hardware acceptance."],
    }


def _ready_probe() -> dict[str, object]:
    return {"ok": True, "probes": [{"matched_usb_ids": ["CMSIS-DAP/DAPLink compatible probe"]}]}
