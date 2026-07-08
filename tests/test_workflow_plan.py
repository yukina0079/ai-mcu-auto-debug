from __future__ import annotations

from pathlib import Path

from ai_mcu_debug.knowledge import prepare_mcu
from ai_mcu_debug.workflow_plan import plan_workflow


ROOT = Path(__file__).resolve().parents[1]
PROJECT = ROOT / "examples/firmware/stm32f103_blinky"
SVD = ROOT / "examples/svd/STM32F103_min.svd"
LINKER = PROJECT / "linker.stm32f103rct6.ld"
STARTUP = PROJECT / "src/startup_stm32f103.c"
DATASHEET = ROOT / "examples/docs/stm32f103_datasheet_notes.md"
ERRATA = ROOT / "examples/docs/stm32f103_errata_notes.md"


def assert_enriched_tool_call(call: dict) -> None:
    assert call["tool"]
    assert isinstance(call["arguments"], dict)
    assert call["cli"].startswith("python -m ai_mcu_debug.cli ")
    assert call["cli_args"][:3] == ["python", "-m", "ai_mcu_debug.cli"]
    safety = call["safety"]
    assert safety["flash_allowed"] is False
    assert safety["repair_allowed"] is False
    assert safety["vision_allowed"] is False
    assert safety["web_search_allowed"] is False
    assert "writes_files" in safety
    assert "touches_hardware" in safety
    assert "requires_approval" in safety


def test_workflow_plan_asks_for_missing_user_documents(tmp_path: Path) -> None:
    project = tmp_path / "empty_project"
    project.mkdir()

    report = plan_workflow(project_path=project, context_path=tmp_path / "mcu_context.json", chip="STM32F103RCT6")

    assert report["ok"] is False
    assert report["status"] == "awaiting_user_documents"
    assert any(item["required"] for item in report["user_requests"])
    assert report["recommended_tool_calls"] == []
    assert report["policy"]["web_search_allowed"] is False


def test_workflow_plan_recommends_context_preparation_with_cli_and_safety(tmp_path: Path) -> None:
    context = tmp_path / "mcu_context.json"

    report = plan_workflow(
        project_path=PROJECT,
        context_path=context,
        chip="STM32F103RCT6",
        svd_path=SVD,
        linker_path=LINKER,
        startup_path=STARTUP,
        extra_docs=[("datasheet", DATASHEET), ("errata", ERRATA)],
    )

    assert report["status"] == "context_not_ready"
    for call in report["recommended_tool_calls"]:
        assert_enriched_tool_call(call)
    prepare = report["recommended_tool_calls"][0]
    assert prepare["tool"] == "prepare_mcu_context"
    assert "prepare-mcu" in prepare["cli"]
    assert prepare["safety"]["side_effects"] is True
    assert prepare["safety"]["writes_files"] is True
    assert prepare["safety"]["touches_hardware"] is False
    check = report["recommended_tool_calls"][1]
    assert check["tool"] == "check_mcu_context"
    assert check["safety"]["side_effects"] is False


def test_workflow_plan_recommends_workspace_initialization_when_context_is_ready(tmp_path: Path) -> None:
    context = tmp_path / "mcu_context.json"
    prepared = prepare_mcu(
        project_path=PROJECT,
        output_path=context,
        chip="STM32F103RCT6",
        svd_path=SVD,
        linker_path=LINKER,
        startup_path=STARTUP,
        extra_docs=[("datasheet", DATASHEET), ("errata", ERRATA)],
    )
    assert prepared["ok"] is True

    report = plan_workflow(
        project_path=PROJECT,
        context_path=context,
        workspace_config=tmp_path / ".embeddedskills/config.json",
        chip="STM32F103RCT6",
    )

    assert report["status"] == "workspace_not_ready"
    for call in report["recommended_tool_calls"]:
        assert_enriched_tool_call(call)
    assert report["recommended_tool_calls"][0]["tool"] == "init_workspace"
    assert report["recommended_tool_calls"][0]["safety"]["writes_files"] is True
    assert report["recommended_tool_calls"][0]["safety"]["touches_hardware"] is False
    assert report["recommended_tool_calls"][1]["tool"] == "workspace_status"
    assert report["recommended_tool_calls"][1]["safety"]["side_effects"] is False


def test_workflow_plan_recommends_nonvision_debug_when_workspace_is_ready(tmp_path: Path) -> None:
    context = tmp_path / "mcu_context.json"
    prepared = prepare_mcu(
        project_path=PROJECT,
        output_path=context,
        chip="STM32F103RCT6",
        svd_path=SVD,
        linker_path=LINKER,
        startup_path=STARTUP,
        extra_docs=[("datasheet", DATASHEET), ("errata", ERRATA)],
    )
    assert prepared["ok"] is True
    build_config = tmp_path / "build.json"
    build_config.write_text("{}", encoding="utf-8")
    target_config = tmp_path / "debug.target.json"
    target_config.write_text("{}", encoding="utf-8")
    task_config = tmp_path / "debug_task.json"
    task_config.write_text("{}", encoding="utf-8")
    config_dir = tmp_path / ".embeddedskills"
    config_dir.mkdir()
    (config_dir / "config.json").write_text(
        (
            '{"schema_version":1,'
            f'"project":"{PROJECT.as_posix()}",'
            f'"mcu":{{"chip":"STM32F103RCT6","context":"{context.as_posix()}"}},'
            f'"build":{{"config":"{build_config.as_posix()}"}},'
            f'"debug":{{"target":"{target_config.as_posix()}","task":"{task_config.as_posix()}"}}'
            '}'
        ),
        encoding="utf-8",
    )

    report = plan_workflow(
        project_path=PROJECT,
        context_path=context,
        workspace_config=config_dir / "config.json",
        chip="STM32F103RCT6",
    )

    assert report["ok"] is True
    assert report["status"] == "ready_for_nonvision_debug"
    for call in report["recommended_tool_calls"]:
        assert_enriched_tool_call(call)
    assert [item["tool"] for item in report["recommended_tool_calls"]] == [
        "run_ai_debug",
        "accept_nonvision",
        "run_ai_debug",
    ]
    dry_run = report["recommended_tool_calls"][0]
    assert dry_run["arguments"]["mode"] == "dry-run"
    assert dry_run["safety"]["touches_hardware"] is False
    assert dry_run["safety"]["flash_allowed"] is False
    assert dry_run["safety"]["repair_allowed"] is False
    assert "--workspace-config" in dry_run["cli_args"]
    accept = report["recommended_tool_calls"][1]
    assert accept["arguments"]["output_dir"] == str(config_dir)
    assert accept["safety"]["writes_files"] is True
    assert accept["safety"]["flash_allowed"] is False
    read_only = report["recommended_tool_calls"][2]
    assert read_only["arguments"]["mode"] == "read-only"
    assert read_only["safety"]["touches_hardware"] is True
    assert read_only["safety"]["flash_allowed"] is False
