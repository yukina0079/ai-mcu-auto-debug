from __future__ import annotations

from pathlib import Path

from ai_mcu_debug.api import setup_project as setup_project_api
from ai_mcu_debug.bootstrap import setup_project


ROOT = Path(__file__).resolve().parents[1]
PROJECT = ROOT / "examples/firmware/stm32f103_blinky"
SVD = ROOT / "examples/svd/STM32F103_min.svd"
LINKER = PROJECT / "linker.stm32f103rct6.ld"
STARTUP = PROJECT / "src/startup_stm32f103.c"
DATASHEET = ROOT / "examples/docs/stm32f103_datasheet_notes.md"
ERRATA = ROOT / "examples/docs/stm32f103_errata_notes.md"


def test_setup_project_prepares_context_and_workspace(tmp_path: Path) -> None:
    report = setup_project(
        project_path=PROJECT,
        output_dir=tmp_path / ".embeddedskills",
        context_path=tmp_path / "mcu_context.json",
        chip="STM32F103RCT6",
        svd_path=SVD,
        linker_path=LINKER,
        startup_path=STARTUP,
        extra_docs=[("datasheet", DATASHEET), ("errata", ERRATA)],
        force=True,
        doctor_runner=_ready_doctor,
        probe_scanner=_ready_probe,
    )

    assert report["ok"] is True
    assert report["status"] == "ready_for_ai_debug"
    assert (tmp_path / "mcu_context.json").exists()
    assert (tmp_path / ".embeddedskills/config.json").exists()
    assert (tmp_path / ".embeddedskills/build.json").exists()
    assert (tmp_path / ".embeddedskills/debug.target.json").exists()
    assert "ai-debug --mode dry-run" in "\n".join(report["next_actions"])
    assert {item["kind"] for item in report["artifacts"]} >= {"mcu_context", "workspace_config", "workspace_state"}


def test_setup_project_asks_for_missing_user_documents(tmp_path: Path, monkeypatch) -> None:
    monkeypatch.chdir(tmp_path)
    project = tmp_path / "empty_project"
    project.mkdir()

    report = setup_project(
        project_path=project,
        output_dir=tmp_path / ".embeddedskills",
        context_path=tmp_path / "mcu_context.json",
        chip="STM32F103RCT6",
        doctor_runner=_ready_doctor,
        probe_scanner=_ready_probe,
    )

    assert report["ok"] is False
    assert report["status"] == "awaiting_user_documents"
    assert "workspace_init" not in report
    assert any(item["kind"] == "svd" for item in report["document_intake"]["required_requests"])
    assert "Ask the user" in report["next_actions"][0]


def test_setup_project_api_exposes_bootstrap_flow(tmp_path: Path, monkeypatch) -> None:
    monkeypatch.chdir(tmp_path)
    project = tmp_path / "empty_project"
    project.mkdir()

    report = setup_project_api(project=project, context=tmp_path / "mcu_context.json", chip="STM32F103RCT6", scan_probes=False)

    assert report["ok"] is False
    assert report["status"] == "awaiting_user_documents"
    assert report["document_intake"]["policy"]["web_search_allowed"] is False


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
