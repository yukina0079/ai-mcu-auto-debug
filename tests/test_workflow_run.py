from __future__ import annotations

import json
from pathlib import Path

from ai_mcu_debug.api import check_prepared_context, prepare_context
from ai_mcu_debug.workflow_run import run_workflow


ROOT = Path(__file__).resolve().parents[1]
PROJECT = ROOT / "examples/firmware/stm32f103_blinky"
SVD = ROOT / "examples/svd/STM32F103_min.svd"
LINKER = PROJECT / "linker.stm32f103rct6.ld"
STARTUP = PROJECT / "src/startup_stm32f103.c"
DATASHEET = ROOT / "examples/docs/stm32f103_datasheet_notes.md"
ERRATA = ROOT / "examples/docs/stm32f103_errata_notes.md"


def test_workflow_run_stops_for_missing_user_documents(tmp_path: Path) -> None:
    project = tmp_path / "empty_project"
    project.mkdir()

    report = run_workflow(
        project_path=project,
        context_path=tmp_path / "mcu_context.json",
        workspace_config=tmp_path / ".embeddedskills/config.json",
        report_dir=tmp_path / "workflow_run",
        chip="STM32F103RCT6",
    )

    assert report["ok"] is False
    assert report["status"] == "awaiting_user_documents"
    assert report["user_requests"]
    assert report["executed_tool_calls"] == []
    assert report["policy"]["flash_allowed"] is False
    assert Path(report["report_path"]).exists()


def test_workflow_run_executes_safe_recommendations_until_nonvision_ready(tmp_path: Path) -> None:
    executed: list[str] = []
    context = tmp_path / "mcu_context.json"
    workspace_config = tmp_path / ".embeddedskills/config.json"

    def fake_executor(call: dict) -> dict:
        tool = call["tool"]
        executed.append(tool)
        args = call["arguments"]
        if tool == "prepare_mcu_context":
            return prepare_context(**args)
        if tool == "check_mcu_context":
            return check_prepared_context(**args)
        if tool == "init_workspace":
            _write_minimal_workspace_config(workspace_config, context, include_debug=False)
            return {"ok": True, "status": "ok", "config": str(workspace_config)}
        if tool == "workspace_status":
            return {"ok": True, "status": "ok", "config": args["config"]}
        if tool in {"run_ai_debug", "accept_nonvision"}:
            return {"ok": True, "status": "ok", "artifacts": [{"kind": tool, "path": str(tmp_path / f"{tool}.json")}]}
        raise AssertionError(tool)

    report = run_workflow(
        project_path=PROJECT,
        context_path=context,
        workspace_config=workspace_config,
        report_dir=tmp_path / "workflow_run",
        chip="STM32F103RCT6",
        svd_path=SVD,
        linker_path=LINKER,
        startup_path=STARTUP,
        extra_docs=[("datasheet", DATASHEET), ("errata", ERRATA)],
        max_steps=3,
        executor=fake_executor,
    )

    assert report["ok"] is True
    assert report["status"] == "ok"
    assert executed == [
        "prepare_mcu_context",
        "check_mcu_context",
        "init_workspace",
        "workspace_status",
        "run_ai_debug",
        "accept_nonvision",
    ]
    assert all(not call["safety"]["flash_allowed"] for call in report["executed_tool_calls"])


def test_workflow_run_blocks_file_writes_when_policy_disallows_them(tmp_path: Path) -> None:
    def forbidden_executor(call: dict) -> dict:
        raise AssertionError(f"executor should not run: {call['tool']}")

    report = run_workflow(
        project_path=PROJECT,
        context_path=tmp_path / "mcu_context.json",
        workspace_config=tmp_path / ".embeddedskills/config.json",
        report_dir=tmp_path / "workflow_run",
        chip="STM32F103RCT6",
        svd_path=SVD,
        linker_path=LINKER,
        startup_path=STARTUP,
        extra_docs=[("datasheet", DATASHEET), ("errata", ERRATA)],
        allow_file_writes=False,
        executor=forbidden_executor,
    )

    assert report["ok"] is False
    assert report["status"] == "execution_blocked_by_policy"
    assert report["executed_tool_calls"] == []
    assert report["skipped_tool_calls"][0]["tool"] == "prepare_mcu_context"
    assert report["skipped_tool_calls"][0]["decision"]["reason"] == "file_writes_not_allowed"


def test_workflow_run_records_executor_exceptions(tmp_path: Path) -> None:
    def broken_executor(call: dict) -> dict:
        raise RuntimeError("adapter exploded")

    report = run_workflow(
        project_path=PROJECT,
        context_path=tmp_path / "mcu_context.json",
        workspace_config=tmp_path / ".embeddedskills/config.json",
        report_dir=tmp_path / "workflow_run",
        chip="STM32F103RCT6",
        svd_path=SVD,
        linker_path=LINKER,
        startup_path=STARTUP,
        extra_docs=[("datasheet", DATASHEET), ("errata", ERRATA)],
        executor=broken_executor,
    )

    assert report["ok"] is False
    assert report["status"] == "tool_call_exception"
    assert report["executed_tool_calls"][0]["result"]["error"] == "adapter exploded"


def test_workflow_run_skips_read_only_hardware_when_policy_disallows_it(tmp_path: Path) -> None:
    context = tmp_path / "mcu_context.json"
    prepared = prepare_context(
        project=PROJECT,
        output=context,
        chip="STM32F103RCT6",
        svd=SVD,
        linker=LINKER,
        startup=STARTUP,
        docs=[f"datasheet={DATASHEET}", f"errata={ERRATA}"],
    )
    assert prepared["ok"] is True
    workspace_config = tmp_path / ".embeddedskills/config.json"
    _write_minimal_workspace_config(workspace_config, context, include_debug=True)
    executed: list[str] = []

    def fake_executor(call: dict) -> dict:
        executed.append(call["tool"])
        return {"ok": True, "status": "ok"}

    report = run_workflow(
        project_path=PROJECT,
        context_path=context,
        workspace_config=workspace_config,
        report_dir=tmp_path / "workflow_run",
        chip="STM32F103RCT6",
        max_steps=1,
        allow_hardware=False,
        executor=fake_executor,
    )

    assert report["ok"] is True
    assert report["status"] == "ok_with_policy_skips"
    assert executed == ["run_ai_debug", "accept_nonvision"]
    assert report["skipped_tool_calls"][0]["tool"] == "run_ai_debug"
    assert report["skipped_tool_calls"][0]["arguments"]["mode"] == "read-only"
    assert report["skipped_tool_calls"][0]["decision"]["reason"] == "hardware_not_allowed"


def _write_minimal_workspace_config(config: Path, context: Path, *, include_debug: bool) -> None:
    config.parent.mkdir(parents=True, exist_ok=True)
    build_config = config.parent / "build.json"
    build_config.write_text("{}", encoding="utf-8")
    data = {
        "schema_version": 1,
        "project": str(PROJECT),
        "mcu": {"chip": "STM32F103RCT6", "context": str(context)},
        "build": {"config": str(build_config)},
    }
    if include_debug:
        target = config.parent / "debug.target.json"
        task = config.parent / "debug_task.json"
        target.write_text("{}", encoding="utf-8")
        task.write_text("{}", encoding="utf-8")
        data["debug"] = {"target": str(target), "task": str(task)}
    config.write_text(json.dumps(data), encoding="utf-8")
